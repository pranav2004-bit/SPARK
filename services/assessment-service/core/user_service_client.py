"""
user_service_client.py — internal HTTP client for assessment-service → user-service calls.

All requests go directly to user-service:8000 on the Docker internal network,
bypassing nginx entirely, mirroring user-service's own core/auth_client.py
(→ auth-service) pattern for retry/error handling.

The one deliberate difference from auth_client.py: this client authenticates
by forwarding the *calling admin's own JWT* as a Bearer token, not a
X-Service-Key shared secret. user-service's GET /api/users/batches/<id>/students/
already enforces admin-role + institution-scoped access on that exact token —
reusing it here means zero changes to user-service's auth/permission layer,
and the roster snapshot is naturally scoped to the same institution the
calling admin belongs to. Only user-service's StudentListSerializer needed one
additive field (user_id) to make the response usable — see that file's comment.

Used exactly once in V1: at BatchAssignment creation time (Task 3.1), to
snapshot a batch's roster into StudentSetAllocation rows. The exam-taking
path (Phase 5) never calls user-service live.

Configuration (via Django settings / environment variables)
------------------------------------------------------------
  USER_SERVICE_URL           — base URL of user-service        (default: http://user-service:8000)
  USER_SERVICE_TIMEOUT       — per-attempt timeout in seconds   (default: 5)
  USER_SERVICE_RETRIES       — total number of attempts (1 = no retry) (default: 3)
  USER_SERVICE_RETRY_BACKOFF — base seconds for exponential backoff (default: 0.3)
"""

import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


_STATUS_MESSAGES: dict[int, str] = {
    400: "User service rejected the request due to invalid data.",
    403: "User service refused the call — the admin's token is not authorized for this batch.",
    404: "Batch not found.",
    500: "User service encountered an internal error.",
    503: "User service is unavailable.",
}

# Exceptions where it is safe to retry because the server provably never
# received the request (connection-level failure before any data was sent).
_RETRYABLE = (
    ConnectionRefusedError,
    ConnectionResetError,
    socket.gaierror,
)

# This client only ever does GET requests (read-only roster fetch) — every
# attempt, including retries, is safe to repeat, unlike auth_client.py's
# POST/PATCH/DELETE calls which must not retry across a read-timeout.
_MAX_PAGES = 200  # 200 pages × 200 page_size = 40,000 students — far above V1 scale


def _cfg() -> dict:
    return {
        "url":     getattr(settings, "USER_SERVICE_URL", "http://user-service:8000"),
        "timeout": int(getattr(settings, "USER_SERVICE_TIMEOUT", 5)),
        "retries": int(getattr(settings, "USER_SERVICE_RETRIES", 3)),
        "backoff": float(getattr(settings, "USER_SERVICE_RETRY_BACKOFF", 0.3)),
    }


def _get(path: str, auth_header: str) -> dict:
    """GET path from user-service, forwarding auth_header verbatim as
    Authorization. Retries on connection-level failures only (read-only, so
    unlike auth_client.py a timeout retry is also safe — but kept consistent
    with the same conservative policy for simplicity and predictability).

    Raises RuntimeError on any failure — the caller (Task 3.1's assignment
    creation) treats a roster-fetch failure as a hard blocker: the whole
    admin action must fail cleanly rather than partially allocate students.
    """
    cfg = _cfg()
    url = f"{cfg['url']}{path}"
    headers = {"Authorization": auth_header}

    last_exc: Optional[Exception] = None

    for attempt in range(1, cfg["retries"] + 1):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
                return json.loads(resp.read().decode("utf-8"))

        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                server_msg = payload.get("message", "")
            except Exception:
                server_msg = ""
            friendly = _STATUS_MESSAGES.get(exc.code, f"HTTP {exc.code}")
            detail = server_msg or friendly
            logger.warning("User service HTTP %s on GET %s: %s", exc.code, path, detail)
            raise RuntimeError(detail)

        except TimeoutError:
            logger.error("User service read timeout — GET %s. Not retrying.", path)
            raise RuntimeError(
                "User service did not respond in time. Please try again — "
                "if the error persists, contact support."
            )

        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                logger.error("User service connection timeout — GET %s. Not retrying.", path)
                raise RuntimeError(
                    "User service did not respond in time. Please try again — "
                    "if the error persists, contact support."
                )
            if isinstance(reason, _RETRYABLE):
                last_exc = exc
            else:
                logger.error("User service network error — GET %s: %s", path, reason)
                raise RuntimeError(f"User service unreachable: {reason}")

        except OSError as exc:
            if isinstance(exc, _RETRYABLE):
                last_exc = exc
            else:
                logger.error("User service OS error — GET %s: %s", path, exc)
                raise RuntimeError(f"User service connection error: {exc}")

        except Exception as exc:
            logger.exception("Unexpected error calling user service — GET %s: %s", path, exc)
            raise RuntimeError(f"Unexpected user service error: {exc}")

        if attempt < cfg["retries"]:
            wait = cfg["backoff"] * attempt
            logger.warning(
                "User service unreachable (attempt %d/%d) — GET %s: %s. Retrying in %.1f s.",
                attempt, cfg["retries"], path, last_exc, wait,
            )
            time.sleep(wait)
        else:
            logger.error(
                "User service unreachable after %d attempt(s) — GET %s: %s",
                cfg["retries"], path, last_exc,
            )

    raise RuntimeError(
        f"User service unreachable after {cfg['retries']} attempt(s). Last error: {last_exc}"
    )


def fetch_batch_roster(batch_id: str, auth_header: str) -> list[dict]:
    """
    Fetch the full (all-pages) student roster for a batch from user-service,
    scoped to whatever institution the given auth_header's admin belongs to.

    Returns a list of dicts with (at least) "user_id" and "student_id" keys
    — the roster snapshot (Task 3.1) only needs user_id (matches
    request.user.id when the student later authenticates); student_id
    (human-readable roll number) is carried through for audit/debugging.

    Raises RuntimeError on any failure (network, auth, or a batch that
    doesn't exist / isn't visible to this admin) — callers must treat this
    as a hard blocker for assignment creation, never a partial result.
    """
    students: list[dict] = []
    page = 1
    for _ in range(_MAX_PAGES):
        query = urllib.parse.urlencode({"page": page, "page_size": 200})
        payload = _get(f"/api/users/batches/{batch_id}/students/?{query}", auth_header)
        data = payload.get("data", payload)
        results = data.get("results", [])
        students.extend(results)
        if not data.get("next"):
            break
        page += 1
    else:
        logger.error(
            "Batch %s roster fetch hit the %d-page safety cap — roster may be incomplete.",
            batch_id, _MAX_PAGES,
        )
        raise RuntimeError("Batch roster is too large to snapshot safely. Contact support.")

    return students
