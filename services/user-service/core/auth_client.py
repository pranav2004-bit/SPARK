"""
auth_client.py — internal HTTP client for user-service → auth-service calls.

All requests go directly to auth-service:8000 on the Docker internal network,
bypassing nginx entirely.  The X-Service-Key header authenticates the call.

Design decisions
----------------
* Settings are read on every call (not at module import time) so that
  runtime overrides — e.g. @override_settings in tests — are respected.

* Retries are only performed on connection-level failures where it is
  certain the server never received the request:
    - ConnectionRefusedError  (server not running yet / restarting)
    - ConnectionResetError    (connection dropped before request was sent)
    - socket.gaierror         (DNS resolution failed)

  Read timeouts are NOT retried.  A timeout means the TCP connection was
  established and the request was sent — the server may have processed it.
  Retrying a non-idempotent call (e.g. POST to create a student) after a
  timeout risks creating duplicate records or hitting primary-key conflicts.

* HTTP-level errors (4xx / 5xx) are never retried — a definitive response
  from auth-service means retrying will not change the outcome.

* All public helpers are non-fatal by default where the operation is
  best-effort (set_student_active, delete_student_auth).
  create_student_auth raises RuntimeError because a missing auth account
  is a hard blocker for student login.

Configuration (via Django settings / environment variables)
------------------------------------------------------------
  AUTH_SERVICE_URL        — base URL of auth-service  (default: http://auth-service:8000)
  SERVICE_KEY             — shared secret sent as X-Service-Key header
  AUTH_SERVICE_TIMEOUT    — per-attempt timeout in seconds            (default: 3)
  AUTH_SERVICE_RETRIES    — total number of attempts (1 = no retry)   (default: 2)
  AUTH_SERVICE_RETRY_BACKOFF — base seconds for exponential backoff   (default: 0.3)
                               attempt 1 waits backoff×1, attempt 2 waits backoff×2, …
"""

import json
import logging
import socket
import time
import urllib.error
import urllib.request
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


# ── Human-readable messages for known HTTP status codes ───────────────────────

_STATUS_MESSAGES: dict[int, str] = {
    400: "Auth service rejected the request due to invalid data.",
    403: "Auth service refused the call — SERVICE_KEY mismatch between services.",
    404: "Auth account not found.",
    409: "An auth account for this student already exists.",
    500: "Auth service encountered an internal error.",
    503: "Auth service is unavailable.",
}

# Exceptions where it is safe to retry because the server provably never
# received the request (connection-level failure before any data was sent).
_RETRYABLE = (
    ConnectionRefusedError,   # server not running / still starting up
    ConnectionResetError,     # connection dropped before the request was sent
    socket.gaierror,          # DNS resolution failed
)


# ── Internal config reader ────────────────────────────────────────────────────

def _cfg() -> dict:
    """
    Read auth-service configuration from Django settings on every call.

    Reading at call time (rather than at module import time) ensures that
    runtime overrides such as @override_settings in tests are always picked up.
    """
    return {
        "url":     getattr(settings, "AUTH_SERVICE_URL", "http://auth-service:8000"),
        "key":     getattr(settings, "SERVICE_KEY", ""),
        "timeout": int(getattr(settings, "AUTH_SERVICE_TIMEOUT", 3)),
        "retries": int(getattr(settings, "AUTH_SERVICE_RETRIES", 2)),
        "backoff": float(getattr(settings, "AUTH_SERVICE_RETRY_BACKOFF", 0.3)),
    }


# ── Core HTTP caller ──────────────────────────────────────────────────────────

