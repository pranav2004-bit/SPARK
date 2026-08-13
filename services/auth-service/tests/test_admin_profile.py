"""
Tests for Admin self-service profile endpoints and enhanced Super Admin CRUD.

Endpoints covered:
  GET  /api/auth/me/                              — admin fetches own profile
  PATCH /api/auth/me/                             — admin updates own name
  POST /api/auth/me/change-password/              — admin changes own password

  GET   /api/auth/admins/<pk>/                    — super admin fetches single admin
  PATCH /api/auth/admins/<pk>/                    — super admin edits name / is_active
  DELETE /api/auth/admins/<pk>/                   — super admin deletes admin
  POST  /api/auth/admins/<pk>/reset-default-password/ — super admin resets to spark@123

  Login now returns id + name for admin role.
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

def _post(token_or_none, url, data=None):
    c = Client()
    kwargs = dict(
        data=json.dumps(data or {}),
        content_type="application/json",
    )
    if token_or_none:
        kwargs["HTTP_AUTHORIZATION"] = f"Bearer {token_or_none}"
    return c.post(url, **kwargs)


def _get(token, url):
    return Client().get(
        url,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


def _patch(token, url, data):
    return Client().patch(
        url,
        data=json.dumps(data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


def _delete(token, url):
    return Client().delete(
        url,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )


def _login(email, password, role):
    resp = _post(None, f"{BASE}/login/", {"email": email, "password": password, "role": role})
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["data"]["access_token"]


def _create_admin_via_api(sa_token, email, name=""):
    resp = _post(sa_token, f"{BASE}/admins/", {"email": email, "name": name})
    assert resp.status_code == 201, f"Create admin failed: {resp.json()}"
    return resp.json()["data"]


# ── Login now returns id + name for admin ─────────────────────────────────────

@pytest.mark.django_db
def test_admin_login_returns_id_and_name(admin_user):
    resp = _post(None, f"{BASE}/login/", {"email": "admin@test.com", "password": "Admin@pass1", "role": "admin"})
    assert resp.status_code == 200
    user_data = resp.json()["data"]["user"]
    assert "id" in user_data
    assert "name" in user_data
    assert user_data["role"] == "admin"


@pytest.mark.django_db
def test_super_admin_login_returns_id_and_name(super_admin_user):
    resp = _post(None, f"{BASE}/login/", {"email": "superadmin@test.com", "password": "Super@pass1", "role": "super_admin"})
    assert resp.status_code == 200
    user_data = resp.json()["data"]["user"]
    assert "id" in user_data
    assert "name" in user_data


# ── GET /auth/me/ ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_self_profile_returns_200(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _get(token, f"{BASE}/me/")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["email"] == "admin@test.com"
    assert "id" in data
    assert "name" in data
    assert "is_active" in data


@pytest.mark.django_db
def test_get_self_profile_blocked_for_super_admin(super_admin_user):
    token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _get(token, f"{BASE}/me/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_get_self_profile_blocked_for_unauthenticated():
    resp = Client().get(f"{BASE}/me/", content_type="application/json")
    assert resp.status_code == 401


# ── PATCH /auth/me/ ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_admin_can_update_own_name(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _patch(token, f"{BASE}/me/", {"name": "Dr. Updated"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Dr. Updated"
    admin_user.refresh_from_db()
    assert admin_user.name == "Dr. Updated"


@pytest.mark.django_db
def test_admin_can_clear_own_name(admin_user):
    """Name is optional — clearing it (empty string) must succeed."""
    admin_user.name = "Old Name"
    admin_user.save(update_fields=["name"])
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _patch(token, f"{BASE}/me/", {"name": ""})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == ""


@pytest.mark.django_db
def test_admin_name_is_stripped(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _patch(token, f"{BASE}/me/", {"name": "  Padded Name  "})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Padded Name"


@pytest.mark.django_db
def test_admin_cannot_update_email_via_me(admin_user):
    """Email is immutable — the PATCH endpoint silently ignores the email field."""
    token = _login("admin@test.com", "Admin@pass1", "admin")
    _patch(token, f"{BASE}/me/", {"name": "Same", "email": "hacker@evil.com"})
    admin_user.refresh_from_db()
    assert admin_user.email == "admin@test.com"


@pytest.mark.django_db
def test_patch_me_blocked_for_super_admin(super_admin_user):
    token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _patch(token, f"{BASE}/me/", {"name": "Hack"})
    assert resp.status_code == 403


# ── POST /auth/me/change-password/ ───────────────────────────────────────────

@pytest.mark.django_db
def test_admin_change_password_success(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/me/change-password/", {
        "current_password": "Admin@pass1",
        "new_password": "NewSecure@99",
        "confirm_password": "NewSecure@99",
    })
    assert resp.status_code == 200
    admin_user.refresh_from_db()
    assert admin_user.check_password("NewSecure@99")


@pytest.mark.django_db
def test_admin_change_password_wrong_current(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/me/change-password/", {
        "current_password": "WrongPass!",
        "new_password": "NewSecure@99",
        "confirm_password": "NewSecure@99",
    })
    assert resp.status_code == 400
    assert "incorrect" in resp.json()["message"].lower()


@pytest.mark.django_db
def test_admin_change_password_mismatch_confirm(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/me/change-password/", {
        "current_password": "Admin@pass1",
        "new_password": "NewSecure@99",
        "confirm_password": "DifferentPass@1",
    })
    assert resp.status_code == 400


@pytest.mark.django_db
def test_admin_change_password_too_short(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/me/change-password/", {
        "current_password": "Admin@pass1",
        "new_password": "short",
        "confirm_password": "short",
    })
    assert resp.status_code == 400


@pytest.mark.django_db
def test_admin_change_password_same_as_current(admin_user):
    """New password cannot be the same as the current one."""
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/me/change-password/", {
        "current_password": "Admin@pass1",
        "new_password": "Admin@pass1",
        "confirm_password": "Admin@pass1",
    })
    assert resp.status_code == 400
    assert "different" in resp.json()["message"].lower()


@pytest.mark.django_db
def test_change_password_blocked_for_super_admin(super_admin_user):
    token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/me/change-password/", {
        "current_password": "Super@pass1",
        "new_password": "NewSecure@99",
        "confirm_password": "NewSecure@99",
    })
    assert resp.status_code == 403


# ── GET /auth/admins/<pk>/ ─────────────────────────────────────────────────────

@pytest.mark.django_db
def test_super_admin_can_fetch_single_admin(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    created = _create_admin_via_api(sa_token, "fetch@test.com", "Fetched")
    resp = _get(sa_token, f"{BASE}/admins/{created['id']}/")
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "fetch@test.com"


@pytest.mark.django_db
def test_fetch_nonexistent_admin_returns_404(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _get(sa_token, f"{BASE}/admins/{uuid.uuid4()}/")
    assert resp.status_code == 404


# ── PATCH /auth/admins/<pk>/ — name update ────────────────────────────────────

@pytest.mark.django_db
def test_super_admin_can_edit_admin_name(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    created = _create_admin_via_api(sa_token, "editname@test.com", "OldName")
    resp = _patch(sa_token, f"{BASE}/admins/{created['id']}/", {"name": "NewName"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "NewName"


@pytest.mark.django_db
def test_super_admin_can_clear_admin_name(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    created = _create_admin_via_api(sa_token, "clearname@test.com", "HasName")
    resp = _patch(sa_token, f"{BASE}/admins/{created['id']}/", {"name": ""})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == ""


@pytest.mark.django_db
def test_super_admin_can_patch_is_active(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    created = _create_admin_via_api(sa_token, "toggleactive@test.com")
    resp = _patch(sa_token, f"{BASE}/admins/{created['id']}/", {"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["data"]["is_active"] is False


@pytest.mark.django_db
def test_super_admin_patch_name_and_active_together(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    created = _create_admin_via_api(sa_token, "both@test.com", "Before")
    resp = _patch(sa_token, f"{BASE}/admins/{created['id']}/", {"name": "After", "is_active": False})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "After"
    assert data["is_active"] is False


@pytest.mark.django_db
def test_patch_admin_empty_body_returns_400(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    created = _create_admin_via_api(sa_token, "emptypatch@test.com")
    resp = _patch(sa_token, f"{BASE}/admins/{created['id']}/", {})
    assert resp.status_code == 400


# ── DELETE /auth/admins/<pk>/ ─────────────────────────────────────────────────

@pytest.mark.django_db
def test_super_admin_can_delete_admin(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    created = _create_admin_via_api(sa_token, "willdelete@test.com")
    resp = _delete(sa_token, f"{BASE}/admins/{created['id']}/")
    assert resp.status_code == 200
    assert not User.objects.filter(email="willdelete@test.com").exists()


@pytest.mark.django_db
def test_delete_nonexistent_admin_returns_404(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _delete(sa_token, f"{BASE}/admins/{uuid.uuid4()}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_delete_blocked_for_regular_admin(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _delete(token, f"{BASE}/admins/{admin_user.id}/")
    assert resp.status_code == 403


# ── POST /auth/admins/<pk>/reset-default-password/ ───────────────────────────

@pytest.mark.django_db
def test_reset_default_password_sets_spark123(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    created = _create_admin_via_api(sa_token, "resetdefault@test.com")

    # Change it first
    admin = User.objects.get(email="resetdefault@test.com")
    admin.set_password("SomeOtherPass@1")
    admin.save(update_fields=["password"])

    resp = _post(sa_token, f"{BASE}/admins/{created['id']}/reset-default-password/")
    assert resp.status_code == 200

    admin.refresh_from_db()
    assert admin.check_password(settings.ADMIN_DEFAULT_PASSWORD)


@pytest.mark.django_db
def test_reset_default_password_nonexistent_returns_404(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(sa_token, f"{BASE}/admins/{uuid.uuid4()}/reset-default-password/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_reset_default_password_blocked_for_regular_admin(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/admins/{admin_user.id}/reset-default-password/")
    assert resp.status_code == 403


# ── Edge cases ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_deleted_admin_cannot_login(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    _create_admin_via_api(sa_token, "gone@test.com")
    admin = User.objects.get(email="gone@test.com")
    _delete(sa_token, f"{BASE}/admins/{admin.id}/")

    login_resp = _post(None, f"{BASE}/login/", {"email": "gone@test.com", "password": settings.ADMIN_DEFAULT_PASSWORD, "role": "admin"})
    assert login_resp.status_code == 401


@pytest.mark.django_db
def test_deactivated_admin_cannot_login(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    created = _create_admin_via_api(sa_token, "inactive@test.com")
    _patch(sa_token, f"{BASE}/admins/{created['id']}/", {"is_active": False})

    login_resp = _post(None, f"{BASE}/login/", {"email": "inactive@test.com", "password": settings.ADMIN_DEFAULT_PASSWORD, "role": "admin"})
    assert login_resp.status_code == 403


@pytest.mark.django_db
def test_reactivated_admin_can_login(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    created = _create_admin_via_api(sa_token, "reactivate@test.com")
    _patch(sa_token, f"{BASE}/admins/{created['id']}/", {"is_active": False})
    _patch(sa_token, f"{BASE}/admins/{created['id']}/", {"is_active": True})

    login_resp = _post(None, f"{BASE}/login/", {"email": "reactivate@test.com", "password": settings.ADMIN_DEFAULT_PASSWORD, "role": "admin"})
    assert login_resp.status_code == 200


@pytest.mark.django_db
def test_name_update_reflected_in_list(super_admin_user):
    """After editing a name, the list endpoint returns the new name."""
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    created = _create_admin_via_api(sa_token, "listreflect@test.com", "Before")
    _patch(sa_token, f"{BASE}/admins/{created['id']}/", {"name": "After"})

    list_resp = _get(sa_token, f"{BASE}/admins/")
    names = [a["name"] for a in list_resp.json()["data"]]
    assert "After" in names
    assert "Before" not in names
