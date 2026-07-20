"""Shared domain types and constants."""

from dataclasses import dataclass

USA_STATE_CODES = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
    }
)


@dataclass(frozen=True, slots=True)
class Coordinates:
    latitude: float
    longitude: float

    def as_tuple(self) -> tuple[float, float]:
        return (self.latitude, self.longitude)

    def as_lng_lat(self) -> tuple[float, float]:
        return (self.longitude, self.latitude)

    def as_geojson_point(self) -> dict:
        return {"type": "Point", "coordinates": [self.longitude, self.latitude]}


@dataclass(frozen=True, slots=True)
class Location:
    coordinates: Coordinates
    label: str | None = None
