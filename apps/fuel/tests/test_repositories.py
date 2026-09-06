"""Route corridor and station position regression tests."""

from decimal import Decimal

import pytest

from apps.core.constants import Coordinates
from apps.core.geo import cumulative_distances_miles
from apps.fuel.models import FuelStation
from apps.fuel.repositories import FuelStationRepository


@pytest.mark.django_db
def test_station_between_vertices_is_in_corridor_and_positioned_on_route():
    station = FuelStation.objects.create(
        opis_id='midpoint', name='Midpoint', address='Road', city='Town', state='TX',
        retail_price=Decimal('3'), latitude=30, longitude=-99,
    )
    FuelStation.objects.create(
        opis_id='outside', name='Outside', address='Road', city='Town', state='TX',
        retail_price=Decimal('2'), latitude=30.1, longitude=-99,
    )
    route = [Coordinates(30, -100), Coordinates(30, -98)]
    miles = cumulative_distances_miles(route)
    result = FuelStationRepository().get_cheapest_by_location(
        route_polyline=route, cumulative_miles=miles, corridor_miles=2,
    )
    assert len(result) == 1
    assert result[0].station_id == station.pk
    assert result[0].distance_from_route_miles == pytest.approx(0)
    assert result[0].distance_along_route_miles == pytest.approx(miles[-1] / 2)


def test_empty_route_has_no_candidates():
    assert FuelStationRepository().get_cheapest_by_location(
        route_polyline=[], cumulative_miles=[], corridor_miles=2,
    ) == []
