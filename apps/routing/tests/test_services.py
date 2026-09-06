"""Integration tests for route planner service."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.core.constants import Coordinates
from apps.core.exceptions import BusinessRuleError
from apps.fuel.domain import FuelStopCandidate
from apps.fuel.repositories import FuelStationRepository
from apps.fuel.services.optimizer import FuelOptimizer
from apps.routing.clients import RoutingClient
from apps.routing.services import RoutePlannerService


class StubRoutingClient(RoutingClient):
    def get_route(self, start: Coordinates, finish: Coordinates) -> dict:
        polyline = [
            Coordinates(latitude=40.7128, longitude=-74.0060),
            Coordinates(latitude=39.9526, longitude=-75.1652),
            Coordinates(latitude=38.9072, longitude=-77.0369),
        ]
        return {
            "polyline": polyline,
            "distance_miles": 225.0,
            "duration_seconds": 14400.0,
            "geometry_geojson": {
                "type": "LineString",
                "coordinates": [[p.longitude, p.latitude] for p in polyline],
            },
        }


@pytest.mark.django_db
def test_route_planner_with_stubbed_clients(fuel_stations):
    repository = FuelStationRepository()
    planner = RoutePlannerService(
        geocoding_client=MagicMock(),
        routing_client=StubRoutingClient(),
        fuel_repository=repository,
        fuel_optimizer=FuelOptimizer(vehicle_range_miles=500, vehicle_mpg=10),
    )

    result = planner.plan_route(
        start={"lat": 40.7128, "lng": -74.0060, "label": "New York, NY"},
        finish={"lat": 38.9072, "lng": -77.0369, "label": "Washington, DC"},
    )

    assert result.distance_miles == 225.0
    assert result.total_gallons_consumed == Decimal("22.50")
    assert result.map_geojson["type"] == "FeatureCollection"
    assert len(result.map_geojson["features"]) >= 3


def test_optimizer_prefers_cheaper_station():
    optimizer = FuelOptimizer(vehicle_range_miles=500, vehicle_mpg=10)
    candidates = [
        FuelStopCandidate(
            station_id=1,
            opis_id="1",
            name="Expensive",
            address="A",
            city="A",
            state="TX",
            retail_price=Decimal("4.00"),
            coordinates=Coordinates(latitude=32.0, longitude=-97.0),
            distance_along_route_miles=400,
            distance_from_route_miles=1,
        ),
        FuelStopCandidate(
            station_id=2,
            opis_id="2",
            name="Cheap",
            address="B",
            city="B",
            state="TX",
            retail_price=Decimal("2.50"),
            coordinates=Coordinates(latitude=32.1, longitude=-97.1),
            distance_along_route_miles=450,
            distance_from_route_miles=1,
        ),
    ]
    plan = optimizer.plan(total_distance_miles=900, candidates=candidates)
    assert plan.fuel_stops
    assert plan.total_fuel_cost_usd > 0


@pytest.mark.parametrize("field", ["start", "finish"])
@pytest.mark.parametrize("coordinates", [
    Coordinates(48.8566, 2.3522),
    Coordinates(float("nan"), -97),
    Coordinates(30, 181),
])
def test_invalid_geocoded_location_is_rejected_before_routing(field, coordinates):
    geocoder = MagicMock()
    valid = Coordinates(30.2672, -97.7431)
    geocoder.geocode.side_effect = (
        [coordinates] if field == "start" else [valid, coordinates]
    )
    routing = MagicMock()
    planner = RoutePlannerService(
        geocoding_client=geocoder, routing_client=routing,
        fuel_repository=MagicMock(), fuel_optimizer=MagicMock(),
    )
    with pytest.raises(BusinessRuleError, match=field):
        planner.plan_route(start="Austin, TX", finish="Destination")
    routing.get_route.assert_not_called()


def test_valid_geocoded_location_preserves_address_label():
    geocoder = MagicMock()
    geocoder.geocode.return_value = Coordinates(30.2672, -97.7431)
    planner = RoutePlannerService(
        geocoding_client=geocoder, routing_client=MagicMock(),
        fuel_repository=MagicMock(), fuel_optimizer=MagicMock(),
    )
    location = planner._resolve_location("  Austin, TX  ", field_name="start")
    assert location.coordinates == Coordinates(30.2672, -97.7431)
    assert location.label == "Austin, TX"
    geocoder.geocode.assert_called_once_with("Austin, TX, USA")
