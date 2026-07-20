"""Route planning API views."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.routing.serializers import RoutePlanRequestSerializer
from apps.routing.services import RoutePlannerService


class RoutePlanView(APIView):
    """Plan a US driving route with cost-optimal fuel stops."""

    def post(self, request):
        serializer = RoutePlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        planner = RoutePlannerService()
        result = planner.plan_route(
            start=serializer.validated_data["start"],
            finish=serializer.validated_data["finish"],
        )

        payload = {
            "start": {
                "label": result.start.label,
                "location": result.start.coordinates.as_geojson_point(),
            },
            "finish": {
                "label": result.finish.label,
                "location": result.finish.coordinates.as_geojson_point(),
            },
            "route": result.route_geometry,
            "map": result.map_geojson,
            "distance_miles": result.distance_miles,
            "duration_seconds": result.duration_seconds,
            "fuel_stops": result.fuel_stops,
            "total_fuel_cost_usd": float(result.total_fuel_cost_usd),
            "total_gallons_consumed": float(result.total_gallons_consumed),
            "vehicle": {
                "range_miles": result.vehicle_range_miles,
                "mpg": result.vehicle_mpg,
            },
            "request_id": getattr(request, "request_id", None),
        }
        return Response(payload, status=status.HTTP_200_OK)
