"""Web UI views."""

from django.conf import settings
from django.views.generic import TemplateView


class RoutePlannerView(TemplateView):
    template_name = "web/planner.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "vehicle_range_miles": settings.VEHICLE_RANGE_MILES,
                "vehicle_mpg": settings.VEHICLE_MPG,
            }
        )
        return context
