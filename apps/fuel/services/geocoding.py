"""Geocoding integrations."""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

import httpx
from django.conf import settings

from apps.core.constants import USA_STATE_CODES, Coordinates
from apps.core.exceptions import ExternalServiceError, ServiceUnavailableError
from apps.fuel.models import GeocodeCache

logger = logging.getLogger(__name__)

STATE_NAME_TO_CODE = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
    "DISTRICT OF COLUMBIA": "DC",
}


class GeocodingClient(ABC):
    @abstractmethod
    def geocode(self, query: str) -> Coordinates:
        raise NotImplementedError


def parse_us_location(query: str) -> tuple[str, str] | None:
    """Parse 'City, ST' or 'City, State Name' from a US location string."""
    cleaned = query.strip()
    cleaned = re.sub(r",?\s*(USA|United States)\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    if not cleaned:
        return None

    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    if len(parts) < 2:
        return None

    city = " ".join(parts[:-1])
    state_token = parts[-1].upper()

    if len(state_token) == 2 and state_token in USA_STATE_CODES:
        return city, state_token

    state_code = STATE_NAME_TO_CODE.get(state_token)
    if state_code:
        return city, state_code

    return None


class LocalGeocodingClient(GeocodingClient):
    """Resolve US city/state strings from bundled data - no external API calls."""

    def __init__(
        self,
        *,
        major_cities_path: Path | None = None,
        seed_cache: GeocodeCacheService | None = None,
    ) -> None:
        self.major_cities_path = major_cities_path or (
            Path(settings.BASE_DIR) / "data" / "major_us_cities.json"
        )
        self.seed_cache = seed_cache or GeocodeCacheService()
        self._major_cities = self._load_major_cities()

    def geocode(self, query: str) -> Coordinates:
        parsed = parse_us_location(query)
        if parsed is None:
            raise ExternalServiceError(
                f"Could not parse location '{query}'. Use 'City, ST' format or coordinates."
            )

        city, state = parsed
        coords = self._lookup_major_city(city, state)
        if coords:
            return coords

        coords = self.seed_cache.get_city_state_coordinates(city, state)
        if coords:
            return coords

        raise ExternalServiceError(f"Could not find coordinates for '{city}, {state}'.")

    def _load_major_cities(self) -> dict[str, list[float]]:
        if not self.major_cities_path.exists():
            return {}
        with self.major_cities_path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _lookup_major_city(self, city: str, state: str) -> Coordinates | None:
        key = f"{city.upper()}|{state.upper()}"
        coords = self._major_cities.get(key)
        if coords is None:
            return None
        return Coordinates(latitude=coords[0], longitude=coords[1])


class PhotonGeocodingClient(GeocodingClient):
    """Komoot Photon geocoder - free fallback for US addresses."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or "https://photon.komoot.io/api/").rstrip("/") + "/"
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self._client = client

    def geocode(self, query: str) -> Coordinates:
        params = {"q": query, "limit": 1, "lang": "en"}
        headers = {
            "User-Agent": settings.NOMINATIM_USER_AGENT,
            "Accept": "application/json",
        }

        try:
            response = self._request(params, headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Photon geocoding request failed", exc_info=exc)
            raise ServiceUnavailableError("Geocoding service is unavailable.") from exc

        features = response.json().get("features", [])
        if not features:
            raise ExternalServiceError(f"Could not geocode location: {query}")

        geometry = features[0]["geometry"]["coordinates"]
        return Coordinates(latitude=float(geometry[1]), longitude=float(geometry[0]))

    def _request(self, params: dict, headers: dict) -> httpx.Response:
        if self._client:
            return self._client.get(
                self.base_url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
        with httpx.Client() as client:
            return client.get(
                self.base_url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )


class NominatimGeocodingClient(GeocodingClient):
    """OpenStreetMap Nominatim geocoder for US locations."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        user_agent: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or settings.NOMINATIM_BASE_URL).rstrip("/")
        self.user_agent = user_agent or settings.NOMINATIM_USER_AGENT
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self._client = client

    def geocode(self, query: str) -> Coordinates:
        params = {"q": query, "format": "json", "limit": 1, "countrycodes": "us"}
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": "en",
        }

        try:
            response = self._request(params, headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Nominatim request failed", exc_info=exc)
            raise ServiceUnavailableError("Geocoding service is unavailable.") from exc

        results = response.json()
        if not results:
            raise ExternalServiceError(f"Could not geocode location: {query}")

        result = results[0]
        return Coordinates(latitude=float(result["lat"]), longitude=float(result["lon"]))

    def _request(self, params: dict, headers: dict) -> httpx.Response:
        if self._client:
            return self._client.get(
                f"{self.base_url}/search",
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
        with httpx.Client() as client:
            return client.get(
                f"{self.base_url}/search",
                params=params,
                headers=headers,
                timeout=self.timeout,
            )


class CompositeGeocodingClient(GeocodingClient):
    """Try local lookup first, then remote providers."""

    def __init__(
        self,
        *,
        local_client: GeocodingClient | None = None,
        remote_clients: list[GeocodingClient] | None = None,
    ) -> None:
        self.local_client = local_client or LocalGeocodingClient()
        self.remote_clients = (
            [PhotonGeocodingClient(), NominatimGeocodingClient()]
            if remote_clients is None
            else remote_clients
        )

    def geocode(self, query: str) -> Coordinates:
        try:
            return self.local_client.geocode(query)
        except ExternalServiceError:
            logger.info("Local geocoding miss for '%s', trying remote providers.", query)

        last_error: Exception | None = None
        for client in self.remote_clients:
            try:
                return client.geocode(query)
            except (ExternalServiceError, ServiceUnavailableError) as exc:
                last_error = exc
                logger.warning(
                    "Geocoding provider %s failed for '%s'",
                    client.__class__.__name__,
                    query,
                )

        if last_error:
            raise last_error
        raise ServiceUnavailableError("Geocoding service is unavailable.")


class GeocodeCacheService:
    """Resolve city/state coordinates using DB cache, seed file, and optional remote geocoder."""

    def __init__(
        self,
        *,
        seed_path: Path | None = None,
        remote_client: GeocodingClient | None = None,
    ) -> None:
        self.seed_path = seed_path or Path(settings.BASE_DIR) / "data" / "geocode_seed.json"
        self.remote_client = remote_client
        self._seed_data = self._load_seed()

    def get_city_state_coordinates(
        self,
        city: str,
        state: str,
        *,
        allow_remote: bool = False,
    ) -> Coordinates | None:
        normalized_city = " ".join(city.split())
        normalized_state = state.strip().upper()
        if normalized_state not in USA_STATE_CODES:
            return None

        cached = GeocodeCache.objects.filter(
            city__iexact=normalized_city,
            state=normalized_state,
        ).first()
        if cached:
            return Coordinates(latitude=cached.latitude, longitude=cached.longitude)

        seed_coords = self._lookup_seed(normalized_city, normalized_state)
        if seed_coords:
            self._persist_cache(normalized_city, normalized_state, seed_coords, source="seed")
            return seed_coords

        if allow_remote and self.remote_client:
            query = f"{normalized_city}, {normalized_state}, USA"
            coords = self.remote_client.geocode(query)
            self._persist_cache(normalized_city, normalized_state, coords, source="nominatim")
            return coords

        return None

    def _load_seed(self) -> dict[str, dict[str, list[float]]]:
        if not self.seed_path.exists():
            return {}
        with self.seed_path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _lookup_seed(self, city: str, state: str) -> Coordinates | None:
        state_entries = self._seed_data.get(state.upper())
        if not state_entries:
            return None

        coords = state_entries.get(city.upper())
        if not coords:
            return None
        return Coordinates(latitude=coords[0], longitude=coords[1])

    @staticmethod
    def _persist_cache(city: str, state: str, coords: Coordinates, *, source: str) -> None:
        GeocodeCache.objects.update_or_create(
            city=city,
            state=state,
            defaults={
                "latitude": coords.latitude,
                "longitude": coords.longitude,
                "source": source,
            },
        )
