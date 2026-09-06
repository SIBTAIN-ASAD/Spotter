"""Route planning domain service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

from apps.core.constants import Coordinates, Location
from apps.core.exceptions import BusinessRuleError
from apps.core.geo import cumulative_distances_miles
from apps.fuel.repositories import FuelStationRepository
from apps.fuel.services.geocoding import CompositeGeocodingClient, GeocodingClient
from apps.fuel.services.optimizer import FuelOptimizer
from apps.routing.clients import OSRMRoutingClient, RoutingClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RoutePlanResult:
    start: Location
    finish: Location
    route_geometry: dict
    map_geojson: dict
    distance_miles: float
    duration_seconds: float
    fuel_stops: list[dict]
    total_fuel_cost_usd: Decimal
    total_gallons_consumed: Decimal
    vehicle_range_miles: float
    vehicle_mpg: float


class RoutePlannerService:
    """Orchestrates geocoding, routing, and fuel optimization."""

    def __init__(
        self,
        *,
        geocoding_client: GeocodingClient | None = None,
        routing_client: RoutingClient | None = None,
        fuel_repository: FuelStationRepository | None = None,
        fuel_optimizer: FuelOptimizer | None = None,
    ) -> None:
        self.geocoding_client = geocoding_client or CompositeGeocodingClient()
        self.routing_client = routing_client or OSRMRoutingClient()
        self.fuel_repository = fuel_repository or FuelStationRepository()
        self.fuel_optimizer = fuel_optimizer or FuelOptimizer(
            vehicle_range_miles=settings.VEHICLE_RANGE_MILES,
            vehicle_mpg=settings.VEHICLE_MPG,
        )

    def plan_route(self, *, start: str | dict, finish: str | dict) -> RoutePlanResult:
        start_location = self._resolve_location(start, field_name="start")
        finish_location = self._resolve_location(finish, field_name="finish")

        route = self.routing_client.get_route(
            start_location.coordinates,
            finish_location.coordinates,
        )
        polyline = route["polyline"]
        cumulative_miles = cumulative_distances_miles(polyline)
        total_distance = route["distance_miles"]

        candidates = self.fuel_repository.get_cheapest_by_location(
            route_polyline=polyline,
            cumulative_miles=cumulative_miles,
            corridor_miles=settings.ROUTE_CORRIDOR_MILES,
        )

        fuel_plan = self.fuel_optimizer.plan(
            total_distance_miles=total_distance,
            candidates=candidates,
        )

        fuel_stops = [self._serialize_fuel_stop(stop) for stop in fuel_plan.fuel_stops]
        total_gallons = (
            Decimal(str(total_distance)) / Decimal(str(settings.VEHICLE_MPG))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        map_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"kind": "route"},
                    "geometry": route["geometry_geojson"],
                },
                {
                    "type": "Feature",
                    "properties": {"kind": "start", "label": start_location.label},
                    "geometry": start_location.coordinates.as_geojson_point(),
                },
                {
                    "type": "Feature",
                    "properties": {"kind": "finish", "label": finish_location.label},
                    "geometry": finish_location.coordinates.as_geojson_point(),
                },
                *[
                    {
                        "type": "Feature",
                        "properties": {
                            "kind": "fuel_stop",
                            "name": stop["name"],
                            "retail_price": stop["retail_price"],
                            "fuel_cost_usd": stop["fuel_cost_usd"],
                        },
                        "geometry": stop["location"],
                    }
                    for stop in fuel_stops
                ],
            ],
        }

        return RoutePlanResult(
            start=start_location,
            finish=finish_location,
            route_geometry=route["geometry_geojson"],
            map_geojson=map_geojson,
            distance_miles=round(total_distance, 2),
            duration_seconds=round(route["duration_seconds"], 1),
            fuel_stops=fuel_stops,
            total_fuel_cost_usd=fuel_plan.total_fuel_cost_usd,
            total_gallons_consumed=total_gallons,
            vehicle_range_miles=settings.VEHICLE_RANGE_MILES,
            vehicle_mpg=settings.VEHICLE_MPG,
        )

    def _resolve_location(self, value: str | dict, *, field_name: str) -> Location:
        if isinstance(value, str):
            query = value.strip()
            if not query:
                raise BusinessRuleError(f"{field_name} location cannot be empty.")
            if not query.lower().endswith("usa") and "united states" not in query.lower():
                query = f"{query}, USA"
            coordinates = self.geocoding_client.geocode(query)
            return self._resolve_coordinate_dict(
                {
                    "lat": coordinates.latitude,
                    "lng": coordinates.longitude,
                    "label": value.strip(),
                },
                field_name=field_name,
            )

        if isinstance(value, dict):
            return self._resolve_coordinate_dict(value, field_name=field_name)

        raise BusinessRuleError(f"{field_name} must be a string address or coordinate object.")

    def _resolve_coordinate_dict(self, value: dict, *, field_name: str) -> Location:
        lat = value.get("lat", value.get("latitude"))
        lng = value.get("lng", value.get("longitude"))
        if lat is None or lng is None:
            raise BusinessRuleError(
                f"{field_name} coordinates must include lat/latitude and lng/longitude."
            )

        try:
            latitude = float(lat)
            longitude = float(lng)
        except (TypeError, ValueError) as exc:
            raise BusinessRuleError(f"{field_name} coordinates must be numeric.") from exc

        if not (-90 <= latitude <= 90):
            raise BusinessRuleError(f"{field_name} latitude must be between -90 and 90.")
        if not (-180 <= longitude <= 180):
            raise BusinessRuleError(f"{field_name} longitude must be between -180 and 180.")

        if not self._is_within_usa(latitude, longitude):
            raise BusinessRuleError(f"{field_name} location must be within the USA.")

        label = value.get("label")
        return Location(
            coordinates=Coordinates(latitude=latitude, longitude=longitude),
            label=label,
        )

    @staticmethod
    def _is_within_usa(latitude: float, longitude: float) -> bool:
        # Approximate bounding box for the contiguous US, Alaska, Hawaii, and Puerto Rico.
        return (
            (24.0 <= latitude <= 72.0 and -170.0 <= longitude <= -65.0)
            or (18.0 <= latitude <= 22.5 and -161.0 <= longitude <= -154.0)
        )

    @staticmethod
    def _serialize_fuel_stop(stop) -> dict:
        return {
            "station_id": stop.station_id,
            "opis_id": stop.opis_id,
            "name": stop.name,
            "address": stop.address,
            "city": stop.city,
            "state": stop.state,
            "retail_price": float(stop.retail_price),
            "location": stop.coordinates.as_geojson_point(),
            "distance_along_route_miles": round(stop.distance_along_route_miles, 2),
            "gallons_purchased": float(stop.gallons_purchased),
            "fuel_cost_usd": float(stop.fuel_cost_usd),
        }
