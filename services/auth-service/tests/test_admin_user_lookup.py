"""
Tests for GET /api/auth/admin/users/lookup/ — resolves a batch of user_ids
to display name/email, institution-scoped. Backs "Created by <name>" labels
on admin-authored content in other services (e.g. assessment-service's
question papers list).
"""

import json
import uuid
import pytest
from django.conf import settings
from django.test import Client
from django.contrib.auth import get_user_model

from .conftest import INSTITUTION_ID

User = get_user_model()
BASE = "/api/auth"


def _get(token, url):
    kwargs = dict(content_type="application/json")
    if token:
        kwargs["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return Client().get(url, **kwargs)


def _post(token_or_none, url, data=None):
    c = Client()
    kwargs = dict(data=json.dumps(data or {}), content_type="application/json")
    if token_or_none:
        kwargs["HTTP_AUTHORIZATION"] = f"Bearer {token_or_none}"
    return c.post(url, **kwargs)


def _login(email, password, role):
    resp = _post(None, f"{BASE}/login/", {"email": email, "password": password, "role": role})
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["data"]["access_token"]


def _login_student(student_id, password):
    resp = _post(None, f"{BASE}/login/", {"student_id": student_id, "password": password, "role": "student"})
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["data"]["access_token"]


@pytest.mark.django_db
def test_resolves_a_single_id_in_same_institution(admin_user):
    other = User.objects.create_user(
        email="colleague@test.com", password="X@pass1", role="admin",
        institution_id=INSTITUTION_ID, name="Dr. Colleague",
    )
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _get(token, f"{BASE}/admin/users/lookup/?ids={other.id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(other.id)
    assert data[0]["name"] == "Dr. Colleague"
    assert data[0]["email"] == "colleague@test.com"


@pytest.mark.django_db
def test_resolves_multiple_ids_in_one_call(admin_user):
    a = User.objects.create_user(email="a@test.com", password="X@pass1", role="admin", institution_id=INSTITUTION_ID, name="A")
    b = User.objects.create_user(email="b@test.com", password="X@pass1", role="admin", institution_id=INSTITUTION_ID, name="B")
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _get(token, f"{BASE}/admin/users/lookup/?ids={a.id},{b.id}")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()["data"]}
    assert ids == {str(a.id), str(b.id)}


@pytest.mark.django_db
def test_empty_name_is_returned_as_empty_string_not_omitted(admin_user):
    # Backend returns the raw data honestly — the frontend decides how to
    # fall back to email when name is blank, not this endpoint.
    blank_name_user = User.objects.create_user(
        email="blank@test.com", password="X@pass1", role="admin",
        institution_id=INSTITUTION_ID, name="",
    )
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _get(token, f"{BASE}/admin/users/lookup/?ids={blank_name_user.id}")
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == ""
    assert data[0]["email"] == "blank@test.com"


@pytest.mark.django_db
def test_id_from_a_different_institution_is_silently_omitted(admin_user):
    other_institution = uuid.uuid4()
    outsider = User.objects.create_user(
        email="outsider@other.com", password="X@pass1", role="admin",
        institution_id=other_institution, name="Outsider",
    )
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _get(token, f"{BASE}/admin/users/lookup/?ids={outsider.id}")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.django_db
def test_missing_ids_param_returns_empty_list(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _get(token, f"{BASE}/admin/users/lookup/")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.django_db
def test_malformed_ids_are_skipped_not_errored(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _get(token, f"{BASE}/admin/users/lookup/?ids=not-a-uuid,,{admin_user.id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == str(admin_user.id)


@pytest.mark.django_db
def test_nonexistent_id_is_silently_omitted(admin_user):
    token = _login("admin@test.com", "Admin@pass1", "admin")
    resp = _get(token, f"{BASE}/admin/users/lookup/?ids={uuid.uuid4()}")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.django_db
def test_super_admin_can_also_call_this(super_admin_user):
    token = _login("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _get(token, f"{BASE}/admin/users/lookup/?ids={super_admin_user.id}")
    assert resp.status_code == 200
    assert resp.json()["data"][0]["email"] == "superadmin@test.com"


@pytest.mark.django_db
def test_blocked_for_student(student_user):
    token = _login_student("S001", settings.STUDENT_DEFAULT_PASSWORD)
    resp = _get(token, f"{BASE}/admin/users/lookup/?ids={student_user.id}")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_blocked_for_unauthenticated():
    resp = _get(None, f"{BASE}/admin/users/lookup/?ids={uuid.uuid4()}")
    assert resp.status_code == 401
