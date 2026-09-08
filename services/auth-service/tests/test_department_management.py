"""
Tests for Department management endpoints.

Endpoints covered:
  GET    /api/auth/departments/           — list departments for caller's institution
  POST   /api/auth/departments/           — create department (code required+unique, name optional, IT only)
  GET    /api/auth/departments/<pk>/      — retrieve one department
  PATCH  /api/auth/departments/<pk>/      — edit name / toggle is_active (IT only) — code not editable
  DELETE /api/auth/departments/<pk>/      — permanently delete department (IT only)

Access (2026-08-20): read = Admin + Super Admin + IT (all three consume this
as dropdown/filter options); write = IT-exclusive. Mirrors Batch's
read/write split in user-service.
"""

import json
import uuid
import pytest
from django.conf import settings
from django.test import Client
from django.contrib.auth import get_user_model

from authentication.models import Department

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


def _get(token, url):
    return Client().get(url, HTTP_AUTHORIZATION=f"Bearer {token}", content_type="application/json")


def _post(token, url, data):
    return Client().post(url, data=json.dumps(data), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")


def _post_unauthed(url, data):
    return Client().post(url, data=json.dumps(data), content_type="application/json")


def _get_unauthed(url):
    return Client().get(url, content_type="application/json")


def _patch(token, url, data):
    return Client().patch(url, data=json.dumps(data), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")


def _delete(token, url):
    return Client().delete(url, HTTP_AUTHORIZATION=f"Bearer {token}", content_type="application/json")


def _make_department(code, name="", institution_id=None, is_active=True):
    return Department.objects.create(code=code, name=name, institution_id=institution_id, is_active=is_active)


# ── GET /departments/ — Admin + Super Admin + IT; no anon access ─────────────

@pytest.mark.django_db
def test_list_departments_returns_200_for_it(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _get(token, f"{BASE}/departments/")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert isinstance(resp.json()["data"], list)


@pytest.mark.django_db
def test_list_departments_returns_200_for_admin(admin_user):
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    resp = _get(token, f"{BASE}/departments/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_list_departments_returns_200_for_super_admin(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _get(token, f"{BASE}/departments/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_list_departments_blocked_for_unauthenticated():
    resp = _get_unauthed(f"{BASE}/departments/")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_list_departments_scoped_to_own_institution_for_it(it_user):
    _make_department("CSE", institution_id=it_user.institution_id)
    _make_department("MECH", institution_id=uuid.uuid4())  # different institution
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _get(token, f"{BASE}/departments/")
    codes = [d["code"] for d in resp.json()["data"]]
    assert "CSE" in codes
    assert "MECH" not in codes


@pytest.mark.django_db
def test_list_departments_cross_institution_for_super_admin(super_admin_user):
    _make_department("CSE", institution_id=super_admin_user.institution_id)
    _make_department("MECH", institution_id=uuid.uuid4())
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _get(token, f"{BASE}/departments/")
    codes = [d["code"] for d in resp.json()["data"]]
    assert "CSE" in codes
    assert "MECH" in codes


# ── POST /departments/ — IT only ──────────────────────────────────────────────

@pytest.mark.django_db
def test_create_department_with_code_and_name(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/departments/", {"code": "cse", "name": "Computer Science"})
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["code"] == "CSE"  # uppercased
    assert data["name"] == "Computer Science"
    assert data["is_active"] is True


@pytest.mark.django_db
def test_create_department_without_name_is_allowed(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/departments/", {"code": "AI"})
    assert resp.status_code == 201
    assert resp.json()["data"]["name"] == ""


@pytest.mark.django_db
def test_create_department_duplicate_code_returns_400(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    _post(token, f"{BASE}/departments/", {"code": "CSE"})
    resp = _post(token, f"{BASE}/departments/", {"code": "cse"})
    assert resp.status_code == 400
    assert "code" in resp.json()["errors"]


@pytest.mark.django_db
def test_create_department_missing_code_returns_400(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/departments/", {"name": "No Code"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_department_auto_stamps_institution_id(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/departments/", {"code": "CSE"})
    assert resp.status_code == 201
    dept = Department.objects.get(code="CSE")
    assert dept.institution_id == it_user.institution_id


@pytest.mark.django_db
def test_create_department_blocked_for_admin(admin_user):
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/departments/", {"code": "CSE"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_department_blocked_for_super_admin(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/departments/", {"code": "CSE"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_department_blocked_for_unauthenticated():
    resp = _post_unauthed(f"{BASE}/departments/", {"code": "CSE"})
    assert resp.status_code == 401


# ── GET /departments/<pk>/ ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_department_detail_as_it(it_user):
    dept = _make_department("CSE", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _get(token, f"{BASE}/departments/{dept.id}/")
    assert resp.status_code == 200
    assert resp.json()["data"]["code"] == "CSE"


@pytest.mark.django_db
def test_get_department_detail_nonexistent_returns_404(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _get(token, f"{BASE}/departments/{uuid.uuid4()}/")
    assert resp.status_code == 404


# ── PATCH /departments/<pk>/ — IT only, code not editable ────────────────────

@pytest.mark.django_db
def test_edit_department_name_as_it(it_user):
    dept = _make_department("CSE", name="Old Name", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _patch(token, f"{BASE}/departments/{dept.id}/", {"name": "New Name"})
    assert resp.status_code == 200
    dept.refresh_from_db()
    assert dept.name == "New Name"


@pytest.mark.django_db
def test_deactivate_and_reactivate_department_as_it(it_user):
    dept = _make_department("CSE", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")

    resp = _patch(token, f"{BASE}/departments/{dept.id}/", {"is_active": False})
    assert resp.status_code == 200
    dept.refresh_from_db()
    assert dept.is_active is False

    resp = _patch(token, f"{BASE}/departments/{dept.id}/", {"is_active": True})
    assert resp.status_code == 200
    dept.refresh_from_db()
    assert dept.is_active is True


@pytest.mark.django_db
def test_patch_department_ignores_code_field(it_user):
    """code is immutable after creation — sending it in the PATCH body must
    not change it (other services match against the original string)."""
    dept = _make_department("CSE", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _patch(token, f"{BASE}/departments/{dept.id}/", {"code": "HACKED", "name": "Renamed"})
    assert resp.status_code == 200
    dept.refresh_from_db()
    assert dept.code == "CSE"
    assert dept.name == "Renamed"


@pytest.mark.django_db
def test_patch_department_blocked_for_admin(admin_user):
    dept = _make_department("CSE", institution_id=admin_user.institution_id)
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    resp = _patch(token, f"{BASE}/departments/{dept.id}/", {"name": "Hacked"})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_patch_nonexistent_department_returns_404(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _patch(token, f"{BASE}/departments/{uuid.uuid4()}/", {"is_active": False})
    assert resp.status_code == 404


# ── DELETE /departments/<pk>/ — IT only ───────────────────────────────────────

@pytest.mark.django_db
def test_delete_department_as_it(it_user):
    dept = _make_department("CSE", institution_id=it_user.institution_id)
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _delete(token, f"{BASE}/departments/{dept.id}/")
    assert resp.status_code == 200
    assert not Department.objects.filter(pk=dept.id).exists()


@pytest.mark.django_db
def test_delete_department_blocked_for_super_admin(super_admin_user):
    dept = _make_department("CSE", institution_id=super_admin_user.institution_id)
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _delete(token, f"{BASE}/departments/{dept.id}/")
    assert resp.status_code == 403
    assert Department.objects.filter(pk=dept.id).exists()


@pytest.mark.django_db
def test_delete_nonexistent_department_returns_404(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _delete(token, f"{BASE}/departments/{uuid.uuid4()}/")
    assert resp.status_code == 404


# ── Cross-role sanity ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_department_management_blocked_for_student(student_user):
    c = Client()
    login_resp = c.post(
        f"{BASE}/login/",
        data=json.dumps({"student_id": "S001", "password": settings.STUDENT_DEFAULT_PASSWORD, "role": "student"}),
        content_type="application/json",
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["data"]["access_token"]
    assert _get(token, f"{BASE}/departments/").status_code == 403
