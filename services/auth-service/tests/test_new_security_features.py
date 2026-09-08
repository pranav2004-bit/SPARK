"""
Tests for new security features introduced in the institution_id / token_version round:
  - force_password_change=True set on account creation (admin, student)
  - force_password_change=False after password change
  - token_version incremented on password change
  - TokenVersionJWTAuthentication rejects stale (pre-change) tokens
  - INSTITUTION_ID validation in create_default_it management command (IT is the
    bootstrapped root as of 2026-08-20, replacing super_admin)
  - force_password_change present in login response body
"""

import json
import uuid
import os
import pytest
from unittest import mock
from django.conf import settings
from django.test import Client
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model

User = get_user_model()

BASE = "/api/auth"
INSTITUTION_ID = uuid.UUID("1470350a-1765-41d1-92b9-bf7b040ddaf9")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _post(token_or_none, url, data=None):
    c = Client()
    kwargs = dict(data=json.dumps(data or {}), content_type="application/json")
    if token_or_none:
        kwargs["HTTP_AUTHORIZATION"] = f"Bearer {token_or_none}"
    return c.post(url, **kwargs)


def _get(token, url):
    return Client().get(url, content_type="application/json",
                        HTTP_AUTHORIZATION=f"Bearer {token}")


def _post_internal(url, data):
    """Call an internal-only endpoint with the SERVICE_KEY header."""
    c = Client()
    return c.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
        HTTP_X_SERVICE_KEY=settings.SERVICE_KEY,
    )


def _login(email_or_id, password, role):
    if role == "student":
        body = {"student_id": email_or_id, "password": password, "role": role}
    else:
        body = {"email": email_or_id, "password": password, "role": role}
    resp = _post(None, f"{BASE}/login/", body)
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["data"]["access_token"]


# ── force_password_change on account creation ─────────────────────────────────

@pytest.mark.django_db
def test_admin_created_via_api_has_force_password_change(it_user):
    """Admin created through the API must have force_password_change=True.
    Creator is IT — admin-account creation is IT-exclusive (2026-08-19)."""
    it_token = _login("it@test.com", "It@pass123", "it")
    _post(it_token, f"{BASE}/admins/", {"email": "newadmin@security.com", "name": "Test"})
    admin = User.objects.get(email="newadmin@security.com")
    assert admin.force_password_change is True


@pytest.mark.django_db
def test_student_created_via_internal_api_has_force_password_change(db):
    """Student created through the internal API must have force_password_change=True."""
    user_id = str(uuid.uuid4())
    resp = _post_internal(
        f"{BASE}/internal/students/",
        {
            "user_id": user_id,
            "student_id": "S999",
            "institution_id": str(INSTITUTION_ID),
        },
    )
    assert resp.status_code == 201, resp.json()
    student = User.objects.get(student_id="S999")
    assert student.force_password_change is True


# ── force_password_change in login response body ───────────────────────────────

@pytest.mark.django_db
def test_admin_login_response_contains_force_password_change(admin_user):
    """Login response for admin must include force_password_change in user object."""
    resp = _post(None, f"{BASE}/login/",
                 {"email": "admin@test.com", "password": "Admin@pass1", "role": "admin"})
    assert resp.status_code == 200
    user_data = resp.json()["data"]["user"]
    assert "force_password_change" in user_data
    assert isinstance(user_data["force_password_change"], bool)


@pytest.mark.django_db
def test_student_login_response_contains_force_password_change(student_user):
    """Login response for student must include force_password_change in user object."""
    resp = _post(None, f"{BASE}/login/",
                 {"student_id": "S001", "password": settings.STUDENT_DEFAULT_PASSWORD, "role": "student"})
    assert resp.status_code == 200
    user_data = resp.json()["data"]["user"]
    assert "force_password_change" in user_data
    assert isinstance(user_data["force_password_change"], bool)


@pytest.mark.django_db
def test_super_admin_login_response_contains_force_password_change(super_admin_user):
    """Login response for super_admin must include force_password_change in user object."""
    resp = _post(None, f"{BASE}/login/",
                 {"email": "superadmin@test.com", "password": "Super@pass1", "role": "super_admin"})
    assert resp.status_code == 200
    user_data = resp.json()["data"]["user"]
    assert "force_password_change" in user_data
    assert isinstance(user_data["force_password_change"], bool)


# ── force_password_change cleared after password change ───────────────────────

@pytest.mark.django_db
def test_admin_force_password_change_cleared_after_change(admin_user):
    """force_password_change must be False after admin changes their password."""
    admin_user.force_password_change = True
    admin_user.save(update_fields=["force_password_change"])

    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/me/change-password/", {
        "current_password": "Admin@pass1",
        "new_password": "NewSecure@88",
        "confirm_password": "NewSecure@88",
    })
    assert resp.status_code == 200
    admin_user.refresh_from_db()
    assert admin_user.force_password_change is False


@pytest.mark.django_db
def test_student_force_password_change_cleared_after_change(student_user):
    """force_password_change must be False after student changes their password."""
    student_user.force_password_change = True
    student_user.save(update_fields=["force_password_change"])

    token = _login("S001", settings.STUDENT_DEFAULT_PASSWORD, "student")
    resp = _post(token, f"{BASE}/student/change-password/", {
        "current_password": settings.STUDENT_DEFAULT_PASSWORD,
        "new_password": "NewSecure@88",
        "repeat_new_password": "NewSecure@88",
    })
    assert resp.status_code == 200
    student_user.refresh_from_db()
    assert student_user.force_password_change is False


# ── token_version incremented after password change ───────────────────────────

