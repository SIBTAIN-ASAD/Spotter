"""Fuel stop optimization."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from apps.core.exceptions import BusinessRuleError
from apps.fuel.domain import FuelStopCandidate


@dataclass(frozen=True, slots=True)
class PlannedFuelStop:
    station_id: int
    opis_id: str
    name: str
    address: str
    city: str
    state: str
    retail_price: Decimal
    coordinates: object
    distance_along_route_miles: float
    gallons_purchased: Decimal
    fuel_cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class FuelPlan:
    fuel_stops: list[PlannedFuelStop]
    total_fuel_cost_usd: Decimal
    total_gallons: Decimal


class FuelOptimizer:
    """Compute minimum-cost refueling plan along a route."""

    def __init__(self, *, vehicle_range_miles: float, vehicle_mpg: float) -> None:
        if not math.isfinite(vehicle_range_miles) or vehicle_range_miles <= 0:
            raise BusinessRuleError("Vehicle range must be finite and greater than zero.")
        if not math.isfinite(vehicle_mpg) or vehicle_mpg <= 0:
            raise BusinessRuleError("Vehicle MPG must be finite and greater than zero.")
        self.vehicle_range_miles = vehicle_range_miles
        self.vehicle_mpg = vehicle_mpg

    def plan(
        self,
        *,
        total_distance_miles: float,
        candidates: list[FuelStopCandidate],
    ) -> FuelPlan:
        if not math.isfinite(total_distance_miles) or total_distance_miles <= 0:
            raise BusinessRuleError("Route distance must be finite and greater than zero.")

        total_gallons = self._gallons_for_distance(total_distance_miles)
        if total_distance_miles <= self.vehicle_range_miles:
            return FuelPlan([], Decimal("0.00"), total_gallons)

        nodes = self._build_nodes(total_distance_miles, candidates)
        if len(nodes) <= 2:
            raise BusinessRuleError("No fuel stations found within range of the route corridor.")

        # Track remaining fuel in miles to avoid accumulating MPG conversion error.
        capacity = Decimal(str(self.vehicle_range_miles))
        remaining = capacity
        mpg = Decimal(str(self.vehicle_mpg))
        miles = [Decimal(str(node["mile"])) for node in nodes]
        stops = []
        for index in range(1, len(nodes)):
            remaining -= miles[index] - miles[index - 1]
            if remaining < 0:
                raise BusinessRuleError(
                    "Unable to reach destination with available fuel stops within vehicle range."
                )
            node = nodes[index]
            if node["type"] == "destination":
                break

            # Buy only enough to reach the first cheaper station. If no cheaper
            # station is reachable, fill up (but never beyond the destination).
            desired = min(capacity, miles[-1] - miles[index])
            for target in range(index + 1, len(nodes)):
                distance = miles[target] - miles[index]
                if distance > capacity:
                    break
                if nodes[target]["price"] <= node["price"]:
                    desired = distance
                    break

            purchase = max(Decimal("0"), desired - remaining)
            if purchase == 0:
                continue
            remaining += purchase
            gallons = purchase / mpg
            candidate = node["candidate"]
            stops.append(PlannedFuelStop(
                station_id=candidate.station_id,
                opis_id=candidate.opis_id,
                name=candidate.name,
                address=candidate.address,
                city=candidate.city,
                state=candidate.state,
                retail_price=candidate.retail_price,
                coordinates=candidate.coordinates,
                distance_along_route_miles=candidate.distance_along_route_miles,
                gallons_purchased=gallons.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                fuel_cost_usd=(gallons * candidate.retail_price).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP,
                ),
            ))

        return FuelPlan(
            fuel_stops=stops,
            total_fuel_cost_usd=sum((stop.fuel_cost_usd for stop in stops), Decimal("0.00")),
            total_gallons=total_gallons,
        )

    def _build_nodes(
        self,
        total_distance_miles: float,
        candidates: list[FuelStopCandidate],
    ) -> list[dict]:
        deduped: dict[tuple[str, str, str], FuelStopCandidate] = {}
        for candidate in candidates:
            if (
                not math.isfinite(candidate.distance_along_route_miles)
                or not candidate.retail_price.is_finite()
                or candidate.retail_price < 0
            ):
                raise BusinessRuleError("Fuel station distance and price must be valid and finite.")
            key = (candidate.opis_id, candidate.city.upper(), candidate.state.upper())
            existing = deduped.get(key)
            if existing is None or candidate.retail_price < existing.retail_price:
                deduped[key] = candidate

        stations = sorted(deduped.values(), key=lambda item: item.distance_along_route_miles)
        nodes: list[dict] = [
            {
                "type": "start",
                "mile": 0.0,
                "price": Decimal("0"),
                "candidate": None,
            }
        ]

        for station in stations:
            if station.distance_along_route_miles <= 0:
                continue
            if station.distance_along_route_miles >= total_distance_miles:
                continue
            nodes.append(
                {
                    "type": "station",
                    "mile": station.distance_along_route_miles,
                    "price": station.retail_price,
                    "candidate": station,
                }
            )

        nodes.append(
            {
                "type": "destination",
                "mile": total_distance_miles,
                "price": Decimal("0"),
                "candidate": None,
            }
        )
        return nodes

    def _gallons_for_distance(self, distance_miles: float) -> Decimal:
        gallons = Decimal(str(distance_miles)) / Decimal(str(self.vehicle_mpg))
        return gallons.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
