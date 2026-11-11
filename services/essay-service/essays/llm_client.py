"""
llm_client.py — Task 5.2 / ADR 003 Decisions 1, 6, 8.

Wraps the OpenAI SDK call itself: JSON mode, per-key quota reservation
with rotation across `settings.OPENAI_API_KEYS`, and the transient-vs-
permanent error classification ported from CLAP's own
`openai_client.py` (verified by direct code reading) — RateLimitError is
handled via key rotation (not a plain retry), APIConnectionError/
APITimeoutError are transient (the caller retries), OpenAIError (content-
policy/auth/invalid-request) is permanent (the caller must not retry),
and a non-JSON response is its own third bucket, LLMMalformedResponseError
— retryable per ADR 003 Decision 6 ("retries once more before going to
DLQ"), not permanent like a definitive provider rejection.
"""
import json
import logging
from typing import NamedTuple

from django.conf import settings

from .quota_tracker import QuotaTracker, QuotaDailyExhaustedException, QuotaTemporarilyUnavailableException

logger = logging.getLogger("essays.llm")


class LLMEvaluationResult(NamedTuple):
    """Phase 7, Task 7.1's own "LLM trace/debug view" requirement needs
    the raw exchange (the exact prompt, the raw response text, OpenAI's
    own request id, the model used), not just the parsed score/feedback
    Phase 5's own scoring logic needs — so this wraps both rather than
    changing call_openai_evaluate to return a bare dict of one shape or
    the other. `parsed` is exactly what the function returned before this
    phase (every existing caller keeps working by reading `.parsed`
    instead of the old bare return value); the rest is new."""
    parsed: dict
    raw_response: str
    request_id: str
    model: str


class LLMTransientError(Exception):
    """Network/timeout-shaped failure — safe to retry."""


class LLMMalformedResponseError(Exception):
    """Non-JSON or otherwise unparsable model output. ADR 003 Decision 6:
    "retries once more before going to DLQ" — shares evaluate_essay's
    ordinary retry budget, unlike LLMPermanentError below, which skips
    retry entirely. May simply be model noise on that one call, not a
    systemic problem."""


class LLMPermanentError(Exception):
    """A definitive provider-side rejection (content-policy refusal,
    invalid request, auth failure) — goes to DLQ immediately, no retry."""


def _redis_client():
    import redis
    return redis.from_url(settings.REDIS_URL)


def call_openai_evaluate(messages: list[dict]) -> LLMEvaluationResult:
    """Calls OpenAI chat completions in JSON mode, rotating across
    `settings.OPENAI_API_KEYS` for quota headroom, and returns an
    LLMEvaluationResult (the parsed JSON dict plus the raw response/
    request id/model, for Task 7.1's own trace view — see that class's
    own docstring). Never lets a raw OpenAI SDK exception or a bare
    json.JSONDecodeError escape this function — every caller only ever
    needs to handle this module's own five exception types: LLMTransientError
    (retry), LLMMalformedResponseError (retry, per ADR 003 Decision 6),
    LLMPermanentError (do not retry, DLQ immediately), and
    QuotaDailyExhaustedException / QuotaTemporarilyUnavailableException
    (not failures at all — retry on the given countdown, never DLQ'd,
    never counted against any retry ceiling)."""
    from openai import APIConnectionError, APITimeoutError, OpenAIError, RateLimitError

    api_keys = list(getattr(settings, "OPENAI_API_KEYS", []) or [])
    if not api_keys:
        raise LLMPermanentError("No OPENAI_API_KEYS configured — cannot evaluate.")

    tracker = QuotaTracker.from_settings(_redis_client())
    # Rough pre-call estimate — the exact usage is only known after the
    # call returns; this is only used for the quota check's own TPM/TPD
    # reservation, not billed anywhere.
    estimated_tokens = sum(len(m["content"]) for m in messages) // 4 + 512

    # Tracked across the WHOLE loop, not just the last key checked: if even
    # one key's denial was a short per-minute cooldown (rpm/tpm), the
    # overall situation is "temporarily unavailable", not "daily
    # exhausted" — even if a later key in rotation happens to be RPD/TPD-
    # denied. Only treat this as genuine daily exhaustion if EVERY
    # checked key was denied for a daily reason. Retry as soon as the
    # EARLIEST temporary denial might clear, not an arbitrary fixed 65s.
    temporary_wait = None
    daily_wait = None
    for api_key in api_keys:
        granted, reason, wait_seconds = tracker.check_and_reserve(api_key, estimated_tokens)
        if not granted:
            # rpm/tpm are per-minute windows (a short cooldown); rpd/tpd
            # are per-day (a real exhaustion) — see QuotaTracker.check_and_
            # reserve's own docstring for the bug this distinction fixes.
            if reason in ("rpd", "tpd"):
                daily_wait = wait_seconds if daily_wait is None else min(daily_wait, wait_seconds)
            else:
                temporary_wait = wait_seconds if temporary_wait is None else min(temporary_wait, wait_seconds)
            continue

        client_kwargs = {"api_key": api_key}
        base_url = getattr(settings, "OPENAI_BASE_URL", None)
        if base_url:
            client_kwargs["base_url"] = base_url

        try:
            from openai import OpenAI
            client = OpenAI(**client_kwargs)
            response = client.chat.completions.create(
                model=getattr(settings, "OPENAI_MODEL", "gpt-4o"),
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"},
                timeout=45.0,
            )
        except RateLimitError as exc:
            logger.warning("llm_client: key rate-limited, rotating to next key: %s", exc)
            # A live 429 from the provider itself — treated the same as an
            # internal rpm/tpm denial (a short cooldown, not a daily one).
            temporary_wait = 65 if temporary_wait is None else min(temporary_wait, 65)
            continue
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMTransientError(str(exc)) from exc
        except OpenAIError as exc:
            raise LLMPermanentError(str(exc)) from exc

        content = response.choices[0].message.content
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise LLMMalformedResponseError(f"Non-JSON LLM response: {exc}") from exc

        return LLMEvaluationResult(
            parsed=parsed,
            raw_response=content,
            request_id=getattr(response, "id", "") or "",
            model=getattr(response, "model", None) or getattr(settings, "OPENAI_MODEL", "gpt-4o"),
        )

    # Every configured key was either quota-exhausted or rate-limited this
    # pass. Prefer the temporary (short-cooldown) classification whenever
    # ANY key qualifies for it — only every single key being genuinely
    # daily-exhausted falls through to the daily branch.
    if temporary_wait is not None:
        raise QuotaTemporarilyUnavailableException(temporary_wait)
    raise QuotaDailyExhaustedException(wait_seconds=daily_wait or 3600)
