"""Routing external service clients."""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod

import httpx
from django.conf import settings

from apps.core.constants import Coordinates
from apps.core.exceptions import ExternalServiceError, ServiceUnavailableError
from apps.core.geo import decode_polyline

logger = logging.getLogger(__name__)


class RoutingClient(ABC):
    @abstractmethod
    def get_route(self, start: Coordinates, finish: Coordinates) -> dict:
        raise NotImplementedError


class OSRMRoutingClient(RoutingClient):
    """Open Source Routing Machine client."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OSRM_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self._client = client

    def get_route(self, start: Coordinates, finish: Coordinates) -> dict:
        coordinates = f"{start.longitude},{start.latitude};{finish.longitude},{finish.latitude}"
        url = f"{self.base_url}/route/v1/driving/{coordinates}"
        params = {"overview": "full", "geometries": "polyline", "steps": "false"}

        try:
            if self._client:
                response = self._client.get(url, params=params, timeout=self.timeout)
            else:
                with httpx.Client() as client:
                    response = client.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("OSRM request failed", exc_info=exc)
            raise ServiceUnavailableError("Routing service is unavailable.") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalServiceError("Routing service returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise ExternalServiceError("Routing service returned an invalid response.")
        if payload.get("code") != "Ok" or not payload.get("routes"):
            message = payload.get("message", "Unable to calculate route.")
            raise ExternalServiceError(message)

        routes = payload["routes"]
        if not isinstance(routes, list) or not isinstance(routes[0], dict):
            raise ExternalServiceError("Routing service returned invalid routes.")
        route = routes[0]
        geometry = route.get("geometry")
        if not geometry:
            raise ExternalServiceError("Routing service returned an empty geometry.")

        if not isinstance(geometry, str):
            raise ExternalServiceError("Routing service returned an invalid geometry.")
        try:
            polyline = decode_polyline(geometry)
        except (IndexError, ValueError) as exc:
            raise ExternalServiceError("Routing service returned an invalid geometry.") from exc
        if len(polyline) < 2:
            raise ExternalServiceError("Routing service returned an invalid geometry.")

        for field in ("distance", "duration"):
            value = route.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ExternalServiceError(f"Routing service returned an invalid {field}.")
        distance_miles = route["distance"] / 1609.344
        duration_seconds = route["duration"]

        return {
            "polyline": polyline,
            "distance_miles": distance_miles,
            "duration_seconds": duration_seconds,
            "geometry_geojson": {
                "type": "LineString",
                "coordinates": [[point.longitude, point.latitude] for point in polyline],
            },
        }
