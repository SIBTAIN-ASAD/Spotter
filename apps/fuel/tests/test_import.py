"""Fuel import transaction regression tests."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.constants import Coordinates
from apps.core.exceptions import ServiceUnavailableError
from apps.fuel.management.commands.load_fuel_stations import Command
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


@pytest.mark.parametrize("price", ["NaN", "sNaN", "Infinity", "-Infinity", "-1", "10000", "bad"])
@pytest.mark.django_db
def test_invalid_prices_fail_before_clear(price, fuel_csv, fuel_stations):
    fuel_csv.write_text(fuel_csv.read_text().replace("3.50", price))
    before = list(FuelStation.objects.order_by("pk").values())
    with pytest.raises(CommandError, match="[Pp]rice.*line 3"):
        call_command("load_fuel_stations", csv_path=str(fuel_csv), clear=True, stdout=StringIO())
    assert list(FuelStation.objects.order_by("pk").values()) == before


@pytest.mark.parametrize("contents", ["", "City,State\nAustin,TX\n"])
def test_missing_headers_have_actionable_error(contents, tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(contents)
    with pytest.raises(CommandError, match="Missing CSV columns:.*Retail Price"):
        Command()._read_csv(path)


@pytest.mark.parametrize("row", [
    "101,New station,Main Street,Austin,TX",
    "101,New station,Main Street, ,TX,1,3.00",
    "101,New station,Main Street,Austin,TX,1,3.00,unexpected",
])
def test_malformed_rows_have_line_number(row, fuel_csv):
    header = fuel_csv.read_text().splitlines()[0]
    fuel_csv.write_text(f"{header}\n{row}\n")
    with pytest.raises(CommandError, match="CSV line 2"):
        Command()._read_csv(fuel_csv)


def test_optional_rack_id_can_be_missing_and_prices_deduplicate(tmp_path):
    path = tmp_path / "stations.csv"
    path.write_text(
        "OPIS Truckstop ID,Truckstop Name,Address,City,State,Retail Price,Rack ID\n"
        "101,Station,Main Street,Austin,TX,3.25\n"
        "101,Station,Main Street,Austin,TX,0\n"
    )
    rows = Command()._read_csv(path)
    assert len(rows) == 1
    assert rows[0]["retail_price"] == 0
    assert rows[0]["rack_id"] == ""
