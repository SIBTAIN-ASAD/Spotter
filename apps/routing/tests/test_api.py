"""Route planning API tests."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.constants import Coordinates, Location
from apps.fuel.services.optimizer import FuelPlan, PlannedFuelStop


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def mock_planner_result():
    start = Location(
        coordinates=Coordinates(latitude=40.7128, longitude=-74.0060),
        label="New York, NY",
    )
    finish = Location(
        coordinates=Coordinates(latitude=38.9072, longitude=-77.0369),
        label="Washington, DC",
    )
    route_geometry = {
        "type": "LineString",
        "coordinates": [[-74.0060, 40.7128], [-77.0369, 38.9072]],
    }
    fuel_stop = PlannedFuelStop(
        station_id=1,
        opis_id="1",
        name="PA Stop",
        address="I-76",
        city="Philadelphia",
        state="PA",
        retail_price=Decimal("3.10"),
        coordinates=Coordinates(latitude=39.9526, longitude=-75.1652),
        distance_along_route_miles=100.0,
        gallons_purchased=Decimal("20.00"),
        fuel_cost_usd=Decimal("62.00"),
    )
    fuel_plan = FuelPlan(
        fuel_stops=[fuel_stop],
        total_fuel_cost_usd=Decimal("62.00"),
        total_gallons=Decimal("20.00"),
    )
    return {
        "start": start,
        "finish": finish,
        "route_geometry": route_geometry,
        "fuel_plan": fuel_plan,
        "distance_miles": 225.5,
        "duration_seconds": 14400.0,
    }


@pytest.mark.django_db
def test_route_plan_validation_errors(api_client):
    url = reverse("route-plan")
    response = api_client.post(url, {"start": "", "finish": "Washington, DC"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in response.json()


@pytest.mark.django_db
@patch("apps.routing.views.RoutePlannerService.plan_route")
def test_route_plan_success(mock_plan_route, api_client, mock_planner_result):
    from apps.routing.services import RoutePlanResult

    mock_plan_route.return_value = RoutePlanResult(
        start=mock_planner_result["start"],
        finish=mock_planner_result["finish"],
        route_geometry=mock_planner_result["route_geometry"],
        map_geojson={"type": "FeatureCollection", "features": []},
        distance_miles=mock_planner_result["distance_miles"],
        duration_seconds=mock_planner_result["duration_seconds"],
        fuel_stops=[
            {
                "station_id": 1,
                "name": "PA Stop",
                "retail_price": 3.10,
                "location": {"type": "Point", "coordinates": [-75.1652, 39.9526]},
                "fuel_cost_usd": 62.0,
            }
        ],
        total_fuel_cost_usd=Decimal("62.00"),
        total_gallons_consumed=Decimal("22.55"),
        vehicle_range_miles=500,
        vehicle_mpg=10,
    )

    url = reverse("route-plan")
    payload = {
        "start": {"lat": 40.7128, "lng": -74.0060, "label": "New York, NY"},
        "finish": {"lat": 38.9072, "lng": -77.0369, "label": "Washington, DC"},
    }
    response = api_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["distance_miles"] == 225.5
    assert body["total_fuel_cost_usd"] == 62.0
    assert body["route"]["type"] == "LineString"
    assert "map" in body


@pytest.mark.django_db
@patch("apps.routing.views.RoutePlannerService.plan_route")
def test_route_plan_external_service_error(mock_plan_route, api_client):
    from apps.core.exceptions import ServiceUnavailableError

    mock_plan_route.side_effect = ServiceUnavailableError("Routing service is unavailable.")
    url = reverse("route-plan")
    response = api_client.post(
        url,
        {"start": "New York, NY", "finish": "Boston, MA"},
        format="json",
    )
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
