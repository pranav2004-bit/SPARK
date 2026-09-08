"""
Tests for bulk Super Admin account import (2026-08-20, revised same day).

Endpoint: POST /api/auth/super-admins/import/ — same shared
_bulk_create_accounts helper as Admin bulk import, targeting role=super_admin
and SUPERADMIN_DEFAULT_PASSWORD. Department is a single value applied to
every row (picked in the UI), not a per-row CSV column. Same IT-exclusive
access as single-create Super Admin management (no read-only remnant for
Super Admin itself).
"""

import json
import pytest
from django.conf import settings
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()

BASE = "/api/auth"


def _login_token(email, password, role):
    client = Client()
    resp = client.post(
        f"{BASE}/login/",
        data=json.dumps({"email": email, "password": password, "role": role}),
        content_type="application/json",
    )
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["data"]["access_token"]


def _post(token, url, data):
    return Client().post(url, data=json.dumps(data), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")


def _post_unauthed(url, data):
    return Client().post(url, data=json.dumps(data), content_type="application/json")


@pytest.mark.django_db
def test_bulk_import_as_it(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/import/", {
        "emails": ["sabulk1@test.com", "sabulk2@test.com"],
        "department": "ECE",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["created"] == 2
    assert data["rejected"] == 0

    sa1 = User.objects.get(email="sabulk1@test.com")
    assert sa1.role == "super_admin"
    assert sa1.department == "ECE"
    assert sa1.name == ""
    assert sa1.check_password(settings.SUPERADMIN_DEFAULT_PASSWORD)
    assert sa1.institution_id == it_user.institution_id


@pytest.mark.django_db
def test_bulk_import_duplicate_with_existing_account_rejected(it_user, super_admin_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/import/", {
        "emails": ["superadmin@test.com", "new-sabulk@test.com"],  # already exists
        "department": "CSE",
    })
    data = resp.json()["data"]
    assert data["created"] == 1
    assert data["rejected"] == 1


@pytest.mark.django_db
def test_bulk_import_missing_department_returns_400(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/import/", {"emails": ["nodept@test.com"]})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_bulk_import_max_limit(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    emails = [f"s{i}@test.com" for i in range(1001)]
    resp = _post(token, f"{BASE}/super-admins/import/", {"emails": emails, "department": "CSE"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_bulk_import_forbidden_for_admin(admin_user):
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/super-admins/import/", {"emails": ["x@test.com"], "department": "CSE"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_bulk_import_forbidden_for_super_admin_itself(super_admin_user):
    """Zero access for Super Admin, same as every other endpoint on this resource."""
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/super-admins/import/", {"emails": ["x@test.com"], "department": "CSE"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_bulk_import_blocked_for_unauthenticated():
    resp = _post_unauthed(f"{BASE}/super-admins/import/", {"emails": ["x@test.com"], "department": "CSE"})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_bulk_import_invalid_emails_type_returns_400(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/super-admins/import/", {"emails": "not-a-list", "department": "CSE"})
    assert resp.status_code == 400
