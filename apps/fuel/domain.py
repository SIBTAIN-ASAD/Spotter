"""Fuel domain objects."""

from dataclasses import dataclass
from decimal import Decimal

from apps.core.constants import Coordinates


@dataclass(frozen=True, slots=True)
class FuelStopCandidate:
    station_id: int
    opis_id: str
    name: str
    address: str
    city: str
    state: str
    retail_price: Decimal
    coordinates: Coordinates
    distance_along_route_miles: float
    distance_from_route_miles: float
