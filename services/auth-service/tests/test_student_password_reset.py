"""
Tests for StudentPasswordResetView (/api/auth/student/<student_id>/reset-password/).

Exclusive to IT (2026-08-19) — student account management is IT's
responsibility; Admin is read/query-only and must be blocked here just like
on every other Batches/Students write endpoint. No coverage existed for this
endpoint prior to this change.
"""

import json

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

from .test_admin_management import _login_token, _post, _post_unauthed

User = get_user_model()

BASE = "/api/auth"


def _student_login_token(student_id, password):
    """Student login authenticates by student_id, not email — _login_token
    (test_admin_management.py) only supports the email-based admin/super_admin/
    it login shape, so this mirrors it for the student payload shape."""
    client = Client()
    resp = client.post(
        f"{BASE}/login/",
        data=json.dumps({"student_id": student_id, "password": password, "role": "student"}),
        content_type="application/json",
    )
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["data"]["access_token"]


@pytest.mark.django_db
def test_it_can_reset_student_password(it_user, student_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/student/{student_user.student_id}/reset-password/", {})
    assert resp.status_code == 200

    student_user.refresh_from_db()
    assert student_user.check_password(settings.STUDENT_DEFAULT_PASSWORD)
    assert student_user.force_password_change is True


@pytest.mark.django_db
def test_admin_blocked_from_resetting_student_password(admin_user, student_user):
    token = _login_token("admin@test.com", "Admin@pass1", "admin")
    resp = _post(token, f"{BASE}/student/{student_user.student_id}/reset-password/", {})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_super_admin_blocked_from_resetting_student_password(super_admin_user, student_user):
    token = _login_token("superadmin@test.com", "Super@pass1", "super_admin")
    resp = _post(token, f"{BASE}/student/{student_user.student_id}/reset-password/", {})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_student_blocked_from_resetting_own_password(student_user):
    token = _student_login_token(student_user.student_id, settings.STUDENT_DEFAULT_PASSWORD)
    resp = _post(token, f"{BASE}/student/{student_user.student_id}/reset-password/", {})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_reset_requires_auth(student_user):
    resp = _post_unauthed(f"{BASE}/student/{student_user.student_id}/reset-password/", {})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_it_cannot_reset_other_institution_student(it_user):
    import uuid
    other_institution = uuid.uuid4()
    other_student = User.objects.create_user(
        email="s999@aptlogic.internal",
        password=settings.STUDENT_DEFAULT_PASSWORD,
        role="student",
        student_id="S999",
        institution_id=other_institution,
    )
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/student/{other_student.student_id}/reset-password/", {})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_reset_nonexistent_student_404(it_user):
    token = _login_token("it@test.com", "It@pass123", "it")
    resp = _post(token, f"{BASE}/student/NOSUCH001/reset-password/", {})
    assert resp.status_code == 404
