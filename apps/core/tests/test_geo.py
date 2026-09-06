"""Geospatial encoding regression tests."""

import pytest

from apps.core.constants import Coordinates
from apps.core.geo import decode_polyline


def test_decode_reference_polyline():
    # Reference example: developers.google.com/maps/documentation/utilities/polylinealgorithm
    assert decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == [
        Coordinates(38.5, -120.2), Coordinates(40.7, -120.95), Coordinates(43.252, -126.453),
    ]


def test_decode_empty_and_duplicate_points():
    assert decode_polyline("") == []
    assert decode_polyline("????") == [Coordinates(0, 0), Coordinates(0, 0)]


@pytest.mark.parametrize("encoded", ["?", "_", "?_", "_p~iF~ps|U_"])
def test_truncated_coordinate(encoded):
    with pytest.raises(ValueError, match="Truncated"):
        decode_polyline(encoded)


@pytest.mark.parametrize("encoded", ["!!", " ?", "?\n", "\x7f?", "é?"])
def test_invalid_character(encoded):
    with pytest.raises(ValueError, match="Invalid character"):
        decode_polyline(encoded)


@pytest.mark.parametrize("encoded", ["________?", "~~~~~~F?"])
def test_oversized_coordinate(encoded):
    with pytest.raises(ValueError, match="32 bits"):
        decode_polyline(encoded)


def test_out_of_range_coordinate():
    # Latitude 100 degrees at E5 precision, longitude zero.
    with pytest.raises(ValueError, match="out of range"):
        decode_polyline("_gjaR?")


@pytest.mark.parametrize('route,point,segment,fraction', [
    ([Coordinates(30, -100), Coordinates(30, -98)], Coordinates(30, -99), 0, 0.5),
    ([Coordinates(30, -100), Coordinates(32, -100)], Coordinates(31, -100), 0, 0.5),
    ([Coordinates(30, -100), Coordinates(30, -100), Coordinates(30, -98)],
     Coordinates(30, -99), 1, 0.5),
    ([Coordinates(0, 179), Coordinates(0, -179)], Coordinates(0, 180), 0, 0.5),
])
def test_points_between_route_vertices(route, point, segment, fraction):
    from apps.core.geo import project_to_polyline

    distance, index, ratio = project_to_polyline(point, route)
    assert distance == pytest.approx(0, abs=1e-8)
    assert index == segment
    assert ratio == pytest.approx(fraction)


def test_segment_projection_clamps_to_endpoints():
    from apps.core.geo import haversine_miles, project_to_polyline

    route = [Coordinates(30, -100), Coordinates(30, -98)]
    point = Coordinates(30, -97)
    distance, index, fraction = project_to_polyline(point, route)
    assert index == 0
    assert fraction == 1
    assert distance == pytest.approx(haversine_miles(point, route[-1]))


def test_projection_handles_empty_and_single_point_routes():
    from apps.core.geo import haversine_miles, project_to_polyline

    point = Coordinates(30, -99)
    assert project_to_polyline(point, [point]) == (0, 0, 0)
    assert project_to_polyline(point, [Coordinates(31, -99)])[0] == pytest.approx(
        haversine_miles(point, Coordinates(31, -99))
    )
    assert project_to_polyline(point, [])[0] == float('inf')
