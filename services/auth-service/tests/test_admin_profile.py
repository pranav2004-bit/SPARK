"""
Tests for Admin self-service profile endpoints and Admin-account CRUD
mechanics (fetch/edit/delete/reset-password and their edge cases —
deleted/deactivated/reactivated admin login behavior, list reflecting a
name update, etc).

Endpoints covered:
  GET  /api/auth/me/                              — admin fetches own profile
  PATCH /api/auth/me/                             — admin updates own name
  POST /api/auth/me/change-password/              — admin changes own password

  GET   /api/auth/admins/<pk>/                    — fetch single admin (Super Admin, IT)
  PATCH /api/auth/admins/<pk>/                    — edit name / is_active (IT only, 2026-08-19)
  DELETE /api/auth/admins/<pk>/                   — delete admin (IT only, 2026-08-19)
  POST  /api/auth/admins/<pk>/reset-default-password/ — reset to spark@123 (IT only, 2026-08-19)

  Login now returns id + name for admin role.

Access note (2026-08-19): Admin-account writes moved to IT-exclusive (see
test_admin_management.py for the full permission-boundary coverage —
super_admin-forbidden / it-allowed on every endpoint). The tests below use
IT as the actor to create/edit/delete fixture data, since that mechanic
(not "who is allowed to call it") is what each test is actually checking.

Access note (2026-08-20): /auth/me/ and /auth/me/change-password/ (self-
service profile, distinct from the admin-*roster* management above) were
opened to Super Admin — previously Admin-only, now the same "My Profile"
capability Admin already had.
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


def _create_admin_via_api(actor_token, email, name=""):
    """actor_token must belong to IT — the only role that can create admin
    accounts since 2026-08-19 (see test_admin_management.py)."""
    resp = _post(actor_token, f"{BASE}/admins/", {"email": email, "name": name})
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
def test_get_self_profile_as_super_admin(super_admin_user):
    """Opened to Super Admin 2026-08-20, mirroring Admin's self-service profile."""
    token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _get(token, f"{BASE}/me/")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["email"] == "superadmin@test.com"
    assert "id" in data
    assert "name" in data
    assert "is_active" in data


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
def test_super_admin_can_update_own_name(super_admin_user):
    """Opened to Super Admin 2026-08-20, mirroring Admin's self-service profile."""
    token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _patch(token, f"{BASE}/me/", {"name": "Dr. Updated"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Dr. Updated"
    super_admin_user.refresh_from_db()
    assert super_admin_user.name == "Dr. Updated"


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
def test_super_admin_change_password_success(super_admin_user):
    """Opened to Super Admin 2026-08-20, mirroring Admin's self-service profile."""
    token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/me/change-password/", {
        "current_password": "Super@pass1",
        "new_password": "NewSecure@99",
        "confirm_password": "NewSecure@99",
    })
    assert resp.status_code == 200
    super_admin_user.refresh_from_db()
    assert super_admin_user.check_password("NewSecure@99")


# ── GET /auth/admins/<pk>/ — Super Admin and IT can both read ────────────────

