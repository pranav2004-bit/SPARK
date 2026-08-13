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


def _post(url, data, access_token=None):
    client = Client()
    headers = {}
    if access_token:
        headers["HTTP_AUTHORIZATION"] = f"Bearer {access_token}"
    return client.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
        **headers,
    )


@pytest.mark.django_db
def test_admin_logout_blacklists_refresh(admin_user):
    tokens = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _post(
        "/api/auth/logout/",
        {"refresh_token": tokens["refresh_token"]},
        access_token=tokens["access_token"],
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.django_db
def test_already_blacklisted_token_returns_400(admin_user):
    tokens = _login("admin@test.com", "Admin@pass1", "admin")
    _post("/api/auth/logout/", {"refresh_token": tokens["refresh_token"]}, tokens["access_token"])
    # Second logout with same token
    resp = _post("/api/auth/logout/", {"refresh_token": tokens["refresh_token"]}, tokens["access_token"])
    assert resp.status_code == 400


@pytest.mark.django_db
def test_logout_without_auth_returns_401(admin_user):
    tokens = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _post("/api/auth/logout/", {"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_logout_missing_refresh_token_returns_400(admin_user):
    tokens = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _post("/api/auth/logout/", {}, tokens["access_token"])
    assert resp.status_code == 400
