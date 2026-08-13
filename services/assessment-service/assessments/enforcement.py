"""
enforcement.py — server-authoritative session-write guard (Task 4.2, ADR 001
decision point 2).

session_is_writable() is the single reusable check every mutating student
endpoint must call before accepting a write. It doesn't exist yet in V1 —
the answer-autosave and submit endpoints are Task 5.2, a later phase — but
the check itself has no dependency on those endpoints, so it's built here as
a pure, already-unit-testable primitive, the same "build the reusable piece
now, wire it into an endpoint later" pattern Task 4.1 used for
finalize_sessions() (which Task 3.2's close/ cascade and this task's future
submit endpoint both call).

strip_client_timestamps() is the other half of AT1 defense in depth: any
client-supplied timestamp-shaped field is silently dropped before it ever
reaches a serializer, never trusted. The server's own clock is the only
timestamp ever written.
"""

from django.utils import timezone

from .models import ASSIGNMENT_STATUS_CLOSED, SESSION_STATUS_IN_PROGRESS


def session_is_writable(session, assignment=None):
    """
    Returns (True, None) if this session may still accept a write (an
    answer autosave or a submit), or (False, <human-readable reason>)
    otherwise.

    Deliberately takes the already-loaded session/assignment objects rather
    than IDs — callers already fetched them for their own IDOR-safe lookup
    (AT3, filtering by the requesting student's own JWT identity), so this
    function does no DB queries itself; it's a pure timing/status check.

    Checks, in order (matches ADR 001 decision point 2 exactly):
      1. assignment.status != 'CLOSED' — an admin emergency-closed the
         exam; independent of whether the sweep's cascade has caught this
         specific session yet (defense in depth against a cascade bug/lag).
      2. session.status == 'IN_PROGRESS' — already finalized by a prior
         submit, the sweep, or a close/ cascade.
      3. now() < session.ends_at — the deadline itself.
    """
    if assignment is None:
        assignment = session.assignment

    if assignment.status == ASSIGNMENT_STATUS_CLOSED:
        return False, "This assessment has been closed by the administrator."

    if session.status != SESSION_STATUS_IN_PROGRESS:
        return False, f"This session is no longer in progress (status: {session.status})."

    if timezone.now() >= session.ends_at:
        return False, "Time has expired for this session."

    return True, None


# Any client payload key shaped like a timestamp the client might try to
# control — a forged submitted_at/answered_at is the textbook AT1 attempt
# (claim an earlier time than the request actually arrived). None of these
# are ever read from client input; every one is server-computed.
CLIENT_TIMESTAMP_FIELDS_TO_IGNORE = frozenset({
    "submitted_at", "answered_at", "started_at", "ends_at", "timestamp",
})


def strip_client_timestamps(data: dict) -> dict:
    """
    Returns a copy of `data` with every known timestamp-shaped key removed.
    Task 5.2's submit/autosave serializers call this on incoming request
    data before validation — defense in depth against AT1, independent of
    whether a given serializer even declares those fields (a field a
    serializer doesn't declare is already ignored by DRF, but an explicit
    strip here means that safety doesn't silently depend on someone
    remembering not to add the field later).
    """
    return {k: v for k, v in data.items() if k not in CLIENT_TIMESTAMP_FIELDS_TO_IGNORE}
