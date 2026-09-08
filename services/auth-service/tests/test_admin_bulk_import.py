"""
Tests for bulk Admin account import (2026-08-20, revised same day).

Endpoint: POST /api/auth/admins/import/ — mirrors AdminStudentBulkCreateView
(user-service): one request with the whole email list, IT-exclusive,
per-email created/rejected results, {total, created, rejected, results}
response. Department is a single value applied to every row (picked in the
UI, same as the student bulk import's shared Department+Batch) — not a
per-row CSV column. `name` is not collected; bulk-created accounts start
blank and are renamed via the ordinary edit flow.
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
    resp = _post(token, f"{BASE}/admins/import/", {
        "emails": ["bulk1@test.com", "bulk2@test.com"],
        "department": "CSE",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    assert data["created"] == 2
    assert data["rejected"] == 0
    emails = {r["email"] for r in data["results"] if r["status"] == "created"}
    assert emails == {"bulk1@test.com", "bulk2@test.com"}

    admin1 = User.objects.get(email="bulk1@test.com")
    assert admin1.role == "admin"
    assert admin1.department == "CSE"
    assert admin1.name == ""
    assert admin1.force_password_change is True
    assert admin1.check_password(settings.ADMIN_DEFAULT_PASSWORD)
    assert admin1.institution_id == it_user.institution_id


@pytest.mark.django_db
def test_bulk_import_max_limit(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    emails = [f"s{i}@test.com" for i in range(1001)]
    resp = _post(token, f"{BASE}/admins/import/", {"emails": emails, "department": "CSE"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_bulk_import_duplicate_with_existing_account_rejected(it_user, admin_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/import/", {
        "emails": ["admin@test.com", "new-bulk@test.com"],  # admin@test.com already exists (admin_user fixture)
        "department": "CSE",
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["created"] == 1
    assert data["rejected"] == 1
    rejected = [r for r in data["results"] if r["status"] == "rejected"][0]
    assert "already exists" in rejected["reason"].lower()


@pytest.mark.django_db
def test_bulk_import_within_file_duplicates(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/import/", {
        "emails": ["dup@test.com", "DUP@test.com"],  # same email, different case
        "department": "CSE",
    })
    data = resp.json()["data"]
    assert data["created"] == 1
    assert data["rejected"] == 1


@pytest.mark.django_db
def test_bulk_import_missing_department_returns_400(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/import/", {"emails": ["nodept@test.com"]})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_bulk_import_invalid_email_format_rejected(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/import/", {"emails": ["not-an-email"], "department": "CSE"})
    data = resp.json()["data"]
    assert data["rejected"] == 1
    assert "invalid" in data["results"][0]["reason"].lower()


@pytest.mark.django_db
def test_bulk_import_empty_email_rejected(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/import/", {"emails": ["", "valid@test.com"], "department": "CSE"})
    data = resp.json()["data"]
    assert data["created"] == 1
    assert data["rejected"] == 1


@pytest.mark.django_db
def test_bulk_import_invalid_emails_type_returns_400(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/import/", {"emails": "not-a-list", "department": "CSE"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_bulk_import_empty_emails_returns_400(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/admins/import/", {"emails": [], "department": "CSE"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_bulk_import_forbidden_for_admin(admin_user):
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/admins/import/", {"emails": ["x@test.com"], "department": "CSE"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_bulk_import_forbidden_for_super_admin(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/admins/import/", {"emails": ["x@test.com"], "department": "CSE"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_bulk_import_blocked_for_unauthenticated():
    resp = _post_unauthed(f"{BASE}/admins/import/", {"emails": ["x@test.com"], "department": "CSE"})
    assert resp.status_code == 401
