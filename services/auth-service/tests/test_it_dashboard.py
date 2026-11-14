"""
Tests for the IT Dashboard stats endpoint.

Endpoint covered:
  GET /api/auth/dashboard-stats/ — IT only. Institution-wide totals for
  departments, admins (with a per-department breakdown), and super admins.
  Deliberately uncached (user decision, 2026-11-14): must reflect the real
  database state on every single request.
"""

import json
import uuid
import pytest
from django.test import Client
from django.contrib.auth import get_user_model

from authentication.models import Department
from .conftest import INSTITUTION_ID

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


def _dept(code, institution_id=INSTITUTION_ID, is_active=True, name=""):
    return Department.objects.create(code=code, name=name, institution_id=institution_id, is_active=is_active)


def _admin(email, department, institution_id=INSTITUTION_ID, is_active=True):
    u = User.objects.create_user(
        email=email, password="Admin@pass1", role="admin",
        department=department, institution_id=institution_id,
    )
    if not is_active:
        u.is_active = False
        u.save(update_fields=["is_active"])
    return u


def _super_admin(email, institution_id=INSTITUTION_ID, is_active=True):
    u = User.objects.create_user(
        email=email, password="Super@pass1", role="super_admin", institution_id=institution_id,
    )
    if not is_active:
        u.is_active = False
        u.save(update_fields=["is_active"])
    return u


# ── Access control ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_it_can_access(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _get(token, f"{BASE}/dashboard-stats/")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.django_db
def test_admin_forbidden(admin_user):
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    resp = _get(token, f"{BASE}/dashboard-stats/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_super_admin_forbidden(super_admin_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _get(token, f"{BASE}/dashboard-stats/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_anon_unauthorized():
    resp = Client().get(f"{BASE}/dashboard-stats/", content_type="application/json")
    assert resp.status_code == 401


# ── Counts ────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_department_counts(it_user):
    _dept("CSE", is_active=True)
    _dept("ECE", is_active=True)
    _dept("MECH", is_active=False)

    token = _login_token("it@test.com", "It@pass123", "it")
    data = _get(token, f"{BASE}/dashboard-stats/").json()["data"]

    assert data["departments"]["total"] == 3
    assert data["departments"]["active"] == 2
    assert data["departments"]["inactive"] == 1
    codes = {row["code"] for row in data["departments"]["list"]}
    assert codes == {"CSE", "ECE", "MECH"}
    # The inactive one is still listed, not hidden — the frontend needs
    # every real department (even an inactive one) to merge against
    # user-service's student-by-department breakdown.
    mech = next(row for row in data["departments"]["list"] if row["code"] == "MECH")
    assert mech["is_active"] is False


@pytest.mark.django_db
def test_admin_counts_and_department_breakdown(it_user):
    _admin("a1@test.com", "CSE", is_active=True)
    _admin("a2@test.com", "CSE", is_active=False)
    _admin("a3@test.com", "ECE", is_active=True)

    token = _login_token("it@test.com", "It@pass123", "it")
    data = _get(token, f"{BASE}/dashboard-stats/").json()["data"]

    assert data["admins"]["total"] == 3
    assert data["admins"]["active"] == 2
    assert data["admins"]["inactive"] == 1

    by_dept = {row["department"]: row for row in data["admins"]["by_department"]}
    assert by_dept["CSE"] == {"department": "CSE", "total": 2, "active": 1, "inactive": 1}
    assert by_dept["ECE"] == {"department": "ECE", "total": 1, "active": 1, "inactive": 0}


@pytest.mark.django_db
def test_super_admin_counts(it_user):
    _super_admin("sa1@test.com", is_active=True)
    _super_admin("sa2@test.com", is_active=False)

    token = _login_token("it@test.com", "It@pass123", "it")
    data = _get(token, f"{BASE}/dashboard-stats/").json()["data"]

    assert data["super_admins"]["total"] == 2
    assert data["super_admins"]["active"] == 1
    assert data["super_admins"]["inactive"] == 1


@pytest.mark.django_db
def test_scoped_to_callers_own_institution(it_user):
    other_institution = uuid.uuid4()
    _dept("CSE", institution_id=INSTITUTION_ID)
    _dept("OTHER", institution_id=other_institution)
    _admin("mine@test.com", "CSE", institution_id=INSTITUTION_ID)
    _admin("theirs@test.com", "OTHER", institution_id=other_institution)
    _super_admin("mine-sa@test.com", institution_id=INSTITUTION_ID)
    _super_admin("theirs-sa@test.com", institution_id=other_institution)

    token = _login_token("it@test.com", "It@pass123", "it")
    data = _get(token, f"{BASE}/dashboard-stats/").json()["data"]

    assert data["departments"]["total"] == 1
    assert data["admins"]["total"] == 1
    assert data["super_admins"]["total"] == 1


@pytest.mark.django_db
def test_reflects_the_real_current_state_not_a_stale_cache(it_user):
    # The explicit "100% accuracy, updates automatically" requirement —
    # verified directly: create something new between two calls and
    # confirm the second call sees it, proving there's no cache.
    token = _login_token("it@test.com", "It@pass123", "it")

    before = _get(token, f"{BASE}/dashboard-stats/").json()["data"]
    assert before["departments"]["total"] == 0

    _dept("CSE")
    after = _get(token, f"{BASE}/dashboard-stats/").json()["data"]
    assert after["departments"]["total"] == 1
