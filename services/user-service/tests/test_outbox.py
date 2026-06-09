"""
Tests for the Outbox pattern implementation.

Coverage
--------
Positive cases
  - Deleting a student creates an OutboxEvent atomically (same transaction).
  - The event payload contains version, student_id, and user_id.
  - process_batch delivers the event to auth-service and marks it DONE.
  - cleanup_outbox removes old DONE events.

Negative cases
  - A transient auth-service failure retries with exponential backoff.
  - After MAX_ATTEMPTS failures the event becomes DEAD_LETTER.
  - A worker crash (stuck PROCESSING event) is detected and re-queued.

Edge cases
  - Events with a future retry_after are not picked up until they are due.
  - An event whose auth-service call succeeds on the second attempt becomes DONE.
  - cleanup_outbox never deletes DEAD_LETTER or PENDING events.
  - cleanup_outbox never deletes recent DONE events within the retention window.
  - delete-then-re-add: process_batch calls auth-service with the original
    user_id so auth-service can skip accounts that were re-created.
"""

import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest
from django.core import mail as django_mail
from django.core.management import call_command
from django.utils import timezone

from tests.conftest import INSTITUTION_A, STUDENT_USER_ID

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_outbox_event(event_type="delete_student_auth", status="pending",
                       student_id="STU001", user_id=None, attempts=0,
                       retry_after=None, processed_at=None):
    from users.models import OutboxEvent
    return OutboxEvent.objects.create(
        event_type=event_type,
        payload={
            "version": 1,
            "student_id": student_id,
            "user_id": str(user_id or uuid.uuid4()),
        },
        status=status,
        attempts=attempts,
        retry_after=retry_after,
        processed_at=processed_at,
    )


# ── Delete view: atomic outbox write ──────────────────────────────────────────

@pytest.mark.django_db
class TestDeleteViewCreatesOutboxEvent:

    def test_delete_creates_outbox_event(self, admin_client, student):
        from users.models import OutboxEvent

        pk = student.pk
        resp = admin_client.delete(f"/api/users/students/{pk}/")

        assert resp.status_code == 200
        assert OutboxEvent.objects.count() == 1

    def test_outbox_event_has_correct_payload(self, admin_client, student):
        from users.models import OutboxEvent, Student

        pk = student.pk
        student_id = student.student_id
        user_id = str(student.user_id)

        admin_client.delete(f"/api/users/students/{pk}/")

        event = OutboxEvent.objects.get()
        assert event.event_type == OutboxEvent.EventType.DELETE_STUDENT_AUTH
        assert event.status == OutboxEvent.Status.PENDING
        assert event.attempts == 0
        assert event.payload["version"] == 1
        assert event.payload["student_id"] == student_id
        assert event.payload["user_id"] == user_id

    def test_delete_and_outbox_are_atomic(self, admin_client, student):
        """
        If the student row is gone from the DB, the outbox event must also
        exist — they are written in the same transaction.
        """
        from users.models import Student, OutboxEvent

        admin_client.delete(f"/api/users/students/{student.pk}/")

        assert not Student.objects.filter(pk=student.pk).exists()
        assert OutboxEvent.objects.count() == 1

    def test_no_direct_auth_call_on_delete(self, admin_client, student):
        """
        The delete view must NOT call delete_student_auth() directly.
        Auth cleanup is delegated entirely to the outbox worker.
        """
        with patch("core.auth_client.delete_student_auth") as mock_delete, \
             patch("core.auth_client.delete_student_auth_by_user_id") as mock_by_id:
            admin_client.delete(f"/api/users/students/{student.pk}/")
            mock_delete.assert_not_called()
            mock_by_id.assert_not_called()


# ── process_batch: success path ───────────────────────────────────────────────

@pytest.mark.django_db
class TestProcessBatchSuccess:

    def test_processes_pending_event_and_marks_done(self, db):
        from users.models import OutboxEvent
        from users.outbox import process_batch

        event = _make_outbox_event()

        with patch("core.auth_client.delete_student_auth_by_user_id") as mock_fn:
            count = process_batch()

        assert count == 1
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DONE
        assert event.processed_at is not None
        assert event.last_error == ""

    def test_calls_auth_service_with_correct_student_id_and_user_id(self, db):
        from users.outbox import process_batch

        uid = str(uuid.uuid4())
        _make_outbox_event(student_id="STU999", user_id=uid)

        with patch("core.auth_client.delete_student_auth_by_user_id") as mock_fn:
            process_batch()

        mock_fn.assert_called_once_with(student_id="STU999", user_id=uid)

    def test_processes_multiple_pending_events(self, db):
        from users.models import OutboxEvent
        from users.outbox import process_batch

        for i in range(3):
            _make_outbox_event(student_id=f"STU{i:03d}")

        with patch("core.auth_client.delete_student_auth_by_user_id"):
            count = process_batch()

        assert count == 3
        assert OutboxEvent.objects.filter(status=OutboxEvent.Status.DONE).count() == 3


