"""Geocoding service tests."""

import pytest

from apps.core.constants import Coordinates
from apps.fuel.services.geocoding import (
    CompositeGeocodingClient,
    LocalGeocodingClient,
    parse_us_location,
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("New York, NY", ("New York", "NY")),
        ("Los Angeles, CA, USA", ("Los Angeles", "CA")),
        ("Washington, DC", ("Washington", "DC")),
        ("Chicago, Illinois", ("Chicago", "IL")),
    ],
)
def test_parse_us_location(query, expected):
    assert parse_us_location(query) == expected


def test_local_geocoding_major_city():
    client = LocalGeocodingClient()
    coords = client.geocode("New York, NY")
    assert coords.latitude == pytest.approx(40.7128)
    assert coords.longitude == pytest.approx(-74.006)


def test_local_geocoding_seed_city():
    client = LocalGeocodingClient()
    coords = client.geocode("Chicago, IL")
    assert isinstance(coords, Coordinates)
    assert coords.latitude == pytest.approx(41.8781, abs=0.5)


def test_composite_geocoding_uses_local_without_network():
    client = CompositeGeocodingClient(remote_clients=[])
    coords = client.geocode("Miami, FL")
    assert coords.latitude == pytest.approx(25.7617, abs=0.1)
