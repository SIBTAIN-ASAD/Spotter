"""Shared pytest fixtures."""

from decimal import Decimal

import pytest

from apps.core.constants import Coordinates
from apps.fuel.models import FuelStation


@pytest.fixture
def sample_route_polyline() -> list[Coordinates]:
    return [
        Coordinates(latitude=40.7128, longitude=-74.0060),
        Coordinates(latitude=39.9526, longitude=-75.1652),
        Coordinates(latitude=38.9072, longitude=-77.0369),
    ]


@pytest.fixture
def fuel_stations(db) -> list[FuelStation]:
    stations = [
        FuelStation(
            opis_id="1",
            name="NJ Stop",
            address="I-95",
            city="Newark",
            state="NJ",
            rack_id="1",
            retail_price=Decimal("3.50"),
            latitude=40.7357,
            longitude=-74.1724,
        ),
        FuelStation(
            opis_id="2",
            name="PA Stop",
            address="I-76",
            city="Philadelphia",
            state="PA",
            rack_id="2",
            retail_price=Decimal("3.10"),
            latitude=39.9526,
            longitude=-75.1652,
        ),
        FuelStation(
            opis_id="3",
            name="MD Stop",
            address="I-95",
            city="Baltimore",
            state="MD",
            rack_id="3",
            retail_price=Decimal("3.25"),
            latitude=39.2904,
            longitude=-76.6122,
        ),
    ]
    return FuelStation.objects.bulk_create(stations)
