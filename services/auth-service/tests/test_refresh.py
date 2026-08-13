import pytest
import json
from django.test import Client


def _login(email, password, role):
    client = Client()
    resp = client.post(
        "/api/auth/login/",
        data=json.dumps({"email": email, "password": password, "role": role}),
        content_type="application/json",
    )
    return resp.json()["data"]


@pytest.mark.django_db
def test_token_refresh_returns_new_access(admin_user):
    tokens = _login("admin@test.com", "Admin@pass1", "admin")
    client = Client()
    resp = client.post(
        "/api/auth/token/refresh/",
        data=json.dumps({"refresh": tokens["refresh_token"]}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    new_data = resp.json()
    assert "access" in new_data


@pytest.mark.django_db
def test_invalid_refresh_token_returns_401():
    client = Client()
    resp = client.post(
        "/api/auth/token/refresh/",
        data=json.dumps({"refresh": "notavalidtoken"}),
        content_type="application/json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_blacklisted_refresh_returns_401(admin_user):
    tokens = _login("admin@test.com", "Admin@pass1", "admin")
    # Blacklist the refresh token via logout
    client = Client()
    client.post(
        "/api/auth/logout/",
        data=json.dumps({"refresh_token": tokens["refresh_token"]}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}",
    )
    # Try to refresh with blacklisted token
    resp = client.post(
        "/api/auth/token/refresh/",
        data=json.dumps({"refresh": tokens["refresh_token"]}),
        content_type="application/json",
    )
    assert resp.status_code == 401