# ── process_batch: retry / backoff ────────────────────────────────────────────

@pytest.mark.django_db
class TestProcessBatchRetry:

    def test_failure_keeps_pending_and_sets_retry_after(self, db):
        from users.models import OutboxEvent
        from users.outbox import process_batch

        event = _make_outbox_event()
        before = timezone.now()

        with patch("core.auth_client.delete_student_auth_by_user_id",
                   side_effect=RuntimeError("Connection refused")):
            process_batch()

        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.PENDING
        assert event.attempts == 1
        assert event.retry_after > before
        assert event.last_error == "Connection refused"

    def test_retry_after_increases_exponentially(self, db):
        """
        First failure: retry_after ≈ now + 30s
        Second failure: retry_after ≈ now + 60s
        """
        from users.outbox import process_batch, BACKOFF_BASE_SECONDS

        event = _make_outbox_event()

        with patch("core.auth_client.delete_student_auth_by_user_id",
                   side_effect=RuntimeError("err")):
            process_batch()

        event.refresh_from_db()
        assert event.attempts == 1
        delay_1 = (event.retry_after - timezone.now()).total_seconds()
        # Should be roughly BACKOFF_BASE_SECONDS (30s) — allow ±5s tolerance.
        assert BACKOFF_BASE_SECONDS - 5 < delay_1 <= BACKOFF_BASE_SECONDS + 5

        # Manually make it eligible again.
        event.retry_after = timezone.now() - timedelta(seconds=1)
        event.save(update_fields=["retry_after"])

        with patch("core.auth_client.delete_student_auth_by_user_id",
                   side_effect=RuntimeError("err")):
            process_batch()

        event.refresh_from_db()
        assert event.attempts == 2
        delay_2 = (event.retry_after - timezone.now()).total_seconds()
        # Should be roughly 60s (2× backoff base).
        assert BACKOFF_BASE_SECONDS * 2 - 5 < delay_2 <= BACKOFF_BASE_SECONDS * 2 + 5

    def test_event_not_picked_up_before_retry_after(self, db):
        from users.models import OutboxEvent
        from users.outbox import process_batch

        future = timezone.now() + timedelta(hours=1)
        event = _make_outbox_event(status="pending", retry_after=future, attempts=1)

        with patch("core.auth_client.delete_student_auth_by_user_id") as mock_fn:
            count = process_batch()

        assert count == 0
        mock_fn.assert_not_called()
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.PENDING

    def test_event_picked_up_after_retry_after_passes(self, db):
        from users.models import OutboxEvent
        from users.outbox import process_batch

        past = timezone.now() - timedelta(seconds=1)
        _make_outbox_event(status="pending", retry_after=past, attempts=1)

        with patch("core.auth_client.delete_student_auth_by_user_id"):
            count = process_batch()

        assert count == 1

    def test_succeeds_on_second_attempt_after_first_failure(self, db):
        from users.models import OutboxEvent
        from users.outbox import process_batch

        event = _make_outbox_event()

        # First attempt: failure.
        with patch("core.auth_client.delete_student_auth_by_user_id",
                   side_effect=RuntimeError("temporary")):
            process_batch()

        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.PENDING
        assert event.attempts == 1

        # Manually make it eligible again (simulate retry_after passing).
        event.retry_after = timezone.now() - timedelta(seconds=1)
        event.save(update_fields=["retry_after"])

        # Second attempt: success.
        with patch("core.auth_client.delete_student_auth_by_user_id"):
            process_batch()

        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DONE
        assert event.attempts == 2


# ── process_batch: dead letter ────────────────────────────────────────────────

@pytest.mark.django_db
class TestProcessBatchDeadLetter:

    def test_dead_letter_after_max_attempts(self, db):
        from users.models import OutboxEvent
        from users.outbox import process_batch, MAX_ATTEMPTS

        # Simulate an event that has already failed MAX_ATTEMPTS - 1 times.
        event = _make_outbox_event(attempts=MAX_ATTEMPTS - 1)

        with patch("core.auth_client.delete_student_auth_by_user_id",
                   side_effect=RuntimeError("persistent failure")):
            process_batch()

        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DEAD_LETTER
        assert event.attempts == MAX_ATTEMPTS
        assert "persistent failure" in event.last_error

    def test_dead_letter_is_not_retried(self, db):
        from users.models import OutboxEvent
        from users.outbox import process_batch

        event = _make_outbox_event(status="dead_letter", attempts=10)

        with patch("core.auth_client.delete_student_auth_by_user_id") as mock_fn:
            count = process_batch()

        assert count == 0
        mock_fn.assert_not_called()
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DEAD_LETTER


