"""
users/outbox.py — Outbox pattern processor for cross-service operations.

Guarantees
----------
* At-least-once delivery: each event is retried up to MAX_ATTEMPTS times with
  exponential backoff (30s → 60s → 120s → … → 30 min).
* SELECT FOR UPDATE SKIP LOCKED (PostgreSQL only) prevents two worker instances
  from processing the same event simultaneously.
* Stuck events — those left in PROCESSING longer than STUCK_THRESHOLD_MINUTES
  because a worker process crashed — are automatically re-queued.
* Dead-letter events (exhausted retries) are logged at CRITICAL level and
  require manual intervention.
* payload['user_id'] is forwarded to auth-service so it can skip deletes that
  would remove a newly re-created auth account rather than the old one.
"""

import logging
from datetime import timedelta

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_ATTEMPTS          = 10
BATCH_SIZE            = 50
STUCK_THRESHOLD_MINUTES = 10
BACKOFF_BASE_SECONDS  = 30
BACKOFF_MAX_SECONDS   = 1800  # 30 minutes cap


# ── Helpers ────────────────────────────────────────────────────────────────────

def _compute_retry_after(attempts: int):
    """Exponential backoff capped at BACKOFF_MAX_SECONDS."""
    delay = min(BACKOFF_BASE_SECONDS * (2 ** (attempts - 1)), BACKOFF_MAX_SECONDS)
    return timezone.now() + timedelta(seconds=delay)


# ── Public API ─────────────────────────────────────────────────────────────────

def recover_stuck_events() -> int:
    """
    Re-queue events that have been stuck in PROCESSING longer than
    STUCK_THRESHOLD_MINUTES.  This happens when a worker process crashes
    mid-flight before it can mark the event as DONE or back to PENDING.

    Returns the number of events recovered.
    """
    from users.models import OutboxEvent

    cutoff = timezone.now() - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
    count = OutboxEvent.objects.filter(
        status=OutboxEvent.Status.PROCESSING,
        last_attempted_at__lt=cutoff,
    ).update(
        status=OutboxEvent.Status.PENDING,
        retry_after=None,
    )
    if count:
        logger.warning(
            "Recovered %d stuck outbox event(s) (PROCESSING > %d min).",
            count, STUCK_THRESHOLD_MINUTES,
        )
    return count


def process_batch() -> int:
    """
    Pick the next batch of due PENDING events, mark them PROCESSING, then
    process each one.  Returns the number of events attempted this call.

    Lock strategy
    -------------
    On PostgreSQL: SELECT FOR UPDATE SKIP LOCKED ensures that when multiple
    worker instances run (e.g. after a rolling restart), they each claim
    different rows and never process the same event twice.

    On SQLite (test environment): locking is omitted — SQLite does not support
    SKIP LOCKED.  Single-worker behaviour in tests is sufficient.
    """
    from users.models import OutboxEvent

    now = timezone.now()

    # ── Claim a batch atomically ───────────────────────────────────────────────
    with transaction.atomic():
        qs = (
            OutboxEvent.objects
            .filter(status=OutboxEvent.Status.PENDING)
            .filter(Q(retry_after__isnull=True) | Q(retry_after__lte=now))
            .order_by('created_at')
        )
        if connection.vendor == 'postgresql':
            qs = qs.select_for_update(skip_locked=True)

        events = list(qs[:BATCH_SIZE])

        for event in events:
            event.status = OutboxEvent.Status.PROCESSING
            event.attempts += 1
            event.last_attempted_at = now
            event.save(update_fields=['status', 'attempts', 'last_attempted_at'])
    # Transaction committed — events are now PROCESSING; other workers skip them.

    # ── Process each event outside the lock ───────────────────────────────────
    for event in events:
        _process_event(event)

    return len(events)


# ── Internal ───────────────────────────────────────────────────────────────────

def _process_event(event) -> None:
    from users.models import OutboxEvent

    try:
        if event.event_type == OutboxEvent.EventType.DELETE_STUDENT_AUTH:
            _handle_delete_student_auth(event)
        else:
            raise ValueError(f"Unknown event type: {event.event_type!r}")

        # ── Success ────────────────────────────────────────────────────────────
        event.status = OutboxEvent.Status.DONE
        event.processed_at = timezone.now()
        event.last_error = ''
        event.save(update_fields=['status', 'processed_at', 'last_error'])
        logger.info(
            "Outbox event %s (%s) done — student_id=%s.",
            event.id, event.event_type, event.payload.get('student_id', '?'),
        )

    except Exception as exc:
        event.last_error = str(exc)

        if event.attempts >= MAX_ATTEMPTS:
            # ── Dead letter ────────────────────────────────────────────────────
            event.status = OutboxEvent.Status.DEAD_LETTER
            event.save(update_fields=['status', 'last_error'])
            student_id = event.payload.get('student_id', '?')
            logger.critical(
                "DEAD LETTER: outbox event %s (%s, student_id=%s) failed after "
                "%d attempt(s) — manual intervention required. Error: %s",
                event.id, event.event_type, student_id, event.attempts, exc,
            )
            # Alert admins by email.  Failure here must NOT prevent the
            # dead-letter record from being committed, so all exceptions
            # are caught and logged separately.
            try:
                from django.core.mail import mail_admins
                mail_admins(
                    subject=f"Dead-letter outbox event — student {student_id}",
                    message=(
                        f"Outbox event {event.id} has exhausted all retry "
                        f"attempts and is now in DEAD_LETTER status.\n\n"
                        f"Event ID:   {event.id}\n"
                        f"Event type: {event.event_type}\n"
                        f"Student ID: {student_id}\n"
                        f"Attempts:   {event.attempts}\n"
                        f"Last error: {event.last_error}\n\n"
                        f"Visit the Super Admin portal Dead Letter Queue tab "
                        f"to retry or investigate."
                    ),
                    fail_silently=False,
                )
            except Exception as mail_exc:
                logger.error(
                    "Failed to send dead-letter alert email for event %s: %s",
                    event.id, mail_exc,
                )
        else:
            # ── Schedule retry with exponential backoff ────────────────────────
            event.status = OutboxEvent.Status.PENDING
            event.retry_after = _compute_retry_after(event.attempts)
            event.save(update_fields=['status', 'last_error', 'retry_after'])
            logger.warning(
                "Outbox event %s (%s, student_id=%s) failed (attempt %d/%d). "
                "Retry after %s. Error: %s",
                event.id, event.event_type,
                event.payload.get('student_id', '?'),
                event.attempts, MAX_ATTEMPTS,
                event.retry_after.isoformat(), exc,
            )


def _handle_delete_student_auth(event) -> None:
    payload = event.payload
    version = payload.get('version', 1)
    if version != 1:
        raise ValueError(f"Unsupported payload version: {version!r}")

    from core.auth_client import delete_student_auth_by_user_id
    delete_student_auth_by_user_id(
        student_id=payload['student_id'],
        user_id=payload['user_id'],
    )