@pytest.mark.django_db
def test_super_admin_can_fetch_single_admin(super_admin_user, it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    created = _create_admin_via_api(it_token, "fetch@test.com", "Fetched")

    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _get(sa_token, f"{BASE}/admins/{created['id']}/")
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "fetch@test.com"


@pytest.mark.django_db
def test_fetch_nonexistent_admin_returns_404(super_admin_user):
    sa_token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _get(sa_token, f"{BASE}/admins/{uuid.uuid4()}/")
    assert resp.status_code == 404


# ── PATCH /auth/admins/<pk>/ — name update (IT-exclusive, 2026-08-19) ────────

@pytest.mark.django_db
def test_it_can_edit_admin_name(it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    created = _create_admin_via_api(it_token, "editname@test.com", "OldName")
    resp = _patch(it_token, f"{BASE}/admins/{created['id']}/", {"name": "NewName"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "NewName"


@pytest.mark.django_db
def test_it_can_clear_admin_name(it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    created = _create_admin_via_api(it_token, "clearname@test.com", "HasName")
    resp = _patch(it_token, f"{BASE}/admins/{created['id']}/", {"name": ""})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == ""


@pytest.mark.django_db
def test_it_can_patch_is_active(it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    created = _create_admin_via_api(it_token, "toggleactive@test.com")
    resp = _patch(it_token, f"{BASE}/admins/{created['id']}/", {"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["data"]["is_active"] is False


@pytest.mark.django_db
def test_it_patch_name_and_active_together(it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    created = _create_admin_via_api(it_token, "both@test.com", "Before")
    resp = _patch(it_token, f"{BASE}/admins/{created['id']}/", {"name": "After", "is_active": False})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "After"
    assert data["is_active"] is False


@pytest.mark.django_db
def test_patch_admin_empty_body_returns_400(it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    created = _create_admin_via_api(it_token, "emptypatch@test.com")
    resp = _patch(it_token, f"{BASE}/admins/{created['id']}/", {})
    assert resp.status_code == 400


# ── DELETE /auth/admins/<pk>/ — IT-exclusive (2026-08-19) ─────────────────────

@pytest.mark.django_db
def test_it_can_delete_admin(it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    created = _create_admin_via_api(it_token, "willdelete@test.com")
    resp = _delete(it_token, f"{BASE}/admins/{created['id']}/")
    assert resp.status_code == 200
    assert not User.objects.filter(email="willdelete@test.com").exists()


@pytest.mark.django_db
def test_delete_nonexistent_admin_returns_404(it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    resp = _delete(it_token, f"{BASE}/admins/{uuid.uuid4()}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_delete_blocked_for_regular_admin(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _delete(token, f"{BASE}/admins/{admin_user.id}/")
    assert resp.status_code == 403


# ── POST /auth/admins/<pk>/reset-default-password/ — IT-exclusive ────────────
# (2026-08-19)

@pytest.mark.django_db
def test_reset_default_password_sets_spark123(it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    created = _create_admin_via_api(it_token, "resetdefault@test.com")

    # Change it first
    admin = User.objects.get(email="resetdefault@test.com")
    admin.set_password("SomeOtherPass@1")
    admin.save(update_fields=["password"])

    resp = _post(it_token, f"{BASE}/admins/{created['id']}/reset-default-password/")
    assert resp.status_code == 200

    admin.refresh_from_db()
    assert admin.check_password(settings.ADMIN_DEFAULT_PASSWORD)


@pytest.mark.django_db
def test_reset_default_password_nonexistent_returns_404(it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    resp = _post(it_token, f"{BASE}/admins/{uuid.uuid4()}/reset-default-password/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_reset_default_password_blocked_for_regular_admin(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/admins/{admin_user.id}/reset-default-password/")
    assert resp.status_code == 403


# ── Edge cases ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_deleted_admin_cannot_login(it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    _create_admin_via_api(it_token, "gone@test.com")
    admin = User.objects.get(email="gone@test.com")
    _delete(it_token, f"{BASE}/admins/{admin.id}/")

    login_resp = _post(None, f"{BASE}/login/", {"email": "gone@test.com", "password": settings.ADMIN_DEFAULT_PASSWORD, "role": "admin"})
    assert login_resp.status_code == 401


@pytest.mark.django_db
def test_deactivated_admin_cannot_login(it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    created = _create_admin_via_api(it_token, "inactive@test.com")
    _patch(it_token, f"{BASE}/admins/{created['id']}/", {"is_active": False})

    login_resp = _post(None, f"{BASE}/login/", {"email": "inactive@test.com", "password": settings.ADMIN_DEFAULT_PASSWORD, "role": "admin"})
    assert login_resp.status_code == 403


@pytest.mark.django_db
def test_reactivated_admin_can_login(it_user):
    it_token = _login("it@test.com", "It@pass123", "it")
    created = _create_admin_via_api(it_token, "reactivate@test.com")
    _patch(it_token, f"{BASE}/admins/{created['id']}/", {"is_active": False})
    _patch(it_token, f"{BASE}/admins/{created['id']}/", {"is_active": True})

    login_resp = _post(None, f"{BASE}/login/", {"email": "reactivate@test.com", "password": settings.ADMIN_DEFAULT_PASSWORD, "role": "admin"})
    assert login_resp.status_code == 200


@pytest.mark.django_db
def test_name_update_reflected_in_list(it_user):
    """After editing a name, the list endpoint returns the new name."""
    it_token = _login("it@test.com", "It@pass123", "it")
    created = _create_admin_via_api(it_token, "listreflect@test.com", "Before")
    _patch(it_token, f"{BASE}/admins/{created['id']}/", {"name": "After"})

    list_resp = _get(it_token, f"{BASE}/admins/")
    names = [a["name"] for a in list_resp.json()["data"]]
    assert "After" in names
    assert "Before" not in names
