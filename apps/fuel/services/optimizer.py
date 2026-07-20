"""Fuel stop optimization."""

from __future__ import annotations

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
        self.vehicle_range_miles = vehicle_range_miles
        self.vehicle_mpg = vehicle_mpg

    def plan(
        self,
        *,
        total_distance_miles: float,
        candidates: list[FuelStopCandidate],
    ) -> FuelPlan:
        if total_distance_miles <= 0:
            raise BusinessRuleError("Route distance must be greater than zero.")

        if total_distance_miles <= self.vehicle_range_miles:
            gallons = self._gallons_for_distance(total_distance_miles)
            return FuelPlan(
                fuel_stops=[],
                total_fuel_cost_usd=Decimal("0.00"),
                total_gallons=gallons,
            )

        nodes = self._build_nodes(total_distance_miles, candidates)
        if len(nodes) <= 2 and total_distance_miles > self.vehicle_range_miles:
            raise BusinessRuleError(
                "No fuel stations found within range of the route corridor."
            )

        predecessors, min_costs = self._shortest_cost_path(nodes)
        destination_index = len(nodes) - 1
        if min_costs[destination_index] == float("inf"):
            raise BusinessRuleError(
                "Unable to reach destination with available fuel stops within vehicle range."
            )

        path = self._reconstruct_path(predecessors, destination_index)
        fuel_stops = self._build_fuel_stops(nodes, path)
        total_cost = Decimal(str(min_costs[destination_index])).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_gallons = sum((stop.gallons_purchased for stop in fuel_stops), Decimal("0.00"))
        total_gallons = total_gallons.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return FuelPlan(
            fuel_stops=fuel_stops,
            total_fuel_cost_usd=total_cost,
            total_gallons=total_gallons,
        )

    def _build_nodes(
        self,
        total_distance_miles: float,
        candidates: list[FuelStopCandidate],
    ) -> list[dict]:
        deduped: dict[tuple[str, str, str], FuelStopCandidate] = {}
        for candidate in candidates:
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

    def _shortest_cost_path(self, nodes: list[dict]) -> tuple[list[int | None], list[float]]:
        size = len(nodes)
        min_costs = [float("inf")] * size
        predecessors: list[int | None] = [None] * size
        min_costs[0] = 0.0

        for target in range(1, size):
            for source in range(target):
                distance = nodes[target]["mile"] - nodes[source]["mile"]
                if distance > self.vehicle_range_miles:
                    continue

                gallons = float(self._gallons_for_distance(distance))
                segment_cost = 0.0 if source == 0 else float(nodes[source]["price"]) * gallons
                candidate_cost = min_costs[source] + segment_cost
                if candidate_cost < min_costs[target]:
                    min_costs[target] = candidate_cost
                    predecessors[target] = source

        return predecessors, min_costs

    @staticmethod
    def _reconstruct_path(predecessors: list[int | None], destination_index: int) -> list[int]:
        path: list[int] = []
        current: int | None = destination_index
        while current is not None:
            path.append(current)
            current = predecessors[current]
        path.reverse()
        return path

    def _build_fuel_stops(self, nodes: list[dict], path: list[int]) -> list[PlannedFuelStop]:
        fuel_stops: list[PlannedFuelStop] = []

        for idx in range(len(path) - 1):
            source_index = path[idx]
            target_index = path[idx + 1]
            source = nodes[source_index]
            target = nodes[target_index]

            if source["type"] != "station":
                continue

            distance = target["mile"] - source["mile"]
            gallons = self._gallons_for_distance(distance)
            fuel_cost = (source["price"] * gallons).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            candidate: FuelStopCandidate = source["candidate"]

            fuel_stops.append(
                PlannedFuelStop(
                    station_id=candidate.station_id,
                    opis_id=candidate.opis_id,
                    name=candidate.name,
                    address=candidate.address,
                    city=candidate.city,
                    state=candidate.state,
                    retail_price=candidate.retail_price,
                    coordinates=candidate.coordinates,
                    distance_along_route_miles=candidate.distance_along_route_miles,
                    gallons_purchased=gallons,
                    fuel_cost_usd=fuel_cost,
                )
            )

        return fuel_stops

    def _gallons_for_distance(self, distance_miles: float) -> Decimal:
        gallons = Decimal(str(distance_miles)) / Decimal(str(self.vehicle_mpg))
        return gallons.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
