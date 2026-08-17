"""
auth_service_client.py — internal HTTP client for assessment-service → auth-service calls.

All requests go directly to auth-service:8000 on the Docker internal network,
bypassing nginx entirely. Same JWT-forwarding pattern as core/user_service_client.py
(not a X-Service-Key shared secret): this is a live per-request lookup made on
behalf of a specific admin's own view (e.g. "who created this paper?"), not a
background service-to-service event — forwarding the calling admin's own JWT
means auth-service's existing admin-role + institution-scoped permission check
on that token does the access-control work for free, with zero changes needed
on auth-service's auth/permission layer.

Used to resolve QuestionPaper.created_by (a bare user_id, no FK — assessment-
service deliberately doesn't know or care which service owns the User model)
into a display name/email for "Created by <name>" labels. Best-effort by
design: see resolve_user_names' docstring for why a lookup failure here must
never fail the caller's own request.

Configuration (via Django settings / environment variables)
------------------------------------------------------------
  AUTH_SERVICE_URL           — base URL of auth-service        (default: http://auth-service:8000)
  AUTH_SERVICE_TIMEOUT       — per-attempt timeout in seconds   (default: 2)
  AUTH_SERVICE_RETRIES       — total number of attempts (1 = no retry) (default: 2)
  AUTH_SERVICE_RETRY_BACKOFF — base seconds for exponential backoff (default: 0.3)
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
    400: "Auth service rejected the request due to invalid data.",
    403: "Auth service refused the call — the admin's token is not authorized for this lookup.",
    500: "Auth service encountered an internal error.",
    503: "Auth service is unavailable.",
}

# Exceptions where it is safe to retry because the server provably never
# received the request (connection-level failure before any data was sent).
_RETRYABLE = (
    ConnectionRefusedError,
    ConnectionResetError,
    socket.gaierror,
)


def _cfg() -> dict:
    return {
        "url":     getattr(settings, "AUTH_SERVICE_URL", "http://auth-service:8000"),
        "timeout": int(getattr(settings, "AUTH_SERVICE_TIMEOUT", 2)),
        "retries": int(getattr(settings, "AUTH_SERVICE_RETRIES", 2)),
        "backoff": float(getattr(settings, "AUTH_SERVICE_RETRY_BACKOFF", 0.3)),
    }


def _get(path: str, auth_header: str) -> dict:
    """GET path from auth-service, forwarding auth_header verbatim as
    Authorization. Retries on connection-level failures only.

    Raises RuntimeError on any failure — resolve_user_names (the only
    caller) catches this and degrades gracefully; this low-level helper
    itself always either returns parsed JSON or raises, same contract as
    user_service_client.py's _get for predictability.
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
            logger.warning("Auth service HTTP %s on GET %s: %s", exc.code, path, detail)
            raise RuntimeError(detail)

        except TimeoutError:
            logger.error("Auth service read timeout — GET %s. Not retrying.", path)
            raise RuntimeError("Auth service did not respond in time.")

        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                logger.error("Auth service connection timeout — GET %s. Not retrying.", path)
                raise RuntimeError("Auth service did not respond in time.")
            if isinstance(reason, _RETRYABLE):
                last_exc = exc
            else:
                logger.error("Auth service network error — GET %s: %s", path, reason)
                raise RuntimeError(f"Auth service unreachable: {reason}")

        except OSError as exc:
            if isinstance(exc, _RETRYABLE):
                last_exc = exc
            else:
                logger.error("Auth service OS error — GET %s: %s", path, exc)
                raise RuntimeError(f"Auth service connection error: {exc}")

        except Exception as exc:
            logger.exception("Unexpected error calling auth service — GET %s: %s", path, exc)
            raise RuntimeError(f"Unexpected auth service error: {exc}")

        if attempt < cfg["retries"]:
            wait = cfg["backoff"] * attempt
            logger.warning(
                "Auth service unreachable (attempt %d/%d) — GET %s: %s. Retrying in %.1f s.",
                attempt, cfg["retries"], path, last_exc, wait,
            )
            time.sleep(wait)
        else:
            logger.error(
                "Auth service unreachable after %d attempt(s) — GET %s: %s",
                cfg["retries"], path, last_exc,
            )

    raise RuntimeError(
        f"Auth service unreachable after {cfg['retries']} attempt(s). Last error: {last_exc}"
    )


def resolve_user_names(user_ids: list[str], auth_header: str) -> dict[str, dict]:
    """
    Resolves a batch of user_ids (e.g. every distinct QuestionPaper.created_by
    on one page of results) to {"name": ..., "email": ...}, scoped to
    whatever institution the given auth_header's admin belongs to — one
    call for the whole batch, not one per row.

    Returns {user_id_str: {"name": ..., "email": ...}}. A requested id that
    doesn't resolve (wrong institution, deleted account) is simply absent
    from the result — callers must .get() with a fallback, never index
    directly.

    Best-effort: swallows any failure and returns {} rather than raising.
    "Created by <name>" is a display nicety, never worth failing an entire
    papers list over a transient auth-service hiccup — the caller falls
    back to showing nothing/an id rather than erroring the whole page.
    """
    if not user_ids:
        return {}
    ids_param = urllib.parse.quote(",".join(user_ids))
    try:
        payload = _get(f"/api/auth/admin/users/lookup/?ids={ids_param}", auth_header)
    except RuntimeError as exc:
        logger.warning("Could not resolve user names from auth-service: %s", exc)
        return {}
    data = payload.get("data", payload)
    if not isinstance(data, list):
        return {}
    return {
        u["id"]: {"name": u.get("name", ""), "email": u.get("email", "")}
        for u in data if "id" in u
    }
