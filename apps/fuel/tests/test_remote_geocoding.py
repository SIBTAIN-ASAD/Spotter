"""Provider response validation and fallback tests using local HTTP transports."""

from unittest.mock import Mock

import httpx
import pytest

from apps.core.constants import Coordinates
from apps.core.exceptions import ExternalServiceError, ServiceUnavailableError
from apps.fuel.services.geocoding import (
    CompositeGeocodingClient,
    NominatimGeocodingClient,
    PhotonGeocodingClient,
)


@pytest.fixture(params=[NominatimGeocodingClient, PhotonGeocodingClient])
def provider_type(request):
    return request.param


def payload_for(provider_type, latitude, longitude):
    if provider_type is NominatimGeocodingClient:
        return [{"lat": latitude, "lon": longitude}]
    return {"features": [{"geometry": {
        "type": "Point", "coordinates": [longitude, latitude],
    }}]}


def geocode(provider_type, response):
    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
        return provider_type(client=client).geocode("Austin, TX")


def test_valid_response(provider_type):
    result = geocode(provider_type, httpx.Response(
        200, json=payload_for(provider_type, "30.2672", "-97.7431"),
    ))
    assert result == Coordinates(30.2672, -97.7431)


@pytest.mark.parametrize("latitude,longitude", [
    ("NaN", -97), ("Infinity", -97), (91, -97), (-91, -97),
    (30, 181), (30, -181), (None, -97), (True, -97), (30, {}),
])
def test_bad_coordinates(provider_type, latitude, longitude):
    with pytest.raises(ExternalServiceError):
        geocode(provider_type, httpx.Response(
            200, json=payload_for(provider_type, latitude, longitude),
        ))


@pytest.mark.parametrize("payload", [None, "unexpected", {}, [None]])
def test_bad_payload_shape(provider_type, payload):
    with pytest.raises(ExternalServiceError):
        geocode(provider_type, httpx.Response(200, json=payload))


def test_invalid_json(provider_type):
    with pytest.raises(ExternalServiceError):
        geocode(provider_type, httpx.Response(200, text="<html>Bad gateway</html>"))


@pytest.mark.parametrize("geometry", [
    None, {}, {"type": "LineString", "coordinates": [[-97, 30], [-98, 31]]},
    {"type": "Point", "coordinates": []}, {"type": "Point", "coordinates": "12"},
])
def test_photon_requires_point_geometry(geometry):
    with pytest.raises(ExternalServiceError):
        geocode(PhotonGeocodingClient, httpx.Response(
            200, json={"features": [{"geometry": geometry}]},
        ))


def test_http_failure_still_returns_service_unavailable(provider_type):
    with pytest.raises(ServiceUnavailableError):
        geocode(provider_type, httpx.Response(503))


def test_invalid_photon_response_falls_back_to_next_provider():
    local = Mock()
    local.geocode.side_effect = ExternalServiceError("Local miss")
    fallback = Mock()
    fallback.geocode.return_value = Coordinates(30, -97)
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text="not JSON"),
    )) as client:
        geocoder = CompositeGeocodingClient(
            local_client=local,
            remote_clients=[PhotonGeocodingClient(client=client), fallback],
        )
        assert geocoder.geocode("Austin, TX") == Coordinates(30, -97)
    fallback.geocode.assert_called_once_with("Austin, TX")
