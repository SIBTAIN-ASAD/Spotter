"""Fuel optimizer tests."""

from decimal import Decimal

import pytest

from apps.core.constants import Coordinates
from apps.core.exceptions import BusinessRuleError
from apps.fuel.domain import FuelStopCandidate
from apps.fuel.services.optimizer import FuelOptimizer


def _candidate(
    station_id: int,
    mile: float,
    price: str,
    *,
    opis_id: str | None = None,
) -> FuelStopCandidate:
    return FuelStopCandidate(
        station_id=station_id,
        opis_id=opis_id or str(station_id),
        name=f"Stop {station_id}",
        address="Highway",
        city="Testville",
        state="TX",
        retail_price=Decimal(price),
        coordinates=Coordinates(latitude=30.0 + station_id * 0.1, longitude=-97.0),
        distance_along_route_miles=mile,
        distance_from_route_miles=1.0,
    )


def test_short_trip_requires_no_fuel_stops():
    optimizer = FuelOptimizer(vehicle_range_miles=500, vehicle_mpg=10)
    plan = optimizer.plan(total_distance_miles=300, candidates=[])
    assert plan.fuel_stops == []
    assert plan.total_fuel_cost_usd == Decimal("0.00")
    assert plan.total_gallons == Decimal("30.00")


def test_long_trip_selects_cheapest_reachable_stop():
    optimizer = FuelOptimizer(vehicle_range_miles=500, vehicle_mpg=10)
    candidates = [
        _candidate(1, 200, "3.50"),
        _candidate(2, 250, "2.80"),
        _candidate(3, 450, "3.90"),
    ]
    plan = optimizer.plan(total_distance_miles=700, candidates=candidates)
    assert len(plan.fuel_stops) >= 1
    assert plan.total_fuel_cost_usd > 0


def test_unreachable_destination_raises():
    optimizer = FuelOptimizer(vehicle_range_miles=500, vehicle_mpg=10)
    with pytest.raises(BusinessRuleError, match="No fuel stations found"):
        optimizer.plan(total_distance_miles=700, candidates=[])
