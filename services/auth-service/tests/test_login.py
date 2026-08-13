import pytest
from django.conf import settings
from django.test import Client
import json


def _post(url, data):
    client = Client()
    return client.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
    )


@pytest.mark.django_db
def test_admin_login_success(admin_user):
    resp = _post("/api/auth/login/", {"email": "admin@test.com", "password": "Admin@pass1", "role": "admin"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "access_token" in data["data"]
    assert "refresh_token" in data["data"]
    assert data["data"]["user"]["role"] == "admin"


@pytest.mark.django_db
def test_student_login_success(student_user):
    resp = _post("/api/auth/login/", {"student_id": "S001", "password": settings.STUDENT_DEFAULT_PASSWORD, "role": "student"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "access_token" in data["data"]
    assert data["data"]["user"]["student_id"] == "S001"


@pytest.mark.django_db
def test_super_admin_login_success(super_admin_user):
    resp = _post("/api/auth/login/", {"email": "superadmin@test.com", "password": "Super@pass1", "role": "super_admin"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["user"]["role"] == "super_admin"


@pytest.mark.django_db
def test_wrong_password_returns_401(admin_user):
    resp = _post("/api/auth/login/", {"email": "admin@test.com", "password": "wrongpass", "role": "admin"})
    assert resp.status_code == 401
    assert resp.json()["success"] is False


@pytest.mark.django_db
def test_unknown_email_returns_401():
    resp = _post("/api/auth/login/", {"email": "nobody@test.com", "password": "pass", "role": "admin"})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_missing_password_returns_400(admin_user):
    resp = _post("/api/auth/login/", {"email": "admin@test.com", "role": "admin"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_inactive_user_returns_403(db):
    import uuid
    from django.contrib.auth import get_user_model
    User = get_user_model()
    User.objects.create_user(
        email="inactive@test.com", password="pass123", role="admin",
        is_active=False, institution_id=uuid.uuid4(),
    )
    resp = _post("/api/auth/login/", {"email": "inactive@test.com", "password": "pass123", "role": "admin"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_role_mismatch_returns_401(admin_user):
    """Admin credentials on student role must return 401."""
    resp = _post("/api/auth/login/", {"student_id": "admin@test.com", "password": "Admin@pass1", "role": "student"})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_admin_login_case_insensitive_email(admin_user):
    """Email lookup should be case-insensitive."""
    resp = _post("/api/auth/login/", {"email": "ADMIN@TEST.COM", "password": "Admin@pass1", "role": "admin"})
    assert resp.status_code == 200


@pytest.mark.django_db
def test_access_token_has_role_claim(admin_user):
    import base64, json as _json
    resp = _post("/api/auth/login/", {"email": "admin@test.com", "password": "Admin@pass1", "role": "admin"})
    token = resp.json()["data"]["access_token"]
    # Decode payload (without signature verification — just inspecting claims)
    payload_b64 = token.split(".")[1]
    padding = "=" * (4 - len(payload_b64) % 4)
    payload = _json.loads(base64.b64decode(payload_b64 + padding))
    assert payload["role"] == "admin"
