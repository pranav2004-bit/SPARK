"""
Tests for Super Admin account management endpoints.

Endpoints covered:
  GET    /api/auth/super-admins/                              — list all super admins
  POST   /api/auth/super-admins/                              — create super admin (email required, name optional, password auto)
  GET    /api/auth/super-admins/<pk>/                         — retrieve one super admin
  PATCH  /api/auth/super-admins/<pk>/                         — edit name / deactivate / reactivate super admin
  DELETE /api/auth/super-admins/<pk>/                         — permanently delete super admin
  POST   /api/auth/super-admins/<pk>/reset-default-password/  — reset super admin password to default

Access (2026-08-20): IT-exclusive across the board — added the same day IT
became the platform's bootstrapped root (see create_default_it), replacing
the old Super-Admin-only "IT Accounts" management. Unlike the Admin
management endpoints, there is no read-only remnant for Super Admin here:
a Super Admin has zero access to this resource, not even GET — matching how
an Admin has zero visibility into other Admin accounts today.
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


def _delete(token, url):
    c = Client()
    return c.delete(url, HTTP_AUTHORIZATION=f"Bearer {token}", content_type="application/json")


def _make_super_admin(email, name="", institution_id=None):
    """Create a super_admin User directly via the ORM — used to seed data in
    tests where the API's own create endpoint is not what's under test."""
    return User.objects.create_user(
        email=email,
        password=settings.SUPERADMIN_DEFAULT_PASSWORD,
        role="super_admin",
        name=name,
        institution_id=institution_id,
    )


# ── GET /super-admins/ — IT only, no unauthenticated/anonymous access ────────

@pytest.mark.django_db
def test_list_super_admins_returns_200_for_it(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _get(token, f"{BASE}/super-admins/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


@pytest.mark.django_db
def test_list_super_admins_blocked_for_super_admin_itself(super_admin_user):
    """Zero access — a super_admin cannot see the super-admin roster at all,
    same as an admin cannot see other admins."""
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _get(token, f"{BASE}/super-admins/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_list_super_admins_blocked_for_regular_admin(admin_user):
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    resp = _get(token, f"{BASE}/super-admins/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_list_super_admins_blocked_for_unauthenticated():
    resp = _get_unauthed(f"{BASE}/super-admins/")
    assert resp.status_code == 401


# ── POST /super-admins/ — IT only ─────────────────────────────────────────────

@pytest.mark.django_db
def test_create_super_admin_with_name_and_email(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/", {"email": "newsa@test.com", "name": "Alice"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["email"] == "newsa@test.com"
    assert data["data"]["name"] == "Alice"
    assert data["data"]["is_active"] is True


@pytest.mark.django_db
def test_create_super_admin_without_name_is_allowed(it_user):
    """Name is optional — creating with only email must succeed."""
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/", {"email": "noname@test.com"})
    assert resp.status_code == 201
    assert resp.json()["data"]["name"] == ""


@pytest.mark.django_db
def test_create_super_admin_with_department(it_user):
    """The IT portal's create form maps the new super admin to a department
    (2026-08-20) — must persist and round-trip in the response."""
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/", {"email": "dept@test.com", "name": "Dept SA", "department": "CSE"})
    assert resp.status_code == 201
    assert resp.json()["data"]["department"] == "CSE"
    sa = User.objects.get(email="dept@test.com")
    assert sa.department == "CSE"


@pytest.mark.django_db
def test_create_super_admin_without_department_defaults_to_blank(it_user):
    """department is optional at the API layer — omitting it must not fail."""
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/", {"email": "nodept@test.com"})
    assert resp.status_code == 201
    assert resp.json()["data"]["department"] == ""


@pytest.mark.django_db
def test_create_super_admin_email_lowercased(it_user):
    """Emails are normalised to lowercase on creation."""
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/", {"email": "UPPER@EXAMPLE.COM", "name": "Bob"})
    assert resp.status_code == 201
    assert resp.json()["data"]["email"] == "upper@example.com"


@pytest.mark.django_db
def test_create_super_admin_default_password_allows_login(it_user):
    """Super admin created with default password can immediately log in."""
    token = _login_token("it@test.com", "It@pass123", "it")
    _post(token, f"{BASE}/super-admins/", {"email": "logincheck@test.com"})

    resp = _post_unauthed(
        f"{BASE}/login/",
        {"email": "logincheck@test.com", "password": settings.SUPERADMIN_DEFAULT_PASSWORD, "role": "super_admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["user"]["role"] == "super_admin"
    assert resp.json()["data"]["user"]["force_password_change"] is True


@pytest.mark.django_db
def test_create_super_admin_duplicate_email_returns_409(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    _post(token, f"{BASE}/super-admins/", {"email": "dup@test.com", "name": "First"})
    resp = _post(token, f"{BASE}/super-admins/", {"email": "dup@test.com", "name": "Second"})
    assert resp.status_code == 409
    assert "already exists" in resp.json()["message"].lower()


@pytest.mark.django_db
def test_create_super_admin_missing_email_returns_400(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/", {"name": "NoEmail"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_super_admin_invalid_email_returns_400(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/", {"email": "not-an-email"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_super_admin_auto_stamps_institution_id(it_user):
    """A super admin created by IT must inherit IT's own institution_id — the
    create form sends only name + email, no UUID exposed anywhere in the UI."""
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/", {"email": "sa@anits.edu", "name": "Dr. Rajan"})
    assert resp.status_code == 201
    sa = User.objects.get(email="sa@anits.edu")
    assert sa.institution_id == it_user.institution_id


@pytest.mark.django_db
def test_create_super_admin_institution_id_not_overridable_from_request(it_user):
    """institution_id sent in the POST body is silently ignored — the backend
    always stamps from the creator's own institution_id."""
    token = _login_token("it@test.com", "It@pass123", "it")
    arbitrary_uuid = str(uuid.uuid4())
    resp = _post(token, f"{BASE}/super-admins/", {
        "email": "override@test.com",
        "institution_id": arbitrary_uuid,
    })
    assert resp.status_code == 201
    sa = User.objects.get(email="override@test.com")
    assert sa.institution_id == it_user.institution_id
    assert str(sa.institution_id) != arbitrary_uuid