# ── Dead-letter email alerts ───────────────────────────────────────────────────

@pytest.mark.django_db
class TestDeadLetterEmailAlert:

    def test_email_sent_when_event_becomes_dead_letter(self, db):
        """
        Transitioning to dead_letter must send one email via mail_admins().
        test_settings.py configures locmem backend so no real SMTP call is made.
        """
        from users.outbox import process_batch, MAX_ATTEMPTS

        event = _make_outbox_event(attempts=MAX_ATTEMPTS - 1, student_id="STU_DL")

        with patch("core.auth_client.delete_student_auth_by_user_id",
                   side_effect=RuntimeError("permanent failure")):
            process_batch()

        event.refresh_from_db()
        assert event.status == "dead_letter"
        assert len(django_mail.outbox) == 1

    def test_email_not_sent_on_retry(self, db):
        """
        A transient failure that still has attempts remaining must NOT send email.
        """
        from users.outbox import process_batch

        event = _make_outbox_event(attempts=0)

        with patch("core.auth_client.delete_student_auth_by_user_id",
                   side_effect=RuntimeError("temporary failure")):
            process_batch()

        event.refresh_from_db()
        assert event.status == "pending"
        assert len(django_mail.outbox) == 0

    def test_email_subject_contains_student_id(self, db):
        from users.outbox import process_batch, MAX_ATTEMPTS

        event = _make_outbox_event(attempts=MAX_ATTEMPTS - 1, student_id="STU_SUBJ")

        with patch("core.auth_client.delete_student_auth_by_user_id",
                   side_effect=RuntimeError("err")):
            process_batch()

        assert len(django_mail.outbox) == 1
        assert "STU_SUBJ" in django_mail.outbox[0].subject

    def test_email_body_contains_event_id_and_student_id(self, db):
        from users.outbox import process_batch, MAX_ATTEMPTS

        event = _make_outbox_event(attempts=MAX_ATTEMPTS - 1, student_id="STU_BODY")

        with patch("core.auth_client.delete_student_auth_by_user_id",
                   side_effect=RuntimeError("err")):
            process_batch()

        assert len(django_mail.outbox) == 1
        body = django_mail.outbox[0].body
        assert str(event.id) in body
        assert "STU_BODY" in body

    def test_email_failure_does_not_prevent_dead_letter_save(self, db):
        """
        If mail_admins() raises (e.g. misconfigured SMTP), the dead-letter
        status must still be persisted — email failure is logged but swallowed.
        """
        from users.models import OutboxEvent
        from users.outbox import process_batch, MAX_ATTEMPTS

        event = _make_outbox_event(attempts=MAX_ATTEMPTS - 1)

        with patch("core.auth_client.delete_student_auth_by_user_id",
                   side_effect=RuntimeError("err")), \
             patch("django.core.mail.mail_admins",
                   side_effect=Exception("SMTP connection refused")):
            process_batch()

        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DEAD_LETTER


# ── recover_stuck_events ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRecoverStuckEvents:

    def test_recovers_event_stuck_in_processing(self, db):
        from users.models import OutboxEvent
        from users.outbox import recover_stuck_events, STUCK_THRESHOLD_MINUTES

        event = _make_outbox_event(status="processing", attempts=1)
        # Simulate: last_attempted_at was more than STUCK_THRESHOLD_MINUTES ago.
        stuck_time = timezone.now() - timedelta(minutes=STUCK_THRESHOLD_MINUTES + 1)
        OutboxEvent.objects.filter(pk=event.pk).update(last_attempted_at=stuck_time)

        recovered = recover_stuck_events()

        assert recovered == 1
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.PENDING
        assert event.retry_after is None

    def test_does_not_recover_recently_processing_event(self, db):
        from users.models import OutboxEvent
        from users.outbox import recover_stuck_events

        event = _make_outbox_event(status="processing", attempts=1)
        # last_attempted_at defaults to None or now — within the threshold.
        OutboxEvent.objects.filter(pk=event.pk).update(
            last_attempted_at=timezone.now()
        )

        recovered = recover_stuck_events()

        assert recovered == 0
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.PROCESSING

    def test_does_not_recover_done_or_dead_letter(self, db):
        from users.outbox import recover_stuck_events

        _make_outbox_event(status="done", attempts=1)
        _make_outbox_event(status="dead_letter", attempts=10)

        recovered = recover_stuck_events()
        assert recovered == 0


