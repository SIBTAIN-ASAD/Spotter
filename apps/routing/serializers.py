"""Route planning API serializers."""

from rest_framework import serializers


class CoordinateInputSerializer(serializers.Serializer):
    lat = serializers.FloatField(required=False)
    latitude = serializers.FloatField(required=False)
    lng = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)
    label = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate(self, attrs):
        latitude = attrs.get("lat", attrs.get("latitude"))
        longitude = attrs.get("lng", attrs.get("longitude"))
        if latitude is None or longitude is None:
            raise serializers.ValidationError(
                "Coordinate objects must include lat/latitude and lng/longitude."
            )
        attrs["lat"] = latitude
        attrs["lng"] = longitude
        return attrs


class RoutePlanRequestSerializer(serializers.Serializer):
    start = serializers.JSONField()
    finish = serializers.JSONField()

    def validate(self, attrs):
        for field_name in ("start", "finish"):
            value = attrs[field_name]
            if isinstance(value, str):
                if not value.strip():
                    raise serializers.ValidationError({field_name: "This field cannot be blank."})
                continue
            if isinstance(value, dict):
                nested = CoordinateInputSerializer(data=value)
                nested.is_valid(raise_exception=True)
                continue
            raise serializers.ValidationError(
                {field_name: "Must be a US address string or coordinate object."}
            )
        return attrs
