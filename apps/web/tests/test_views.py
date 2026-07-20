"""Web UI tests."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_route_planner_page_renders(client):
    response = client.get(reverse("route-planner"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Spotter" in content
    assert "Plan Route" in content
