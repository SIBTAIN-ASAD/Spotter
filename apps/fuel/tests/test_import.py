"""Fuel import transaction regression tests."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.core.constants import Coordinates
from apps.core.exceptions import ServiceUnavailableError
from apps.fuel.models import FuelStation


@pytest.fixture
def fuel_csv(tmp_path):
    path = tmp_path / "stations.csv"
    path.write_text(
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
        "101,New station,Main Street,Austin,TX,1,3.00\n"
        "102,Other station,Second Street,Dallas,TX,2,3.50\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.django_db
def test_failed_clear_import_restores_existing_stations(fuel_stations, fuel_csv):
    original_rows = list(FuelStation.objects.order_by("pk").values())
    with patch(
        "apps.fuel.management.commands.load_fuel_stations."
        "GeocodeCacheService.get_city_state_coordinates",
        side_effect=[Coordinates(30.2672, -97.7431), ServiceUnavailableError("Timeout")],
    ), pytest.raises(ServiceUnavailableError):
        call_command("load_fuel_stations", csv_path=str(fuel_csv), clear=True, stdout=StringIO())
    assert list(FuelStation.objects.order_by("pk").values()) == original_rows


@pytest.mark.django_db
def test_successful_clear_import_replaces_existing_stations(fuel_stations, fuel_csv):
    with patch(
        "apps.fuel.management.commands.load_fuel_stations."
        "GeocodeCacheService.get_city_state_coordinates",
        return_value=Coordinates(30.2672, -97.7431),
    ):
        call_command("load_fuel_stations", csv_path=str(fuel_csv), clear=True, stdout=StringIO())
    assert set(FuelStation.objects.values_list("opis_id", flat=True)) == {"101", "102"}
