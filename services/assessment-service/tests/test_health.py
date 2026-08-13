import pytest


@pytest.mark.django_db
class TestHealth:
    def test_health_returns_200(self, anon_client):
        resp = anon_client.get("/api/assessments/health/")
        assert resp.status_code == 200

    def test_health_service_name(self, anon_client):
        resp = anon_client.get("/api/assessments/health/")
        assert resp.json()["data"]["service"] == "assessment-service"

    def test_health_no_auth_required(self, anon_client):
        resp = anon_client.get("/api/assessments/health/")
        assert resp.status_code != 401
