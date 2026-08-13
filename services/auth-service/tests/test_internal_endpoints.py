"""
Tests for internal service-to-service endpoints (user-service → auth-service).

Endpoints covered:
  POST   /api/auth/internal/students/                      — create student auth account
  PATCH  /api/auth/internal/students/<student_id>/         — update is_active
  DELETE /api/auth/internal/students/<student_id>/delete/  — permanently delete account

All endpoints are protected by IsInternalService (X-Service-Key header).
The module-level `apply_service_key` autouse fixture sets settings.SERVICE_KEY
so permission checks pass in tests.
"""

import json
import uuid
import pytest
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()

BASE = "/api/auth/internal"
_SERVICE_KEY = "test-internal-service-key-for-pytest"


# ── Module-level autouse: set SERVICE_KEY for every test in this file ─────────

@pytest.fixture(autouse=True)
def apply_service_key(settings):
    settings.SERVICE_KEY = _SERVICE_KEY


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _post(url, data, key=_SERVICE_KEY):
    c = Client()
    return c.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
        HTTP_X_SERVICE_KEY=key,
    )


def _patch(url, data, key=_SERVICE_KEY):
    c = Client()
    return c.patch(
        url,
        data=json.dumps(data),
        content_type="application/json",
        HTTP_X_SERVICE_KEY=key,
    )


def _delete(url, key=_SERVICE_KEY):
    c = Client()
    return c.delete(url, HTTP_X_SERVICE_KEY=key)


def _make_student(student_id, is_active=True):
    """Create a student auth User directly in the DB."""
    return User.objects.create(
        id=uuid.uuid4(),
        student_id=student_id,
        role="student",
        is_active=is_active,
        institution_id=uuid.uuid4(),
    )


# ── InternalStudentCreateView ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestInternalStudentCreate:

    def test_creates_auth_account_and_returns_201(self):
        user_id = str(uuid.uuid4())
        resp = _post(f"{BASE}/students/", {
            "user_id": user_id,
            "student_id": "INT001",
            "institution_id": str(uuid.uuid4()),
        })
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["student_id"] == "INT001"
        u = User.objects.get(student_id="INT001")
        assert u.email == "int001@students.internal"

    def test_multiple_students_can_be_created_without_email_conflict(self):
        """
        Regression: each student must get a unique internal email derived from
        their student_id so the unique constraint on the email column is never
        violated when creating more than one student.
        """
        for sid in ("MULTI001", "MULTI002", "MULTI003"):
            resp = _post(f"{BASE}/students/", {
                "user_id": str(uuid.uuid4()),
                "student_id": sid,
                "institution_id": str(uuid.uuid4()),
            })
            assert resp.status_code == 201, (
                f"Expected 201 for {sid}, got {resp.status_code}: {resp.json()}"
            )
        assert User.objects.filter(role="student").count() == 3

    def test_missing_user_id_returns_400(self):
        resp = _post(f"{BASE}/students/", {"student_id": "INT002"})
        assert resp.status_code == 400

    def test_missing_student_id_returns_400(self):
        resp = _post(f"{BASE}/students/", {"user_id": str(uuid.uuid4())})
        assert resp.status_code == 400

    def test_missing_institution_id_returns_400(self):
        """institution_id is a NOT NULL database column — must be validated explicitly
        with a clear 400, not left to crash as a confusing 500 IntegrityError."""
        resp = _post(f"{BASE}/students/", {"user_id": str(uuid.uuid4()), "student_id": "NOINST01"})
        assert resp.status_code == 400
        assert "institution_id" in resp.json()["message"]

    def test_replaces_active_orphan_instead_of_409(self):
        """
        When an active auth account exists for a student_id but the incoming
        user_id is different, the old student was deleted in user-service but
        auth cleanup failed (non-fatal path).  The endpoint must replace the
        stale account rather than returning 409 — user-service is the source
        of truth for student existence.
        """
        _make_student("INT003", is_active=True)
        new_id = str(uuid.uuid4())
        resp = _post(f"{BASE}/students/", {
            "user_id": new_id,
            "student_id": "INT003",
            "institution_id": str(uuid.uuid4()),
        })
        assert resp.status_code == 201, (
            f"Expected 201 (active orphan replaced), got {resp.status_code}: {resp.json()}"
        )
        users = User.objects.filter(student_id="INT003")
        assert users.count() == 1
        assert str(users.first().id) == new_id

    def test_idempotent_on_same_user_id(self):
        """
        If the same user_id is sent twice (e.g. client timed out after the
        first attempt succeeded), the endpoint must return 201 instead of
        crashing with a primary-key conflict.
        """
        user_id = str(uuid.uuid4())
        institution_id = str(uuid.uuid4())
        # First call — creates the account.
        r1 = _post(f"{BASE}/students/", {"user_id": user_id, "student_id": "IDEM001", "institution_id": institution_id})
        assert r1.status_code == 201
        # Second call with the same user_id — must succeed idempotently.
        r2 = _post(f"{BASE}/students/", {"user_id": user_id, "student_id": "IDEM001", "institution_id": institution_id})
        assert r2.status_code == 201
        # Still only one account in the DB.
        assert User.objects.filter(student_id="IDEM001").count() == 1

    def test_replaces_inactive_orphan_instead_of_409(self):
        """
        Core regression test for Issue 3.

        When an auth account exists for a student_id but is inactive (orphan
        from a legacy soft-delete), the endpoint must delete the stale account
        and create a fresh one — NOT return 409.
        """
        _make_student("GHOST01", is_active=False)
        assert User.objects.filter(student_id="GHOST01", is_active=False).exists()

        new_id = str(uuid.uuid4())
        resp = _post(f"{BASE}/students/", {
            "user_id": new_id,
            "student_id": "GHOST01",
            "institution_id": str(uuid.uuid4()),
        })

        assert resp.status_code == 201, (
            f"Expected 201 (orphan replaced), got {resp.status_code}: {resp.json()}"
        )
        # Exactly one auth account for GHOST01, and it is the new active one.
        users = User.objects.filter(student_id="GHOST01")
        assert users.count() == 1
        u = users.first()
        assert u.is_active is True
        assert str(u.id) == new_id

    def test_no_service_key_returns_403(self):
        resp = _post(f"{BASE}/students/", {
            "user_id": str(uuid.uuid4()),
            "student_id": "NOKEY",
        }, key="")
        assert resp.status_code == 403

    def test_wrong_service_key_returns_403(self):
        resp = _post(f"{BASE}/students/", {
            "user_id": str(uuid.uuid4()),
            "student_id": "WRONGKEY",
        }, key="not-the-right-key")
        assert resp.status_code == 403