@pytest.mark.django_db
def test_create_super_admin_forbidden_for_super_admin_itself(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/super-admins/", {"email": "shouldfail@test.com"})
    assert resp.status_code == 403
    assert not User.objects.filter(email="shouldfail@test.com").exists()


@pytest.mark.django_db
def test_create_super_admin_blocked_for_regular_admin(admin_user):
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/super-admins/", {"email": "blocked@test.com"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_super_admin_blocked_for_unauthenticated():
    resp = _post_unauthed(f"{BASE}/super-admins/", {"email": "anon@test.com"})
    assert resp.status_code == 401


# ── GET /super-admins/<pk>/ — IT only ─────────────────────────────────────────

@pytest.mark.django_db
def test_get_super_admin_detail_as_it(it_user):
    sa = _make_super_admin("detail@test.com", name="Detail", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _get(token, f"{BASE}/super-admins/{sa.id}/")
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "detail@test.com"


@pytest.mark.django_db
def test_get_super_admin_detail_nonexistent_returns_404(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _get(token, f"{BASE}/super-admins/{uuid.uuid4()}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_get_super_admin_detail_forbidden_for_super_admin_itself(super_admin_user):
    other = _make_super_admin("peer@test.com", institution_id=super_admin_user.institution_id)
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")

    resp = _get(token, f"{BASE}/super-admins/{other.id}/")
    assert resp.status_code == 403


# ── PATCH /super-admins/<pk>/ — IT only ───────────────────────────────────────

@pytest.mark.django_db
def test_edit_super_admin_name_as_it(it_user):
    sa = _make_super_admin("rename@test.com", name="Old", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _patch(token, f"{BASE}/super-admins/{sa.id}/", {"name": "New"})
    assert resp.status_code == 200
    sa.refresh_from_db()
    assert sa.name == "New"


@pytest.mark.django_db
def test_edit_super_admin_department_as_it(it_user):
    sa = _make_super_admin("redept@test.com", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _patch(token, f"{BASE}/super-admins/{sa.id}/", {"department": "ECE"})
    assert resp.status_code == 200
    sa.refresh_from_db()
    assert sa.department == "ECE"


@pytest.mark.django_db
def test_deactivate_and_reactivate_super_admin_as_it(it_user):
    sa = _make_super_admin("toggle@test.com", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _patch(token, f"{BASE}/super-admins/{sa.id}/", {"is_active": False})
    assert resp.status_code == 200
    sa.refresh_from_db()
    assert sa.is_active is False

    resp = _patch(token, f"{BASE}/super-admins/{sa.id}/", {"is_active": True})
    assert resp.status_code == 200
    sa.refresh_from_db()
    assert sa.is_active is True


@pytest.mark.django_db
def test_patch_nonexistent_super_admin_returns_404(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _patch(token, f"{BASE}/super-admins/{uuid.uuid4()}/", {"is_active": False})
    assert resp.status_code == 404


@pytest.mark.django_db
def test_edit_super_admin_forbidden_for_super_admin_itself(super_admin_user):
    other = _make_super_admin("peer2@test.com", institution_id=super_admin_user.institution_id)
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")

    resp = _patch(token, f"{BASE}/super-admins/{other.id}/", {"name": "Hacked"})
    assert resp.status_code == 403
    other.refresh_from_db()
    assert other.name != "Hacked"


# ── DELETE /super-admins/<pk>/ — IT only ──────────────────────────────────────

@pytest.mark.django_db
def test_delete_super_admin_as_it(it_user):
    sa = _make_super_admin("todelete@test.com", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _delete(token, f"{BASE}/super-admins/{sa.id}/")
    assert resp.status_code == 200
    assert not User.objects.filter(pk=sa.id).exists()


@pytest.mark.django_db
def test_delete_nonexistent_super_admin_returns_404(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _delete(token, f"{BASE}/super-admins/{uuid.uuid4()}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_delete_super_admin_forbidden_for_super_admin_itself(super_admin_user):
    other = _make_super_admin("peer3@test.com", institution_id=super_admin_user.institution_id)
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")

    resp = _delete(token, f"{BASE}/super-admins/{other.id}/")
    assert resp.status_code == 403
    assert User.objects.filter(pk=other.id).exists()


# ── POST /super-admins/<pk>/reset-default-password/ — IT only ────────────────

@pytest.mark.django_db
def test_reset_super_admin_to_default_password_as_it(it_user):
    sa = _make_super_admin("defreset@test.com", institution_id=it_user.institution_id)
    sa.set_password("SomethingElse@1")
    sa.save(update_fields=["password"])
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _post(token, f"{BASE}/super-admins/{sa.id}/reset-default-password/", {})
    assert resp.status_code == 200
    sa.refresh_from_db()
    assert sa.check_password(settings.SUPERADMIN_DEFAULT_PASSWORD)
    assert sa.force_password_change is True


@pytest.mark.django_db
def test_reset_super_admin_to_default_password_nonexistent_returns_404(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/{uuid.uuid4()}/reset-default-password/", {})
    assert resp.status_code == 404


@pytest.mark.django_db
def test_reset_super_admin_password_forbidden_for_super_admin_itself(super_admin_user):
    other = _make_super_admin("peer4@test.com", institution_id=super_admin_user.institution_id)
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")

    resp = _post(token, f"{BASE}/super-admins/{other.id}/reset-default-password/", {})
    assert resp.status_code == 403


# ── Cross-role sanity ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_super_admin_management_blocked_for_student(student_user):
    # Student login authenticates by student_id, not email.
    c = Client()
    login_resp = c.post(
        f"{BASE}/login/",
        data=json.dumps({"student_id": "S001", "password": settings.STUDENT_DEFAULT_PASSWORD, "role": "student"}),
        content_type="application/json",
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["data"]["access_token"]
    assert _get(token, f"{BASE}/super-admins/").status_code == 403
