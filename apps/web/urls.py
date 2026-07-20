"""Web UI URLs."""

from django.urls import path

from apps.web.views import RoutePlannerView

urlpatterns = [
    path("", RoutePlannerView.as_view(), name="route-planner"),
]
