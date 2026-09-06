"""Core app tests."""

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import AnonRateThrottle

from apps.core.constants import Coordinates
from apps.core.geo import cumulative_distances_miles, decode_polyline, haversine_miles


def test_haversine_miles_known_distance():
    nyc = Coordinates(latitude=40.7128, longitude=-74.0060)
    philly = Coordinates(latitude=39.9526, longitude=-75.1652)
    distance = haversine_miles(nyc, philly)
    assert 75 <= distance <= 95


def test_decode_polyline_roundtrip():
    # Encoded polyline for a short path near NYC.
    encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    points = decode_polyline(encoded)
    assert len(points) >= 2
    cumulative = cumulative_distances_miles(points)
    assert cumulative[0] == 0.0
    assert cumulative[-1] > 0.0


@pytest.mark.django_db
def test_health_check_returns_ok():
    client = APIClient()
    response = client.get(reverse("health-check"))
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.django_db
def test_health_probes_do_not_consume_route_request_quota(monkeypatch):
    monkeypatch.setattr(AnonRateThrottle, "THROTTLE_RATES", {"anon": "1/min"})
    client = APIClient(REMOTE_ADDR="192.0.2.77")
    key = "throttle_anon_192.0.2.77"
    cache.delete(key)
    try:
        for _ in range(3):
            assert client.get(reverse("health-check")).status_code == 200
        # Invalid route input avoids any external requests while exercising
        # the real route endpoint's throttle and validation path.
        payload = {"start": "", "finish": "Boston, MA"}
        assert client.post(reverse("route-plan"), payload, format="json").status_code == 400
        assert client.post(reverse("route-plan"), payload, format="json").status_code == 429
        assert client.get(reverse("health-check")).status_code == 200
    finally:
        cache.delete(key)
