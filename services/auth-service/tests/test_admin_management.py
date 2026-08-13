"""
Tests for Admin Management endpoints (Super Admin only).

Endpoints covered:
  GET  /api/auth/admins/                     — list all admins
  POST /api/auth/admins/                     — create admin (email required, name optional, password auto)
  PATCH /api/auth/admins/<pk>/               — deactivate/reactivate admin
  POST /api/auth/admin-password-reset/       — reset admin password by id
"""

import json
import uuid
import pytest
from django.conf import settings
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()

BASE = "/api/auth"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _login_token(email, password, role):
    """Return a JWT access token for the given credentials."""
    client = Client()
    resp = client.post(
        f"{BASE}/login/",
        data=json.dumps({"email": email, "password": password, "role": role}),
        content_type="application/json",
    )
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["data"]["access_token"]


def _get(token, url):
    c = Client()
    return c.get(url, HTTP_AUTHORIZATION=f"Bearer {token}", content_type="application/json")


def _post(token, url, data):
    c = Client()
    return c.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


def _post_unauthed(url, data):
    c = Client()
    return c.post(url, data=json.dumps(data), content_type="application/json")


def _get_unauthed(url):
    return Client().get(url, content_type="application/json")


def _patch(token, url, data):
    c = Client()
    return c.patch(
        url,
        data=json.dumps(data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


# ── GET /admins/ ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_list_admins_returns_200_for_super_admin(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _get(token, f"{BASE}/admins/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


@pytest.mark.django_db
def test_list_admins_blocked_for_regular_admin(admin_user):
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    resp = _get(token, f"{BASE}/admins/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_list_admins_blocked_for_unauthenticated():
    resp = _get_unauthed(f"{BASE}/admins/")
    assert resp.status_code == 401


# ── POST /admins/ ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_create_admin_with_name_and_email(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/admins/", {"email": "newadmin@test.com", "name": "Alice"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["email"] == "newadmin@test.com"
    assert data["data"]["name"] == "Alice"
    assert data["data"]["is_active"] is True


@pytest.mark.django_db
def test_create_admin_without_name_is_allowed(super_admin_user):
    """Name is optional — creating with only email must succeed."""
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/admins/", {"email": "noname@test.com"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["name"] == ""


@pytest.mark.django_db
def test_create_admin_email_lowercased(super_admin_user):
    """Emails are normalised to lowercase on creation."""
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/admins/", {"email": "UPPER@EXAMPLE.COM", "name": "Bob"})
    assert resp.status_code == 201
    assert resp.json()["data"]["email"] == "upper@example.com"


@pytest.mark.django_db
def test_create_admin_default_password_is_spark(super_admin_user):
    """The created admin must be able to log in with the default password spark@123."""
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    _post(token, f"{BASE}/admins/", {"email": "pwcheck@test.com", "name": "PwCheck"})

    admin = User.objects.get(email="pwcheck@test.com")
    assert admin.check_password(settings.ADMIN_DEFAULT_PASSWORD), f"Default password should be {settings.ADMIN_DEFAULT_PASSWORD}"


@pytest.mark.django_db
def test_create_admin_default_password_allows_login(super_admin_user):
    """Admin created with default password can immediately log in via the login endpoint."""
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    _post(token, f"{BASE}/admins/", {"email": "logincheck@test.com"})

    resp = _post_unauthed(
        f"{BASE}/login/",
        {"email": "logincheck@test.com", "password": settings.ADMIN_DEFAULT_PASSWORD, "role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["user"]["role"] == "admin"


@pytest.mark.django_db
def test_create_admin_duplicate_email_returns_409(super_admin_user):
    """Creating a second account with the same email must return 409."""
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    _post(token, f"{BASE}/admins/", {"email": "dup@test.com", "name": "First"})
    resp = _post(token, f"{BASE}/admins/", {"email": "dup@test.com", "name": "Second"})
    assert resp.status_code == 409
    assert "already exists" in resp.json()["message"].lower()


@pytest.mark.django_db
def test_create_admin_duplicate_email_case_insensitive(super_admin_user):
    """Email uniqueness check is case-insensitive because emails are normalised."""
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    _post(token, f"{BASE}/admins/", {"email": "case@test.com"})
    resp = _post(token, f"{BASE}/admins/", {"email": "CASE@TEST.COM"})
    assert resp.status_code == 409


@pytest.mark.django_db
def test_create_admin_missing_email_returns_400(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/admins/", {"name": "NoEmail"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_admin_invalid_email_returns_400(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/admins/", {"email": "not-an-email"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_admin_blocked_for_regular_admin(admin_user):
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/admins/", {"email": "blocked@test.com"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_admin_blocked_for_unauthenticated():
    resp = _post_unauthed(f"{BASE}/admins/", {"email": "anon@test.com"})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_create_admin_no_department_stored(super_admin_user):
    """Department must be empty string — it is no longer accepted as input."""
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    _post(token, f"{BASE}/admins/", {"email": "nodept@test.com"})
    admin = User.objects.get(email="nodept@test.com")
    assert admin.department == ""


@pytest.mark.django_db
def test_create_admin_auto_stamps_institution_id(super_admin_user):
    """
    Faculty created by a super admin must inherit the super admin's institution_id.
    The Super Admin form sends only name + email — no UUID exposed anywhere in the UI.
    """
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/admins/", {
        "email": "faculty@anits.edu",
        "name": "Dr. Rajan",
    })
    assert resp.status_code == 201
    admin = User.objects.get(email="faculty@anits.edu")
    assert admin.institution_id == super_admin_user.institution_id


@pytest.mark.django_db
def test_create_admin_institution_id_not_overridable_from_request(super_admin_user):
    """
    institution_id sent in the POST body is silently ignored — the backend always
    stamps from the super admin's own institution_id, so an arbitrary UUID in the
    request must NOT be stored on the created admin record.
    """
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    arbitrary_uuid = str(uuid.uuid4())
    resp = _post(token, f"{BASE}/admins/", {
        "email": "override@test.com",
        "institution_id": arbitrary_uuid,   # should be ignored by the backend
    })
    assert resp.status_code == 201
    admin = User.objects.get(email="override@test.com")
    assert admin.institution_id == super_admin_user.institution_id
    assert str(admin.institution_id) != arbitrary_uuid


@pytest.mark.django_db
def test_create_admin_name_optional_institution_still_stamped(super_admin_user):
    """Creating an admin with only email (no name) still gets institution_id stamped from super admin."""
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/admins/", {"email": "noname@test.com"})
    assert resp.status_code == 201
    admin = User.objects.get(email="noname@test.com")
    assert admin.name == ""
    assert admin.institution_id == super_admin_user.institution_id


# ── PATCH /admins/<pk>/ ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_deactivate_admin(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    _post(token, f"{BASE}/admins/", {"email": "deact@test.com"})
    admin = User.objects.get(email="deact@test.com")

    resp = _patch(token, f"{BASE}/admins/{admin.id}/", {"is_active": False})
    assert resp.status_code == 200
    admin.refresh_from_db()
    assert admin.is_active is False


@pytest.mark.django_db
def test_reactivate_admin(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    _post(token, f"{BASE}/admins/", {"email": "react@test.com"})
    admin = User.objects.get(email="react@test.com")
    admin.is_active = False
    admin.save(update_fields=["is_active"])

    resp = _patch(token, f"{BASE}/admins/{admin.id}/", {"is_active": True})
    assert resp.status_code == 200
    admin.refresh_from_db()
    assert admin.is_active is True


@pytest.mark.django_db
def test_deactivate_nonexistent_admin_returns_404(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _patch(token, f"{BASE}/admins/{uuid.uuid4()}/", {"is_active": False})
    assert resp.status_code == 404


# ── POST /admin-password-reset/ ───────────────────────────────────────────────

@pytest.mark.django_db
def test_reset_admin_password_by_id(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    _post(token, f"{BASE}/admins/", {"email": "resetme@test.com"})
    admin = User.objects.get(email="resetme@test.com")

    resp = _post(token, f"{BASE}/admin-password-reset/", {
        "admin_id": str(admin.id),
        "new_password": "NewPass@99",
    })
    assert resp.status_code == 200
    admin.refresh_from_db()
    assert admin.check_password("NewPass@99")


@pytest.mark.django_db
def test_reset_admin_password_short_password_returns_400(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    _post(token, f"{BASE}/admins/", {"email": "shortpw@test.com"})
    admin = User.objects.get(email="shortpw@test.com")

    resp = _post(token, f"{BASE}/admin-password-reset/", {
        "admin_id": str(admin.id),
        "new_password": "short",
    })
    assert resp.status_code == 400


@pytest.mark.django_db
def test_reset_admin_password_nonexistent_id_returns_404(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/admin-password-reset/", {
        "admin_id": str(uuid.uuid4()),
        "new_password": "ValidPass@1",
    })
    assert resp.status_code == 404
