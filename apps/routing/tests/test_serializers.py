"""Request validation preserves normalized coordinate values and error location."""

import pytest

from apps.routing.serializers import RoutePlanRequestSerializer


@pytest.mark.parametrize("field", ["start", "finish"])
def test_nested_coordinate_values_are_normalized(field):
    payload = {"start": "Austin, TX", "finish": "Dallas, TX"}
    payload[field] = {"latitude": "30.2672", "longitude": "-97.7431", "label": 123}
    serializer = RoutePlanRequestSerializer(data=payload)
    assert serializer.is_valid(), serializer.errors
    coordinates = serializer.validated_data[field]
    assert coordinates["lat"] == 30.2672
    assert coordinates["lng"] == -97.7431
    assert coordinates["label"] == "123"
    assert payload[field]["latitude"] == "30.2672"


@pytest.mark.parametrize("field", ["start", "finish"])
@pytest.mark.parametrize("coordinates", [
    {"lat": "invalid", "lng": -97},
    {"lat": 30},
    {"lat": 30, "lng": -97, "label": "x" * 256},
])
def test_coordinate_errors_identify_location_field(field, coordinates):
    payload = {"start": "Austin, TX", "finish": "Dallas, TX", field: coordinates}
    serializer = RoutePlanRequestSerializer(data=payload)
    assert not serializer.is_valid()
    assert set(serializer.errors) == {field}


def test_coordinate_alias_precedence_is_preserved():
    serializer = RoutePlanRequestSerializer(data={
        "start": {"lat": 30, "latitude": 31, "lng": -97, "longitude": -98},
        "finish": "Dallas, TX",
    })
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["start"]["lat"] == 30
    assert serializer.validated_data["start"]["lng"] == -97