@pytest.mark.django_db
def test_admin_token_version_increments_on_password_change(admin_user):
    """token_version must increment by 1 when admin changes their password."""
    initial_version = admin_user.token_version
    token = _login("admin@test.com", "Admin@pass1", "admin")
    _post(token, f"{BASE}/me/change-password/", {
        "current_password": "Admin@pass1",
        "new_password": "NewSecure@77",
        "confirm_password": "NewSecure@77",
    })
    admin_user.refresh_from_db()
    assert admin_user.token_version == initial_version + 1


@pytest.mark.django_db
def test_student_token_version_increments_on_password_change(student_user):
    """token_version must increment by 1 when student changes their password."""
    initial_version = student_user.token_version
    token = _login("S001", settings.STUDENT_DEFAULT_PASSWORD, "student")
    _post(token, f"{BASE}/student/change-password/", {
        "current_password": settings.STUDENT_DEFAULT_PASSWORD,
        "new_password": "NewSecure@77",
        "repeat_new_password": "NewSecure@77",
    })
    student_user.refresh_from_db()
    assert student_user.token_version == initial_version + 1


# ── TokenVersionJWTAuthentication rejects stale tokens ────────────────────────

@pytest.mark.django_db
def test_stale_admin_token_rejected_after_password_change(admin_user):
    """A token issued before a password change must be rejected on subsequent requests."""
    old_token = _login("admin@test.com", "Admin@pass1", "admin")

    # Change password — increments token_version, old token becomes stale
    new_token = _login("admin@test.com", "Admin@pass1", "admin")
    _post(new_token, f"{BASE}/me/change-password/", {
        "current_password": "Admin@pass1",
        "new_password": "StaleTest@99",
        "confirm_password": "StaleTest@99",
    })

    # Old token must now be rejected
    resp = _get(old_token, f"{BASE}/me/")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_new_admin_token_valid_after_password_change(admin_user):
    """A token issued after a password change must be accepted."""
    # Change password using old token
    old_token = _login("admin@test.com", "Admin@pass1", "admin")
    _post(old_token, f"{BASE}/me/change-password/", {
        "current_password": "Admin@pass1",
        "new_password": "FreshToken@99",
        "confirm_password": "FreshToken@99",
    })

    # Login again with new password to get a fresh token
    new_token = _login("admin@test.com", "FreshToken@99", "admin")
    resp = _get(new_token, f"{BASE}/me/")
    assert resp.status_code == 200


# ── INSTITUTION_ID management command validation ──────────────────────────────
# create_default_it (2026-08-20) replaced create_default_superadmin as the
# bootstrap command — IT is now the platform's bootstrapped root.

@pytest.mark.django_db
def test_create_default_it_raises_if_institution_id_missing():
    """Management command must fail with CommandError if INSTITUTION_ID is not set."""
    with mock.patch.dict(os.environ, {"INSTITUTION_ID": ""}, clear=False):
        with pytest.raises(CommandError, match="INSTITUTION_ID"):
            call_command("create_default_it")


@pytest.mark.django_db
def test_create_default_it_raises_if_institution_id_invalid():
    """Management command must fail with CommandError if INSTITUTION_ID is not a valid UUID."""
    with mock.patch.dict(os.environ, {"INSTITUTION_ID": "not-a-uuid"}, clear=False):
        with pytest.raises(CommandError, match="not a valid UUID"):
            call_command("create_default_it")


@pytest.mark.django_db
def test_create_default_it_raises_on_institution_id_mismatch():
    """Management command must fail if INSTITUTION_ID in .env differs from the existing DB record."""
    original_id = uuid.UUID("1470350a-1765-41d1-92b9-bf7b040ddaf9")
    different_id = str(uuid.uuid4())

    # Create IT account with original institution_id
    User.objects.create_user(
        email=settings.IT_EMAIL,
        password=settings.IT_PASSWORD,
        role="it",
        institution_id=original_id,
    )

    # Run command with a different INSTITUTION_ID — must fail
    with mock.patch.dict(os.environ, {"INSTITUTION_ID": different_id}, clear=False):
        with pytest.raises(CommandError, match="mismatch"):
            call_command("create_default_it")


@pytest.mark.django_db
def test_create_default_it_raises_on_password_drift():
    """Management command must fail loudly if .env's IT_PASSWORD no longer
    matches the live database password — editing .env has no effect on an existing
    account, so this must be a hard failure, not a silent no-op."""
    User.objects.create_user(
        email=settings.IT_EMAIL,
        password="OriginalPass@1",
        role="it",
        institution_id=uuid.UUID(os.environ["INSTITUTION_ID"]),
    )

    with mock.patch.object(settings, "IT_PASSWORD", "DifferentPass@9"):
        with pytest.raises(CommandError, match="does not match the live database password"):
            call_command("create_default_it")


@pytest.mark.django_db
def test_create_default_it_no_error_when_password_matches():
    """No error when .env's IT_PASSWORD matches the live database password."""
    User.objects.create_user(
        email=settings.IT_EMAIL,
        password=settings.IT_PASSWORD,
        role="it",
        institution_id=uuid.UUID(os.environ["INSTITUTION_ID"]),
    )

    call_command("create_default_it")  # must not raise


@pytest.mark.django_db
def test_create_default_it_succeeds_with_valid_institution_id():
    """Management command must create the IT account with force_password_change=True."""
    call_command("create_default_it")
    user = User.objects.get(email=settings.IT_EMAIL)
    assert str(user.institution_id) == os.environ["INSTITUTION_ID"]
    assert user.force_password_change is True
    assert user.role == "it"


@pytest.mark.django_db
def test_create_default_it_idempotent():
    """Running the command twice must not raise an error or create a duplicate."""
    call_command("create_default_it")
    call_command("create_default_it")
    count = User.objects.filter(email=settings.IT_EMAIL).count()
    assert count == 1