# ── InternalStudentUpdateView ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestInternalStudentUpdate:

    def test_deactivates_active_student(self):
        _make_student("UPD001", is_active=True)
        resp = _patch(f"{BASE}/students/UPD001/", {"is_active": False})
        assert resp.status_code == 200
        assert User.objects.get(student_id="UPD001").is_active is False

    def test_reactivates_inactive_student(self):
        _make_student("UPD002", is_active=False)
        resp = _patch(f"{BASE}/students/UPD002/", {"is_active": True})
        assert resp.status_code == 200
        assert User.objects.get(student_id="UPD002").is_active is True

    def test_missing_is_active_field_returns_400(self):
        _make_student("UPD003")
        resp = _patch(f"{BASE}/students/UPD003/", {})
        assert resp.status_code == 400

    def test_nonexistent_student_returns_404(self):
        resp = _patch(f"{BASE}/students/NOBODY/", {"is_active": False})
        assert resp.status_code == 404

    def test_no_service_key_returns_403(self):
        _make_student("UPD004")
        resp = _patch(f"{BASE}/students/UPD004/", {"is_active": False}, key="")
        assert resp.status_code == 403


# ── InternalStudentDeleteView ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestInternalStudentDelete:

    def test_deletes_existing_student(self):
        _make_student("DEL001")
        resp = _delete(f"{BASE}/students/DEL001/delete/")
        assert resp.status_code == 200
        assert not User.objects.filter(student_id="DEL001").exists()

    def test_delete_nonexistent_is_idempotent(self):
        """Deleting an already-absent account must return 200, not 404."""
        resp = _delete(f"{BASE}/students/NOBODY/delete/")
        assert resp.status_code == 200

    def test_no_service_key_returns_403(self):
        _make_student("DEL002")
        resp = _delete(f"{BASE}/students/DEL002/delete/", key="")
        assert resp.status_code == 403

    def test_delete_with_matching_expected_user_id_deletes(self):
        """
        When expected_user_id matches the existing auth account, the account
        is deleted and 200 is returned.
        """
        user = _make_student("DEL003")
        c = Client()
        resp = c.delete(
            f"{BASE}/students/DEL003/delete/",
            data=json.dumps({"expected_user_id": str(user.id)}),
            content_type="application/json",
            HTTP_X_SERVICE_KEY=_SERVICE_KEY,
        )
        assert resp.status_code == 200
        assert not User.objects.filter(student_id="DEL003").exists()

    def test_delete_with_mismatched_expected_user_id_skips(self):
        """
        When expected_user_id does NOT match (student was deleted then
        re-added with a new user_id), the existing account must NOT be deleted.
        This prevents the outbox worker from removing a newly re-created account.
        """
        user = _make_student("DEL004")
        wrong_user_id = str(uuid.uuid4())  # different from user.id

        c = Client()
        resp = c.delete(
            f"{BASE}/students/DEL004/delete/",
            data=json.dumps({"expected_user_id": wrong_user_id}),
            content_type="application/json",
            HTTP_X_SERVICE_KEY=_SERVICE_KEY,
        )
        assert resp.status_code == 200
        # Account must still exist — it belongs to the re-created student.
        assert User.objects.filter(student_id="DEL004").exists()

    def test_delete_without_expected_user_id_deletes_by_student_id(self):
        """
        Backward-compatible: omitting expected_user_id deletes by student_id
        (used by maintenance commands such as cleanup_ghost_students).
        """
        _make_student("DEL005")
        resp = _delete(f"{BASE}/students/DEL005/delete/")
        assert resp.status_code == 200
        assert not User.objects.filter(student_id="DEL005").exists()
