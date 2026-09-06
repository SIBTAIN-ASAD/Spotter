"""Routing provider contract tests without live network requests."""

import httpx
import pytest

from apps.core.constants import Coordinates
from apps.core.exceptions import ExternalServiceError, ServiceUnavailableError
from apps.routing.clients import OSRMRoutingClient

GEOMETRY = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
START = Coordinates(38.5, -120.2)
FINISH = Coordinates(43.252, -126.453)


def get_route(response):
    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
        return OSRMRoutingClient(client=client).get_route(START, FINISH)


def test_valid_route_response():
    result = get_route(httpx.Response(200, json={
        "code": "Ok",
        "routes": [{"geometry": GEOMETRY, "distance": 1609.344, "duration": 60}],
    }))
    assert result["distance_miles"] == pytest.approx(1)
    assert result["duration_seconds"] == 60
    assert result["polyline"][0] == START
    assert result["polyline"][-1] == FINISH


@pytest.mark.parametrize("payload", [
    None, [], "unexpected", {"code": "Ok", "routes": "unexpected"},
    {"code": "Ok", "routes": [None]},
    {"code": "NoRoute", "routes": []},
])
def test_invalid_response_shape(payload):
    with pytest.raises(ExternalServiceError):
        get_route(httpx.Response(200, json=payload))


def test_invalid_json():
    with pytest.raises(ExternalServiceError):
        get_route(httpx.Response(200, text="<html>upstream error</html>"))


@pytest.mark.parametrize("geometry", ["", "_", "?", "??", [1, 2]])
def test_invalid_geometry(geometry):
    with pytest.raises(ExternalServiceError):
        get_route(httpx.Response(200, json={
            "code": "Ok",
            "routes": [{"geometry": geometry, "distance": 1, "duration": 1}],
        }))


@pytest.mark.parametrize("field", ["distance", "duration"])
@pytest.mark.parametrize("value", [None, "1", True, -1])
def test_invalid_route_measurements(field, value):
    route = {"geometry": GEOMETRY, "distance": 1, "duration": 1}
    route[field] = value
    with pytest.raises(ExternalServiceError):
        get_route(httpx.Response(200, json={"code": "Ok", "routes": [route]}))


@pytest.mark.parametrize("field", ["distance", "duration"])
def test_missing_route_measurement(field):
    route = {"geometry": GEOMETRY, "distance": 1, "duration": 1}
    del route[field]
    with pytest.raises(ExternalServiceError):
        get_route(httpx.Response(200, json={"code": "Ok", "routes": [route]}))


def test_http_error_remains_service_unavailable():
    with pytest.raises(ServiceUnavailableError):
        get_route(httpx.Response(503))
