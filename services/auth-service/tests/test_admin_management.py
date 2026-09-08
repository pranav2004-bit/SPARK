"""
Tests for Admin Management endpoints.

Endpoints covered:
  GET  /api/auth/admins/                              — list all admins
  POST /api/auth/admins/                              — create admin (email required, name optional, password auto)
  PATCH /api/auth/admins/<pk>/                        — edit name / deactivate / reactivate admin
  DELETE /api/auth/admins/<pk>/                       — permanently delete admin
  POST /api/auth/admins/<pk>/reset-default-password/  — reset admin password to default (the endpoint the UI
                                                          actually calls)
  POST /api/auth/admin-password-reset/                — reset admin password by id (legacy, not called by the UI —
                                                          untouched by the 2026-08-19 changes below, still Super
                                                          Admin-only)

Access (2026-08-19): Admin account management was placed in the IT role.
Phase 1 (same mechanism as every other module moved to IT this project):
IT was given the same full create/manage capability Super Admin had —
additive, not a move — and validated live. Phase 2, immediately after
validating phase 1, restricted Super Admin to read-only on these same
endpoints (GET stays; POST/PATCH/DELETE/reset-password are now IT-exclusive)
— the same treatment Batches got earlier the same day. The super_admin
write tests that existed before phase 2 are kept below as 403 assertions;
their validation coverage (duplicate email, institution-stamping, etc.)
moved to the IT section, since IT is now the only role that reaches that
code path.
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


def _make_admin(email, name="", institution_id=None):
    """Create an admin User directly via the ORM — used to seed data in
    tests where the API's own create endpoint is not what's under test (and,
    since 2026-08-19 phase 2, is no longer reachable by super_admin at all)."""
    return User.objects.create_user(
        email=email,
        password=settings.ADMIN_DEFAULT_PASSWORD,
        role="admin",
        name=name,
        institution_id=institution_id,
    )


# ── GET /admins/ — read-only, Super Admin and IT both allowed ────────────────

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


# ── GET /admins/<pk>/ — read-only, Super Admin and IT both allowed ───────────

@pytest.mark.django_db
def test_get_admin_detail_as_super_admin(super_admin_user):
    admin = _make_admin("detail@test.com", name="Detail", institution_id=super_admin_user.institution_id)
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")

    resp = _get(token, f"{BASE}/admins/{admin.id}/")
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "detail@test.com"


@pytest.mark.django_db
def test_get_admin_detail_nonexistent_returns_404_for_super_admin(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _get(token, f"{BASE}/admins/{uuid.uuid4()}/")
    assert resp.status_code == 404


# ── POST /admins/ — IT-exclusive (2026-08-19, phase 2) ────────────────────────

@pytest.mark.django_db
def test_create_admin_forbidden_for_super_admin(super_admin_user):
    """Admin account creation moved to IT (2026-08-19) — Super Admin is
    read-only here now, same treatment as Batches."""
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/admins/", {"email": "shouldfail@test.com"})
    assert resp.status_code == 403
    assert not User.objects.filter(email="shouldfail@test.com").exists()


@pytest.mark.django_db
def test_create_admin_blocked_for_regular_admin(admin_user):
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/admins/", {"email": "blocked@test.com"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_admin_blocked_for_unauthenticated():
    resp = _post_unauthed(f"{BASE}/admins/", {"email": "anon@test.com"})
    assert resp.status_code == 401


# ── PATCH /admins/<pk>/ — IT-exclusive (2026-08-19, phase 2) ──────────────────

@pytest.mark.django_db
def test_edit_admin_name_forbidden_for_super_admin(super_admin_user):
    admin = _make_admin("rename@test.com", institution_id=super_admin_user.institution_id)
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")

    resp = _patch(token, f"{BASE}/admins/{admin.id}/", {"name": "New Name"})
    assert resp.status_code == 403
    admin.refresh_from_db()
    assert admin.name != "New Name"


@pytest.mark.django_db
def test_toggle_active_forbidden_for_super_admin(super_admin_user):
    admin = _make_admin("toggle@test.com", institution_id=super_admin_user.institution_id)
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")

    resp = _patch(token, f"{BASE}/admins/{admin.id}/", {"is_active": False})
    assert resp.status_code == 403
    admin.refresh_from_db()
    assert admin.is_active is True


# ── DELETE /admins/<pk>/ — IT-exclusive (2026-08-19, phase 2) ─────────────────

@pytest.mark.django_db
def test_delete_admin_forbidden_for_super_admin(super_admin_user):
    admin = _make_admin("todelete@test.com", institution_id=super_admin_user.institution_id)
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")

    resp = _delete(token, f"{BASE}/admins/{admin.id}/")
    assert resp.status_code == 403
    assert User.objects.filter(pk=admin.id).exists()


# ── POST /admins/<pk>/reset-default-password/ — IT-exclusive ─────────────────
# (2026-08-19, phase 2) — a write-only action with no read equivalent, so
# Super Admin loses it outright, same as Admin's toggle-status did earlier.

@pytest.mark.django_db
def test_reset_admin_to_default_password_forbidden_for_super_admin(super_admin_user):
    admin = _make_admin("defreset@test.com", institution_id=super_admin_user.institution_id)
    admin.set_password("SomethingElse@1")
    admin.save(update_fields=["password"])
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")

    resp = _post(token, f"{BASE}/admins/{admin.id}/reset-default-password/", {})
    assert resp.status_code == 403
    admin.refresh_from_db()
    assert admin.check_password("SomethingElse@1")


# ── POST /admin-password-reset/ (legacy endpoint, not called by the UI) ──────
# Untouched by the 2026-08-19 changes above — still Super Admin-only. Seeds
# via the ORM (not the now-blocked create endpoint) since only the reset
# endpoint itself is under test here.

@pytest.mark.django_db
def test_reset_admin_password_by_id(super_admin_user):
    admin = _make_admin("resetme@test.com", institution_id=super_admin_user.institution_id)
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")

    resp = _post(token, f"{BASE}/admin-password-reset/", {
        "admin_id": str(admin.id),
        "new_password": "NewPass@99",
    })
    assert resp.status_code == 200
    admin.refresh_from_db()
    assert admin.check_password("NewPass@99")


@pytest.mark.django_db
def test_reset_admin_password_short_password_returns_400(super_admin_user):
    admin = _make_admin("shortpw@test.com", institution_id=super_admin_user.institution_id)
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")

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


# ── IT: full CRUD (2026-08-19) — IT is the sole writer on every endpoint ──────
# above except the legacy /admin-password-reset/. All validation coverage
# that used to run via super_admin write calls (now blocked) lives here.

@pytest.mark.django_db
def test_list_admins_returns_200_for_it(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _get(token, f"{BASE}/admins/")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.django_db
def test_create_admin_with_name_and_email(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/", {"email": "newadmin@test.com", "name": "Alice"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["email"] == "newadmin@test.com"
    assert data["data"]["name"] == "Alice"
    assert data["data"]["is_active"] is True


@pytest.mark.django_db
def test_create_admin_without_name_is_allowed(it_user):
    """Name is optional — creating with only email must succeed."""
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/", {"email": "noname@test.com"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["name"] == ""


@pytest.mark.django_db
def test_create_admin_with_department_is_accepted(it_user):
    """department is shared with the Super Admin serializer/view (2026-08-20)
    — Admin's own UI doesn't send it yet, but the backend must accept and
    persist it when present."""
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/", {"email": "deptadmin@test.com", "department": "ECE"})
    assert resp.status_code == 201
    assert resp.json()["data"]["department"] == "ECE"


@pytest.mark.django_db
def test_create_admin_email_lowercased(it_user):
    """Emails are normalised to lowercase on creation."""
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/", {"email": "UPPER@EXAMPLE.COM", "name": "Bob"})
    assert resp.status_code == 201
    assert resp.json()["data"]["email"] == "upper@example.com"


@pytest.mark.django_db
def test_create_admin_default_password_is_spark(it_user):
    """The created admin must be able to log in with the default password spark@123."""
    token = _login_token("it@test.com", "It@pass123", "it")
    _post(token, f"{BASE}/admins/", {"email": "pwcheck@test.com", "name": "PwCheck"})

    admin = User.objects.get(email="pwcheck@test.com")
    assert admin.check_password(settings.ADMIN_DEFAULT_PASSWORD), f"Default password should be {settings.ADMIN_DEFAULT_PASSWORD}"


@pytest.mark.django_db
def test_create_admin_default_password_allows_login(it_user):
    """Admin created with default password can immediately log in via the login endpoint."""
    token = _login_token("it@test.com", "It@pass123", "it")
    _post(token, f"{BASE}/admins/", {"email": "logincheck@test.com"})

    resp = _post_unauthed(
        f"{BASE}/login/",
        {"email": "logincheck@test.com", "password": settings.ADMIN_DEFAULT_PASSWORD, "role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["user"]["role"] == "admin"


@pytest.mark.django_db
def test_create_admin_duplicate_email_returns_409(it_user):
    """Creating a second account with the same email must return 409."""
    token = _login_token("it@test.com", "It@pass123", "it")
    _post(token, f"{BASE}/admins/", {"email": "dup@test.com", "name": "First"})
    resp = _post(token, f"{BASE}/admins/", {"email": "dup@test.com", "name": "Second"})
    assert resp.status_code == 409
    assert "already exists" in resp.json()["message"].lower()


@pytest.mark.django_db
def test_create_admin_duplicate_email_case_insensitive(it_user):
    """Email uniqueness check is case-insensitive because emails are normalised."""
    token = _login_token("it@test.com", "It@pass123", "it")
    _post(token, f"{BASE}/admins/", {"email": "case@test.com"})
    resp = _post(token, f"{BASE}/admins/", {"email": "CASE@TEST.COM"})
    assert resp.status_code == 409


@pytest.mark.django_db
def test_create_admin_missing_email_returns_400(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/", {"name": "NoEmail"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_admin_invalid_email_returns_400(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/", {"email": "not-an-email"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_admin_no_department_stored(it_user):
    """Department must be empty string — it is no longer accepted as input."""
    token = _login_token("it@test.com", "It@pass123", "it")
    _post(token, f"{BASE}/admins/", {"email": "nodept@test.com"})
    admin = User.objects.get(email="nodept@test.com")
    assert admin.department == ""


@pytest.mark.django_db
def test_create_admin_auto_stamps_institution_id(it_user):
    """
    Faculty created by IT must inherit IT's own institution_id — the create
    form sends only name + email, no UUID exposed anywhere in the UI.
    """
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/", {
        "email": "faculty@anits.edu",
        "name": "Dr. Rajan",
    })
    assert resp.status_code == 201
    admin = User.objects.get(email="faculty@anits.edu")
    assert admin.institution_id == it_user.institution_id


@pytest.mark.django_db
def test_create_admin_institution_id_not_overridable_from_request(it_user):
    """
    institution_id sent in the POST body is silently ignored — the backend always
    stamps from the creator's own institution_id, so an arbitrary UUID in the
    request must NOT be stored on the created admin record.
    """
    token = _login_token("it@test.com", "It@pass123", "it")
    arbitrary_uuid = str(uuid.uuid4())
    resp = _post(token, f"{BASE}/admins/", {
        "email": "override@test.com",
        "institution_id": arbitrary_uuid,   # should be ignored by the backend
    })
    assert resp.status_code == 201
    admin = User.objects.get(email="override@test.com")
    assert admin.institution_id == it_user.institution_id
    assert str(admin.institution_id) != arbitrary_uuid


@pytest.mark.django_db
def test_create_admin_name_optional_institution_still_stamped(it_user):
    """Creating an admin with only email (no name) still gets institution_id stamped from IT."""
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/", {"email": "noname2@test.com"})
    assert resp.status_code == 201
    admin = User.objects.get(email="noname2@test.com")
    assert admin.name == ""
    assert admin.institution_id == it_user.institution_id


@pytest.mark.django_db
def test_get_admin_detail_as_it(it_user):
    admin = _make_admin("itdetail@test.com", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _get(token, f"{BASE}/admins/{admin.id}/")
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "itdetail@test.com"


@pytest.mark.django_db
def test_edit_admin_name_as_it(it_user):
    admin = _make_admin("itrename@test.com", name="Old", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _patch(token, f"{BASE}/admins/{admin.id}/", {"name": "New"})
    assert resp.status_code == 200
    admin.refresh_from_db()
    assert admin.name == "New"


@pytest.mark.django_db
def test_edit_admin_department_as_it(it_user):
    admin = _make_admin("itredept@test.com", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _patch(token, f"{BASE}/admins/{admin.id}/", {"department": "MECH"})
    assert resp.status_code == 200
    admin.refresh_from_db()
    assert admin.department == "MECH"


@pytest.mark.django_db
def test_deactivate_and_reactivate_admin_as_it(it_user):
    admin = _make_admin("ittoggle@test.com", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _patch(token, f"{BASE}/admins/{admin.id}/", {"is_active": False})
    assert resp.status_code == 200
    admin.refresh_from_db()
    assert admin.is_active is False

    resp = _patch(token, f"{BASE}/admins/{admin.id}/", {"is_active": True})
    assert resp.status_code == 200
    admin.refresh_from_db()
    assert admin.is_active is True


@pytest.mark.django_db
def test_patch_nonexistent_admin_returns_404_for_it(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _patch(token, f"{BASE}/admins/{uuid.uuid4()}/", {"is_active": False})
    assert resp.status_code == 404


@pytest.mark.django_db
def test_delete_admin_as_it(it_user):
    admin = _make_admin("ittodelete@test.com", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _delete(token, f"{BASE}/admins/{admin.id}/")
    assert resp.status_code == 200
    assert not User.objects.filter(pk=admin.id).exists()


@pytest.mark.django_db
def test_delete_nonexistent_admin_returns_404_for_it(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _delete(token, f"{BASE}/admins/{uuid.uuid4()}/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_reset_admin_to_default_password_as_it(it_user):
    admin = _make_admin("itdefreset@test.com", institution_id=it_user.institution_id)
    admin.set_password("SomethingElse@1")
    admin.save(update_fields=["password"])
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _post(token, f"{BASE}/admins/{admin.id}/reset-default-password/", {})
    assert resp.status_code == 200
    admin.refresh_from_db()
    assert admin.check_password(settings.ADMIN_DEFAULT_PASSWORD)
    assert admin.force_password_change is True


@pytest.mark.django_db
def test_reset_admin_to_default_password_nonexistent_returns_404_for_it(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/{uuid.uuid4()}/reset-default-password/", {})
    assert resp.status_code == 404


@pytest.mark.django_db
def test_admin_management_blocked_for_regular_admin(admin_user):
    """A regular admin must not be able to manage other admin accounts,
    on any of the endpoints IT now owns."""
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    assert _get(token, f"{BASE}/admins/").status_code == 403
    assert _post(token, f"{BASE}/admins/", {"email": "x@test.com"}).status_code == 403


@pytest.mark.django_db
def test_admin_management_blocked_for_student(student_user):
    # Student login authenticates by student_id, not email — _login_token
    # only supports the email-based admin/super_admin/it login shape.
    c = Client()
    login_resp = c.post(
        f"{BASE}/login/",
        data=json.dumps({"student_id": "S001", "password": settings.STUDENT_DEFAULT_PASSWORD, "role": "student"}),
        content_type="application/json",
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["data"]["access_token"]
    assert _get(token, f"{BASE}/admins/").status_code == 403
