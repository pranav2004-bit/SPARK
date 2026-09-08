"""
Tests for the IT Dead-Letter Queue API.

Moved from Super Admin to IT (2026-08-18) — same endpoints, ownership
transferred wholesale, not duplicated. Super Admin is now explicitly
locked out (see the `test_returns_403_for_super_admin` cases below),
same as Admin already was.

Endpoints under test
--------------------
GET  /api/users/admin/outbox/dead-letters/           — list dead-letter events
POST /api/users/admin/outbox/dead-letters/<id>/retry/ — manually retry an event
GET  /api/users/admin/outbox/health/                 — status counts

Coverage
--------
Positive cases
  - Dead-letter list returns only dead_letter events, paginated.
  - Retry resets status to pending and clears retry_after / last_error.
  - Retry response body contains the updated serialized event.
  - Health returns correct counts for each status.

Negative cases
  - List returns 403 for admin and for super_admin (IT-only now).
  - List returns 403 for student.
  - List returns 401 for unauthenticated.
  - Retry returns 404 for a non-existent event.
  - Retry returns 404 for an event that is not dead_letter (pending/done/processing).
  - Retry returns 403 for admin and for super_admin.
  - Retry returns 401 for unauthenticated.
  - Health returns 403 for admin and for super_admin.
  - Health returns 401 for unauthenticated.

Edge cases
  - Dead-letter list excludes pending, done, processing events.
  - Dead-letter list is empty when no dead_letter events exist.
  - Health returns all-zero counts when the table is empty.
  - Health correctly accumulates counts across multiple events of the same status.
  - Retried event is picked up by process_batch on the next poll.
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from tests.conftest import INSTITUTION_A, STUDENT_USER_ID


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_event(status="dead_letter", student_id="STU001", attempts=10,
                last_error="conn refused", retry_after=None):
    from users.models import OutboxEvent
    return OutboxEvent.objects.create(
        event_type=OutboxEvent.EventType.DELETE_STUDENT_AUTH,
        payload={
            "version": 1,
            "student_id": student_id,
            "user_id": str(uuid.uuid4()),
        },
        status=status,
        attempts=attempts,
        last_error=last_error,
        retry_after=retry_after,
    )


# ── GET /admin/outbox/dead-letters/ — positive ────────────────────────────────

@pytest.mark.django_db
class TestDeadLetterListPositive:

    def test_returns_dead_letter_events(self, it_client, db):
        from users.models import OutboxEvent
        _make_event(status="dead_letter", student_id="STU_DL")
        resp = it_client.get("/api/users/admin/outbox/dead-letters/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["student_id"] == "STU_DL"

    def test_response_shape_matches_serializer(self, it_client, db):
        ev = _make_event()
        resp = it_client.get("/api/users/admin/outbox/dead-letters/")
        assert resp.status_code == 200
        result = resp.json()["results"][0]
        for field in ("id", "event_type", "payload", "student_id",
                      "attempts", "last_error", "created_at", "last_attempted_at"):
            assert field in result, f"Missing field: {field}"

    def test_results_ordered_newest_first(self, it_client, db):
        from users.models import OutboxEvent
        ev1 = _make_event(student_id="FIRST")
        ev2 = _make_event(student_id="SECOND")
        # Backdate ev1 so ev2 is newer.
        OutboxEvent.objects.filter(pk=ev1.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )
        resp = it_client.get("/api/users/admin/outbox/dead-letters/")
        results = resp.json()["results"]
        assert results[0]["student_id"] == "SECOND"
        assert results[1]["student_id"] == "FIRST"

    def test_pagination_is_applied(self, it_client, db):
        for i in range(3):
            _make_event(student_id=f"STU{i:03d}")
        resp = it_client.get("/api/users/admin/outbox/dead-letters/?page_size=2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 3
        assert len(body["results"]) == 2

    def test_empty_when_no_dead_letter_events(self, it_client, db):
        resp = it_client.get("/api/users/admin/outbox/dead-letters/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["results"] == []


# ── GET /admin/outbox/dead-letters/ — negative / edge ────────────────────────

@pytest.mark.django_db
class TestDeadLetterListNegative:

    def test_excludes_pending_events(self, it_client, db):
        _make_event(status="pending", student_id="PENDING_STU", attempts=3)
        resp = it_client.get("/api/users/admin/outbox/dead-letters/")
        assert resp.json()["count"] == 0

    def test_excludes_done_events(self, it_client, db):
        _make_event(status="done", student_id="DONE_STU", attempts=1, last_error="")
        resp = it_client.get("/api/users/admin/outbox/dead-letters/")
        assert resp.json()["count"] == 0

    def test_excludes_processing_events(self, it_client, db):
        _make_event(status="processing", student_id="PROC_STU", attempts=5)
        resp = it_client.get("/api/users/admin/outbox/dead-letters/")
        assert resp.json()["count"] == 0

    def test_returns_403_for_admin(self, admin_client, db):
        resp = admin_client.get("/api/users/admin/outbox/dead-letters/")
        assert resp.status_code == 403

    def test_returns_403_for_super_admin(self, super_admin_client, db):
        """Moved to IT — super_admin (the previous owner) is now locked out too."""
        resp = super_admin_client.get("/api/users/admin/outbox/dead-letters/")
        assert resp.status_code == 403

    def test_returns_403_for_student(self, student_client, db):
        resp = student_client.get("/api/users/admin/outbox/dead-letters/")
        assert resp.status_code == 403

    def test_returns_401_for_unauthenticated(self, anon_client, db):
        resp = anon_client.get("/api/users/admin/outbox/dead-letters/")
        assert resp.status_code == 401


# ── POST /admin/outbox/dead-letters/<pk>/retry/ — positive ───────────────────

@pytest.mark.django_db
class TestDeadLetterRetryPositive:

    def test_resets_status_to_pending(self, it_client, db):
        from users.models import OutboxEvent
        ev = _make_event(status="dead_letter")
        resp = it_client.post(
            f"/api/users/admin/outbox/dead-letters/{ev.id}/retry/"
        )
        assert resp.status_code == 200
        ev.refresh_from_db()
        assert ev.status == OutboxEvent.Status.PENDING

    def test_clears_retry_after(self, it_client, db):
        future = timezone.now() + timedelta(hours=1)
        ev = _make_event(status="dead_letter", retry_after=future)
        it_client.post(
            f"/api/users/admin/outbox/dead-letters/{ev.id}/retry/"
        )
        ev.refresh_from_db()
        assert ev.retry_after is None

    def test_clears_last_error(self, it_client, db):
        ev = _make_event(status="dead_letter", last_error="SMTP error")
        it_client.post(
            f"/api/users/admin/outbox/dead-letters/{ev.id}/retry/"
        )
        ev.refresh_from_db()
        assert ev.last_error == ""

    def test_response_contains_updated_event(self, it_client, db):
        ev = _make_event(status="dead_letter")
        resp = it_client.post(
            f"/api/users/admin/outbox/dead-letters/{ev.id}/retry/"
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["id"] == str(ev.id)

    def test_retried_event_is_picked_up_by_worker(self, it_client, db):
        from unittest.mock import patch
        from users.models import OutboxEvent
        from users.outbox import process_batch

        ev = _make_event(status="dead_letter")
        it_client.post(
            f"/api/users/admin/outbox/dead-letters/{ev.id}/retry/"
        )
        with patch("core.auth_client.delete_student_auth_by_user_id") as mock_fn:
            count = process_batch()
        assert count == 1
        ev.refresh_from_db()
        assert ev.status == OutboxEvent.Status.DONE


# ── POST /admin/outbox/dead-letters/<pk>/retry/ — negative ───────────────────

@pytest.mark.django_db
class TestDeadLetterRetryNegative:

    def test_returns_404_for_nonexistent_event(self, it_client, db):
        random_id = uuid.uuid4()
        resp = it_client.post(
            f"/api/users/admin/outbox/dead-letters/{random_id}/retry/"
        )
        assert resp.status_code == 404

    def test_returns_404_for_pending_event(self, it_client, db):
        ev = _make_event(status="pending", attempts=3)
        resp = it_client.post(
            f"/api/users/admin/outbox/dead-letters/{ev.id}/retry/"
        )
        assert resp.status_code == 404

    def test_returns_404_for_done_event(self, it_client, db):
        ev = _make_event(status="done", attempts=1, last_error="")
        resp = it_client.post(
            f"/api/users/admin/outbox/dead-letters/{ev.id}/retry/"
        )
        assert resp.status_code == 404

    def test_returns_404_for_processing_event(self, it_client, db):
        ev = _make_event(status="processing", attempts=5)
        resp = it_client.post(
            f"/api/users/admin/outbox/dead-letters/{ev.id}/retry/"
        )
        assert resp.status_code == 404

    def test_returns_403_for_admin(self, admin_client, db):
        ev = _make_event(status="dead_letter")
        resp = admin_client.post(
            f"/api/users/admin/outbox/dead-letters/{ev.id}/retry/"
        )
        assert resp.status_code == 403

    def test_returns_403_for_super_admin(self, super_admin_client, db):
        """Moved to IT — super_admin (the previous owner) is now locked out too."""
        ev = _make_event(status="dead_letter")
        resp = super_admin_client.post(
            f"/api/users/admin/outbox/dead-letters/{ev.id}/retry/"
        )
        assert resp.status_code == 403

    def test_returns_401_for_unauthenticated(self, anon_client, db):
        ev = _make_event(status="dead_letter")
        resp = anon_client.post(
            f"/api/users/admin/outbox/dead-letters/{ev.id}/retry/"
        )
        assert resp.status_code == 401


# ── GET /admin/outbox/health/ — positive ─────────────────────────────────────

@pytest.mark.django_db
class TestOutboxHealthPositive:

    def test_returns_all_zero_when_empty(self, it_client, db):
        resp = it_client.get("/api/users/admin/outbox/health/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data == {"pending": 0, "processing": 0, "done": 0, "dead_letter": 0}

    def test_counts_each_status_correctly(self, it_client, db):
        _make_event(status="pending",    attempts=1, last_error="")
        _make_event(status="pending",    attempts=2, last_error="")
        _make_event(status="processing", attempts=3)
        _make_event(status="done",       attempts=1, last_error="")
        _make_event(status="dead_letter")
        _make_event(status="dead_letter")

        resp = it_client.get("/api/users/admin/outbox/health/")
        data = resp.json()["data"]
        assert data["pending"] == 2
        assert data["processing"] == 1
        assert data["done"] == 1
        assert data["dead_letter"] == 2

    def test_response_has_success_true(self, it_client, db):
        resp = it_client.get("/api/users/admin/outbox/health/")
        assert resp.json()["success"] is True


# ── GET /admin/outbox/health/ — negative ─────────────────────────────────────

@pytest.mark.django_db
class TestOutboxHealthNegative:

    def test_returns_403_for_admin(self, admin_client, db):
        resp = admin_client.get("/api/users/admin/outbox/health/")
        assert resp.status_code == 403

    def test_returns_403_for_super_admin(self, super_admin_client, db):
        """Moved to IT — super_admin (the previous owner) is now locked out too."""
        resp = super_admin_client.get("/api/users/admin/outbox/health/")
        assert resp.status_code == 403

    def test_returns_403_for_student(self, student_client, db):
        resp = student_client.get("/api/users/admin/outbox/health/")
        assert resp.status_code == 403

    def test_returns_401_for_unauthenticated(self, anon_client, db):
        resp = anon_client.get("/api/users/admin/outbox/health/")
        assert resp.status_code == 401