# ── delete-then-re-add edge case ──────────────────────────────────────────────

@pytest.mark.django_db
class TestDeleteThenReAdd:

    def test_outbox_event_carries_original_user_id(self, admin_client, student):
        """
        The payload must contain the user_id of the deleted student, not a
        new one.  auth-service uses this to skip the delete if the student
        has already been re-added with a new account.
        """
        from users.models import OutboxEvent

        original_user_id = str(student.user_id)
        admin_client.delete(f"/api/users/students/{student.pk}/")

        event = OutboxEvent.objects.get()
        assert event.payload["user_id"] == original_user_id

    def test_process_batch_passes_user_id_to_auth_service(self, db):
        """
        The worker must forward the payload's user_id to auth-service so
        auth-service can guard against deleting the wrong account.
        """
        from users.outbox import process_batch

        original_uid = str(uuid.uuid4())
        _make_outbox_event(student_id="STU001", user_id=original_uid)

        with patch("core.auth_client.delete_student_auth_by_user_id") as mock_fn:
            process_batch()

        # auth-service receives the exact original user_id.
        mock_fn.assert_called_once_with(
            student_id="STU001",
            user_id=original_uid,
        )


# ── Management commands ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestProcessOutboxCommand:

    def test_command_processes_pending_event(self, db):
        from users.models import OutboxEvent

        _make_outbox_event()
        with patch("core.auth_client.delete_student_auth_by_user_id"):
            call_command("process_outbox")

        assert OutboxEvent.objects.filter(status=OutboxEvent.Status.DONE).count() == 1

    def test_command_output_when_no_events(self, db):
        out = StringIO()
        call_command("process_outbox", stdout=out)
        assert "No pending events" in out.getvalue()


@pytest.mark.django_db
class TestCleanupOutboxCommand:

    def test_deletes_old_done_events(self, db):
        from users.models import OutboxEvent

        old_time = timezone.now() - timedelta(days=31)
        event = _make_outbox_event(status="done", processed_at=old_time)
        # Backdate processed_at directly in the DB.
        OutboxEvent.objects.filter(pk=event.pk).update(processed_at=old_time)

        out = StringIO()
        call_command("cleanup_outbox", stdout=out)

        assert not OutboxEvent.objects.filter(pk=event.pk).exists()
        assert "Deleted 1" in out.getvalue()

    def test_preserves_recent_done_events(self, db):
        from users.models import OutboxEvent

        event = _make_outbox_event(status="done",
                                   processed_at=timezone.now() - timedelta(days=1))
        OutboxEvent.objects.filter(pk=event.pk).update(
            processed_at=timezone.now() - timedelta(days=1)
        )

        out = StringIO()
        call_command("cleanup_outbox", stdout=out)

        assert OutboxEvent.objects.filter(pk=event.pk).exists()

    def test_never_deletes_pending_or_dead_letter(self, db):
        from users.models import OutboxEvent

        pending = _make_outbox_event(status="pending")
        dead = _make_outbox_event(status="dead_letter", attempts=10)
        # Backdate created_at to simulate old records.
        old_time = timezone.now() - timedelta(days=31)
        OutboxEvent.objects.filter(pk__in=[pending.pk, dead.pk]).update(
            processed_at=old_time
        )

        call_command("cleanup_outbox")

        assert OutboxEvent.objects.filter(pk=pending.pk).exists()
        assert OutboxEvent.objects.filter(pk=dead.pk).exists()

    def test_dry_run_does_not_delete(self, db):
        from users.models import OutboxEvent

        old_time = timezone.now() - timedelta(days=31)
        event = _make_outbox_event(status="done", processed_at=old_time)
        OutboxEvent.objects.filter(pk=event.pk).update(processed_at=old_time)

        out = StringIO()
        call_command("cleanup_outbox", dry_run=True, stdout=out)

        assert OutboxEvent.objects.filter(pk=event.pk).exists()
        assert "DRY RUN" in out.getvalue()

    def test_custom_retention_period(self, db):
        from users.models import OutboxEvent

        # Event is 10 days old.
        ten_days_ago = timezone.now() - timedelta(days=10)
        event = _make_outbox_event(status="done", processed_at=ten_days_ago)
        OutboxEvent.objects.filter(pk=event.pk).update(processed_at=ten_days_ago)

        # With default 30-day retention: not deleted.
        call_command("cleanup_outbox")
        assert OutboxEvent.objects.filter(pk=event.pk).exists()

        # With 7-day retention: deleted.
        call_command("cleanup_outbox", retention_days=7)
        assert not OutboxEvent.objects.filter(pk=event.pk).exists()
