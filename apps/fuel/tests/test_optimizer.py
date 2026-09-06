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


def test_remaining_initial_fuel_is_not_purchased_again():
    plan = FuelOptimizer(vehicle_range_miles=500, vehicle_mpg=10).plan(
        total_distance_miles=700,
        candidates=[_candidate(1, 200, '3.50'), _candidate(2, 250, '2.80'),
                    _candidate(3, 450, '3.90')],
    )
    assert [stop.station_id for stop in plan.fuel_stops] == [2]
    assert plan.fuel_stops[0].gallons_purchased == Decimal('20.00')
    assert plan.total_fuel_cost_usd == Decimal('56.00')
    assert plan.total_gallons == Decimal('70.00')


def test_tank_carries_cheaper_fuel_past_expensive_stations():
    plan = FuelOptimizer(vehicle_range_miles=500, vehicle_mpg=10).plan(
        total_distance_miles=1000,
        candidates=[_candidate(1, 400, '2.00'), _candidate(2, 500, '5.00'),
                    _candidate(3, 800, '3.00')],
    )
    assert [stop.station_id for stop in plan.fuel_stops] == [1, 3]
    assert [stop.gallons_purchased for stop in plan.fuel_stops] == [Decimal('40'), Decimal('10')]
    assert plan.total_fuel_cost_usd == Decimal('110.00')
    assert plan.total_fuel_cost_usd == sum(stop.fuel_cost_usd for stop in plan.fuel_stops)


def test_gap_longer_than_tank_range_is_unreachable():
    with pytest.raises(BusinessRuleError, match='Unable to reach'):
        FuelOptimizer(vehicle_range_miles=500, vehicle_mpg=10).plan(
            total_distance_miles=1200, candidates=[_candidate(1, 400, '3')],
        )


@pytest.mark.parametrize('value', [0, -1, float('nan'), float('inf')])
@pytest.mark.parametrize('field', ['vehicle_range_miles', 'vehicle_mpg'])
def test_invalid_vehicle_configuration(value, field):
    values = {'vehicle_range_miles': 500, 'vehicle_mpg': 10, field: value}
    with pytest.raises(BusinessRuleError):
        FuelOptimizer(**values)


@pytest.mark.parametrize('distance', [0, -1, float('nan'), float('inf')])
def test_invalid_route_distance(distance):
    with pytest.raises(BusinessRuleError):
        FuelOptimizer(vehicle_range_miles=500, vehicle_mpg=10).plan(
            total_distance_miles=distance, candidates=[],
        )


@pytest.mark.parametrize('price', ['NaN', 'Infinity', '-1'])
def test_invalid_station_price(price):
    with pytest.raises(BusinessRuleError):
        FuelOptimizer(vehicle_range_miles=500, vehicle_mpg=10).plan(
            total_distance_miles=700, candidates=[_candidate(1, 400, price)],
        )


def test_small_routes_match_exhaustive_fuel_state_search():
    import random

    rng = random.Random(7)
    capacity, destination = 3, 8
    optimizer = FuelOptimizer(vehicle_range_miles=capacity, vehicle_mpg=1)
    for _ in range(100):
        prices = {mile: rng.randint(1, 6) for mile in range(1, destination)
                  if rng.random() < 0.7}
        # Exhaustively consider every possible whole-gallon purchase. With
        # integer station distances, capacity and prices, an optimum exists
        # at these integer fuel levels; this solver is independent of greedy choice.
        costs = {capacity: 0}
        for mile in range(1, destination + 1):
            arrived = {fuel - 1: cost for fuel, cost in costs.items() if fuel >= 1}
            costs = {}
            for fuel, cost in arrived.items():
                purchases = range(capacity - fuel + 1) if mile in prices else [0]
                for purchase in purchases:
                    level = fuel + purchase
                    candidate_cost = cost + purchase * prices.get(mile, 0)
                    costs[level] = min(costs.get(level, float('inf')), candidate_cost)
        candidates = [_candidate(mile, mile, str(price)) for mile, price in prices.items()]
        if not costs:
            with pytest.raises(BusinessRuleError):
                optimizer.plan(total_distance_miles=destination, candidates=candidates)
        else:
            plan = optimizer.plan(total_distance_miles=destination, candidates=candidates)
            assert plan.total_fuel_cost_usd == Decimal(min(costs.values())), prices
            fuel, previous = Decimal(capacity), Decimal(0)
            for stop in plan.fuel_stops:
                fuel -= Decimal(str(stop.distance_along_route_miles)) - previous
                assert fuel >= 0
                fuel += stop.gallons_purchased
                assert fuel <= capacity
                previous = Decimal(str(stop.distance_along_route_miles))
            assert fuel >= Decimal(destination) - previous
