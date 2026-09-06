"""Geocoding service tests."""

from unittest.mock import Mock, patch

import pytest

from apps.core.constants import Coordinates
from apps.core.exceptions import ExternalServiceError, ServiceUnavailableError
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


def test_empty_remote_clients_disables_network_on_local_miss():
    local = Mock()
    local.geocode.side_effect = ExternalServiceError("Not in local data")
    with patch("httpx.Client") as http_client:
        client = CompositeGeocodingClient(local_client=local, remote_clients=[])
        with pytest.raises(ServiceUnavailableError):
            client.geocode("Unknown Town, TX")
        http_client.assert_not_called()


def test_omitted_remote_clients_keeps_default_providers():
    client = CompositeGeocodingClient(local_client=Mock())
    assert [type(provider).__name__ for provider in client.remote_clients] == [
        "PhotonGeocodingClient", "NominatimGeocodingClient",
    ]


def test_explicit_remote_provider_is_used_on_local_miss():
    local = Mock()
    local.geocode.side_effect = ExternalServiceError("Not in local data")
    remote = Mock()
    remote.geocode.return_value = Coordinates(30, -100)
    client = CompositeGeocodingClient(local_client=local, remote_clients=[remote])
    assert client.geocode("Example, TX") == Coordinates(30, -100)
    remote.geocode.assert_called_once_with("Example, TX")