def _call(method: str, path: str, data: Optional[dict] = None) -> dict:
    """
    Make an authenticated HTTP call to auth-service.

    Retries only on connection-level failures (server not reachable).
    Read timeouts and HTTP errors are raised immediately — retrying them
    risks duplicate operations on the server side.

    Raises
    ------
    RuntimeError
        On any failure (HTTP error, network error, or exhausted retries).
        The message is human-readable and safe to surface to callers.
    """
    cfg = _cfg()
    url = f"{cfg['url']}{path}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {
        "Content-Type": "application/json",
        "X-Service-Key": cfg["key"],
    }

    last_exc: Optional[Exception] = None

    for attempt in range(1, cfg["retries"] + 1):
        req = urllib.request.Request(
            url, data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
                return json.loads(resp.read().decode("utf-8"))

        except urllib.error.HTTPError as exc:
            # A proper HTTP response was received — do NOT retry.
            raw_body = exc.read().decode("utf-8", errors="replace")
            try:
                server_msg = json.loads(raw_body).get("message", "")
            except Exception:
                # Non-JSON body (e.g. Django's own HTML error page for a
                # DisallowedHost/500 that never reached DRF) — log the raw
                # body so the real cause is visible instead of only ever
                # surfacing the generic per-status fallback message below.
                server_msg = ""
                logger.warning(
                    "Auth service returned non-JSON body for HTTP %s on %s %s: %.500s",
                    exc.code, method, path, raw_body,
                )
            friendly = _STATUS_MESSAGES.get(exc.code, f"HTTP {exc.code}")
            detail = server_msg or friendly
            logger.warning(
                "Auth service HTTP %s on %s %s: %s",
                exc.code, method, path, detail,
            )
            raise RuntimeError(detail)

        except TimeoutError:
            # The TCP connection was open and the request was sent.
            # The server MAY have processed it — do NOT retry to avoid
            # duplicate side-effects (e.g. duplicate student creation).
            logger.error(
                "Auth service read timeout — %s %s. "
                "Request was sent; the operation may or may not have been processed. "
                "Not retrying to prevent duplicate operations.",
                method, path,
            )
            raise RuntimeError(
                "Auth service did not respond in time. "
                "Please try again — if the error persists, contact support."
            )

        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                # URLError wrapping a timeout — same policy as bare TimeoutError.
                logger.error(
                    "Auth service connection timeout — %s %s. Not retrying.",
                    method, path,
                )
                raise RuntimeError(
                    "Auth service did not respond in time. "
                    "Please try again — if the error persists, contact support."
                )
            if isinstance(reason, _RETRYABLE):
                # Server provably did not receive the request — safe to retry.
                last_exc = exc
            else:
                # Unknown network error — treat as non-retryable.
                logger.error(
                    "Auth service network error — %s %s: %s",
                    method, path, reason,
                )
                raise RuntimeError(f"Auth service unreachable: {reason}")

        except OSError as exc:
            if isinstance(exc, _RETRYABLE):
                last_exc = exc
            else:
                logger.error(
                    "Auth service OS error — %s %s: %s", method, path, exc
                )
                raise RuntimeError(f"Auth service connection error: {exc}")

        except Exception as exc:
            logger.exception(
                "Unexpected error calling auth service — %s %s: %s",
                method, path, exc,
            )
            raise RuntimeError(f"Unexpected auth service error: {exc}")

        # If we reach here, last_exc was set and we should retry.
        if attempt < cfg["retries"]:
            wait = cfg["backoff"] * attempt   # 0.3 s → 0.6 s → 0.9 s …
            logger.warning(
                "Auth service unreachable (attempt %d/%d) — %s %s: %s. "
                "Retrying in %.1f s.",
                attempt, cfg["retries"], method, path, last_exc, wait,
            )
            time.sleep(wait)
        else:
            logger.error(
                "Auth service unreachable after %d attempt(s) — %s %s: %s",
                cfg["retries"], method, path, last_exc,
            )

    raise RuntimeError(
        f"Auth service unreachable after {cfg['retries']} attempt(s). "
        f"Last error: {last_exc}"
    )


# ── Public helpers ─────────────────────────────────────────────────────────────

def create_student_auth(
    user_id: str,
    student_id: str,
    institution_id: Optional[str],
) -> None:
    """
    Create an auth User for a newly created student.

    Raises RuntimeError on failure — the caller must treat this as a hard
    error because the student cannot log in without an auth account.
    """
    _call("POST", "/api/auth/internal/students/", {
        "user_id": user_id,
        "student_id": student_id,
        "institution_id": institution_id,
    })
    logger.info("Auth account created for student_id=%s", student_id)


def set_student_active(student_id: str, is_active: bool) -> None:
    """
    Sync is_active status to the student's auth User.

    Non-fatal: logs a warning on failure and continues.  The profile record
    in user-service is already updated; the auth sync is best-effort.
    """
    try:
        _call(
            "PATCH",
            f"/api/auth/internal/students/{student_id}/",
            {"is_active": is_active},
        )
        logger.info(
            "Auth account is_active=%s for student_id=%s", is_active, student_id
        )
    except RuntimeError as exc:
        logger.warning(
            "Could not sync is_active for student_id=%s: %s", student_id, exc
        )


def delete_student_auth(student_id: str) -> None:
    """
    Delete the auth User for a student (best-effort, no expected_user_id check).

    Non-fatal: logs a warning on failure and continues.  Used by maintenance
    commands (cleanup_ghost_students) where the exact user_id is not known.
    For normal student deletion use the outbox pattern which calls
    delete_student_auth_by_user_id instead.
    """
    try:
        _call("DELETE", f"/api/auth/internal/students/{student_id}/delete/")
        logger.info("Auth account deleted for student_id=%s", student_id)
    except RuntimeError as exc:
        logger.warning(
            "Could not delete auth account for student_id=%s: %s", student_id, exc
        )


def delete_student_auth_by_user_id(student_id: str, user_id: str) -> None:
    """
    Delete the auth User for a student, only if its primary key matches user_id.

    Passing expected_user_id prevents a race condition where the student is
    deleted and immediately re-added (acquiring a new user_id).  Without this
    guard the outbox worker would delete the newly created auth account instead
    of the old stale one.

    Auth-service returns 200 in all terminal cases:
      - Account found and user_id matches      → deleted, 200
      - Account found but user_id differs      → skipped, 200 (re-added student)
      - Account not found                      → already gone, 200 (idempotent)

    Raises RuntimeError on network or server-side failures so the outbox worker
    can retry the event.
    """
    _call(
        "DELETE",
        f"/api/auth/internal/students/{student_id}/delete/",
        {"expected_user_id": user_id},
    )
    logger.info(
        "Auth account delete dispatched for student_id=%s (expected_user_id=%s).",
        student_id, user_id,
    )
