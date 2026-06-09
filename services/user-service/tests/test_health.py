import pytest


@pytest.mark.django_db
class TestHealth:
    def test_health_returns_200(self, anon_client):
        resp = anon_client.get("/api/users/health/")
        assert resp.status_code == 200

    def test_health_has_service_field(self, anon_client):
        resp = anon_client.get("/api/users/health/")
        assert resp.json()["data"]["service"] == "user-service"

    def test_health_has_db_field(self, anon_client):
        resp = anon_client.get("/api/users/health/")
        assert "db" in resp.json()["data"]

    def test_health_no_auth_required(self, anon_client):
        resp = anon_client.get("/api/users/health/")
        assert resp.status_code != 401
