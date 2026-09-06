"""Geospatial utility functions."""

from __future__ import annotations

import math
from itertools import pairwise

from apps.core.constants import Coordinates


def haversine_miles(a: Coordinates, b: Coordinates) -> float:
    """Return great-circle distance in miles between two coordinates."""
    radius_miles = 3958.8
    lat1, lon1 = math.radians(a.latitude), math.radians(a.longitude)
    lat2, lon2 = math.radians(b.latitude), math.radians(b.longitude)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius_miles * math.asin(min(1.0, math.sqrt(h)))


def decode_polyline(encoded: str) -> list[Coordinates]:
    """Decode a Google/OSRM encoded polyline into coordinates."""
    coordinates: list[Coordinates] = []
    index = 0
    lat = 0
    lng = 0

    def read_delta() -> int:
        nonlocal index
        result = 0
        for shift in range(0, 35, 5):
            if index >= len(encoded):
                raise ValueError("Truncated encoded coordinate.")
            value = ord(encoded[index]) - 63
            index += 1
            if not 0 <= value <= 63:
                raise ValueError("Invalid character in encoded polyline.")
            result |= (value & 0x1F) << shift
            if value < 0x20:
                if result > 0xFFFFFFFF:
                    raise ValueError("Encoded coordinate exceeds 32 bits.")
                return ~(result >> 1) if result & 1 else result >> 1
        raise ValueError("Encoded coordinate exceeds 32 bits.")

    while index < len(encoded):
        lat += read_delta()
        lng += read_delta()
        if not (-9000000 <= lat <= 9000000 and -18000000 <= lng <= 18000000):
            raise ValueError("Decoded coordinate is out of range.")
        coordinates.append(Coordinates(latitude=lat / 1e5, longitude=lng / 1e5))

    return coordinates


def cumulative_distances_miles(points: list[Coordinates]) -> list[float]:
    """Return cumulative distance in miles for each point along a path."""
    if not points:
        return []

    cumulative = [0.0]
    total = 0.0
    for idx in range(1, len(points)):
        total += haversine_miles(points[idx - 1], points[idx])
        cumulative.append(total)
    return cumulative


def project_to_polyline(
    point: Coordinates, polyline: list[Coordinates],
) -> tuple[float, int, float]:
    """Return approximate distance, segment index, and fraction along that segment.

    Use a local equirectangular projection for each segment, then measure the
    distance to the projected point with haversine. This is an approximation
    intended for the short segments of a road route, not transcontinental arcs.
    """
    if not polyline:
        return float("inf"), 0, 0.0
    best = (haversine_miles(point, polyline[0]), 0, 0.0)
    for index, (start, finish) in enumerate(pairwise(polyline)):
        scale = math.cos(math.radians((start.latitude + finish.latitude) / 2))
        longitude_delta = (finish.longitude - start.longitude + 180) % 360 - 180
        x = longitude_delta * scale
        y = finish.latitude - start.latitude
        point_x = ((point.longitude - start.longitude + 180) % 360 - 180) * scale
        point_y = point.latitude - start.latitude
        length_squared = x * x + y * y
        fraction = (
            max(0.0, min(1.0, (point_x * x + point_y * y) / length_squared))
            if length_squared else 0.0
        )
        projected = Coordinates(
            latitude=start.latitude + y * fraction,
            longitude=(start.longitude + longitude_delta * fraction + 180) % 360 - 180,
        )
        distance = haversine_miles(point, projected)
        if distance < best[0]:
            best = distance, index, fraction
    return best


def distance_to_polyline_miles(point: Coordinates, polyline: list[Coordinates]) -> float:
    """Approximate minimum distance to the route segments, in miles."""
    return project_to_polyline(point, polyline)[0]


def sample_polyline(
    polyline: list[Coordinates],
    cumulative_miles: list[float],
    *,
    max_points: int = 120,
) -> tuple[list[Coordinates], list[float]]:
    """Downsample a polyline while preserving route shape."""
    if len(polyline) <= max_points:
        return polyline, cumulative_miles

    total_distance = cumulative_miles[-1]
    if total_distance == 0:
        return [polyline[0]], [0.0]

    targets = [total_distance * idx / (max_points - 1) for idx in range(max_points)]
    sampled_points: list[Coordinates] = []
    sampled_miles: list[float] = []

    for target in targets:
        point = interpolate_along_polyline(polyline, cumulative_miles, target)
        sampled_points.append(point)
        sampled_miles.append(target)

    return sampled_points, sampled_miles


def interpolate_along_polyline(
    polyline: list[Coordinates],
    cumulative_miles: list[float],
    target_miles: float,
) -> Coordinates:
    """Return coordinates at a given distance along the polyline."""
    if target_miles <= 0:
        return polyline[0]

    for idx in range(1, len(polyline)):
        if cumulative_miles[idx] >= target_miles:
            prev_dist = cumulative_miles[idx - 1]
            segment_length = cumulative_miles[idx] - prev_dist
            if segment_length == 0:
                return polyline[idx]
            ratio = (target_miles - prev_dist) / segment_length
            prev = polyline[idx - 1]
            curr = polyline[idx]
            return Coordinates(
                latitude=prev.latitude + (curr.latitude - prev.latitude) * ratio,
                longitude=prev.longitude + (curr.longitude - prev.longitude) * ratio,
            )

    return polyline[-1]
