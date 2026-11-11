"""
enforcement.py — server-authoritative attempt-write guard (Task 4.1).

Mirrors assessment-service's own enforcement.py (session_is_writable /
strip_client_timestamps) exactly, adapted for EssayAttempt. This is the
single reusable check every mutating student endpoint (autosave, submit)
must call before accepting a write.
"""

from django.utils import timezone

from .models import ASSIGNMENT_STATUS_CLOSED, ATTEMPT_STATUS_IN_PROGRESS


def attempt_is_writable(attempt, assignment=None):
    """
    Returns (True, None) if this attempt may still accept a write (an
    autosave or a submit), or (False, <human-readable reason>) otherwise.

    Takes the already-loaded attempt/assignment objects rather than IDs —
    callers already fetched them for their own IDOR-safe lookup (filtered by
    the requesting student's own JWT identity), so this function does no DB
    queries itself; it's a pure timing/status check.

    Checks, in order (matches ADR 001's pattern, adapted):
      1. assignment.status != 'CLOSED' — an admin emergency-closed the exam.
      2. attempt.status == 'IN_PROGRESS' — already finalized by a prior
         submit or the sweep.
      3. now() < attempt.ends_at — the deadline itself.
    """
    if assignment is None:
        assignment = attempt.assignment

    if assignment is not None and assignment.status == ASSIGNMENT_STATUS_CLOSED:
        return False, "This assessment has been closed by the administrator."

    if attempt.status != ATTEMPT_STATUS_IN_PROGRESS:
        return False, f"This attempt is no longer in progress (status: {attempt.status})."

    if timezone.now() >= attempt.ends_at:
        return False, "Time has expired for this attempt."

    return True, None


# Any client payload key shaped like a timestamp the client might try to
# control — matches assessment-service's CLIENT_TIMESTAMP_FIELDS_TO_IGNORE
# exactly (AT1 defense in depth).
CLIENT_TIMESTAMP_FIELDS_TO_IGNORE = frozenset({
    "submitted_at", "answered_at", "started_at", "ends_at", "timestamp",
})


def strip_client_timestamps(data: dict) -> dict:
    """Returns a copy of `data` with every known timestamp-shaped key
    removed — defense in depth against a forged timestamp, independent of
    whether a given serializer even declares those fields."""
    return {k: v for k, v in data.items() if k not in CLIENT_TIMESTAMP_FIELDS_TO_IGNORE}
