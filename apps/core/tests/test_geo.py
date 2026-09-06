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
