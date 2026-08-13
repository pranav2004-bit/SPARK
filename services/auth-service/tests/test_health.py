import pytest
from django.test import Client


@pytest.mark.django_db
def test_health_returns_200():
    client = Client()
    resp = client.get("/api/auth/health/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["service"] == "auth-service"
    assert data["data"]["status"] == "ok"


@pytest.mark.django_db
def test_health_db_field_present():
    resp = Client().get("/api/auth/health/")
    assert "db" in resp.json()["data"]


@pytest.mark.django_db
def test_health_no_auth_required():
    """Health endpoint must be public."""
    resp = Client().get("/api/auth/health/")
    assert resp.status_code == 200
