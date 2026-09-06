"""Fuel station repository."""

from __future__ import annotations

from decimal import Decimal

from apps.core.constants import Coordinates
from apps.core.geo import project_to_polyline, sample_polyline
from apps.fuel.domain import FuelStopCandidate
from apps.fuel.models import FuelStation


class FuelStationRepository:
    """Read-optimized access to fuel station data."""

    def get_cheapest_by_location(
        self,
        *,
        route_polyline: list[Coordinates],
        cumulative_miles: list[float],
        corridor_miles: float,
    ) -> list[FuelStopCandidate]:
        if not route_polyline:
            return []
        sampled_polyline, sampled_miles = sample_polyline(route_polyline, cumulative_miles)
        min_lat, max_lat, min_lng, max_lng = self._route_bounding_box(
            sampled_polyline,
            corridor_miles,
        )
        queryset = FuelStation.objects.filter(
            latitude__gte=min_lat,
            latitude__lte=max_lat,
            longitude__gte=min_lng,
            longitude__lte=max_lng,
            latitude__isnull=False,
            longitude__isnull=False,
        ).only(
            "id",
            "opis_id",
            "name",
            "address",
            "city",
            "state",
            "retail_price",
            "latitude",
            "longitude",
        )

        best_by_stop: dict[tuple[str, str, str], FuelStopCandidate] = {}
        for station in queryset.iterator(chunk_size=500):
            coords = Coordinates(latitude=station.latitude, longitude=station.longitude)
            off_route, segment, fraction = project_to_polyline(coords, sampled_polyline)
            if off_route > corridor_miles:
                continue

            route_mile = sampled_miles[segment]
            if segment + 1 < len(sampled_miles):
                route_mile += fraction * (sampled_miles[segment + 1] - sampled_miles[segment])
            dedupe_key = (station.opis_id, station.city.upper(), station.state.upper())
            candidate = FuelStopCandidate(
                station_id=station.id,
                opis_id=station.opis_id,
                name=station.name,
                address=station.address,
                city=station.city,
                state=station.state,
                retail_price=Decimal(str(station.retail_price)),
                coordinates=coords,
                distance_along_route_miles=route_mile,
                distance_from_route_miles=off_route,
            )
            existing = best_by_stop.get(dedupe_key)
            if existing is None or candidate.retail_price < existing.retail_price:
                best_by_stop[dedupe_key] = candidate

        candidates = list(best_by_stop.values())
        candidates.sort(key=lambda item: item.distance_along_route_miles)
        return candidates

    @staticmethod
    def _route_bounding_box(
        polyline: list[Coordinates],
        corridor_miles: float,
    ) -> tuple[float, float, float, float]:
        latitudes = [point.latitude for point in polyline]
        longitudes = [point.longitude for point in polyline]
        lat_padding = corridor_miles / 69.0
        lng_padding = corridor_miles / 55.0
        return (
            min(latitudes) - lat_padding,
            max(latitudes) + lat_padding,
            min(longitudes) - lng_padding,
            max(longitudes) + lng_padding,
        )
