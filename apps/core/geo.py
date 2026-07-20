"""Geospatial utility functions."""

from __future__ import annotations

import math

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

    while index < len(encoded):
        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        delta_lat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += delta_lat

        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        delta_lng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += delta_lng

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


def distance_to_polyline_miles(point: Coordinates, polyline: list[Coordinates]) -> float:
    """Approximate minimum distance from a point to a polyline in miles."""
    if not polyline:
        return float("inf")

    min_distance = float("inf")
    for poly_point in polyline:
        min_distance = min(min_distance, haversine_miles(point, poly_point))
    return min_distance


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
