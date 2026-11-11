"""
quota_tracker.py — Task 5.2 / ADR 003 Decision 8.

Ported from CLAP's `django-backend/api/utils/quota_tracker.py`, verified
by direct code reading (re-confirmed during Phase 5's own pre-
implementation audit, 2026-09-20) — this one genuinely is a faithful
reuse, unlike Decisions 3-5's prompt/redaction/guard machinery. One
atomic Redis Lua script checks and increments all four OpenAI quota
dimensions (RPM/RPD/TPM/TPD) per key in a single round-trip (zero
check-then-act race window), applies a safety margin under the provider's
real limit via `math.floor`, hashes each key (SHA-256, never stores the
raw key in Redis), and fails OPEN — if Redis is down, a quota check
passes through rather than blocking a real evaluation (ADR 003 Decision 8
point 1; this is the deliberate opposite of Task 5.1's submission-rate
throttle, which fails closed — see core/throttling_resilience.py's
FailClosedThrottleMixin for that one).

Default limits below (rpm=3, rpd=200, tpm=60_000, tpd=200_000) are CLAP's
own verified real numbers — ADR 004 Section 3's own capacity table is
built against exactly these. They are NOT this platform's real numbers:
ADR 004 Section 3 names substituting the actual provisioned tier's real
limits as a blocking prerequisite for Phase 5 going to production, still
open as of this phase's implementation (no OpenAI account tier exists on
this platform yet). Configurable via Django settings (OPENAI_QUOTA_*) so
that substitution is a config change, not a code change, once the real
tier is confirmed.
"""
import hashlib
import math
import time

import redis.exceptions
from django.conf import settings

_CHECK_AND_RESERVE_LUA = """
local rpm_key = KEYS[1]; local rpd_key = KEYS[2]
local tpm_key = KEYS[3]; local tpd_key = KEYS[4]
local rpm_lim = tonumber(ARGV[1]); local rpd_lim = tonumber(ARGV[2])
local tpm_lim = tonumber(ARGV[3]); local tpd_lim = tonumber(ARGV[4])
local tokens  = tonumber(ARGV[5])

local rpm = tonumber(redis.call('GET', rpm_key) or 0)
local rpd = tonumber(redis.call('GET', rpd_key) or 0)
local tpm = tonumber(redis.call('GET', tpm_key) or 0)
local tpd = tonumber(redis.call('GET', tpd_key) or 0)

if rpm + 1 > rpm_lim then
    return {0, 'rpm', rpm, redis.call('TTL', rpm_key)}
end
if rpd + 1 > rpd_lim then
    return {0, 'rpd', rpd, redis.call('TTL', rpd_key)}
end
if tpm + tokens > tpm_lim then
    return {0, 'tpm', tpm, redis.call('TTL', tpm_key)}
end
if tpd + tokens > tpd_lim then
    return {0, 'tpd', tpd, redis.call('TTL', tpd_key)}
end

redis.call('INCRBY', rpm_key, 1)
redis.call('INCRBY', rpd_key, 1)
redis.call('INCRBY', tpm_key, tokens)
redis.call('INCRBY', tpd_key, tokens)

redis.call('EXPIRE', rpm_key, 65)
redis.call('EXPIRE', rpd_key, 86410)
redis.call('EXPIRE', tpm_key, 65)
redis.call('EXPIRE', tpd_key, 86410)

return {1, 'ok', 0, 0}
"""


def _key_hash(api_key: str) -> str:
    """A safe 12-char identifier for an API key — never the key itself."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:12]


def _minute_epoch() -> int:
    return int(time.time() // 60)


def _day_epoch() -> int:
    return int(time.time() // 86400)


class QuotaDailyExhaustedException(Exception):
    """All available keys have exhausted their daily (RPD/TPD) quota."""
    def __init__(self, wait_seconds: int):
        self.wait_seconds = wait_seconds
        super().__init__(f"All OpenAI API keys have exhausted daily quota. Retry after {wait_seconds}s.")


class QuotaTemporarilyUnavailableException(Exception):
    """All available keys are RPM/TPM-limited for the current minute window."""
    def __init__(self, wait_seconds: int):
        self.wait_seconds = wait_seconds
        super().__init__(f"All OpenAI API keys are rate-limited this minute. Retry after {wait_seconds}s.")


class QuotaTracker:
    def __init__(
        self,
        redis_client,
        rpm_limit: int = 3,
        rpd_limit: int = 200,
        tpm_limit: int = 60_000,
        tpd_limit: int = 200_000,
        safety_margin: float = 0.90,
    ):
        self._r = redis_client
        self.rpm_limit = max(1, math.floor(rpm_limit * safety_margin))
        self.rpd_limit = max(1, math.floor(rpd_limit * safety_margin))
        self.tpm_limit = max(100, math.floor(tpm_limit * safety_margin))
        self.tpd_limit = max(1000, math.floor(tpd_limit * safety_margin))
        self._check_and_reserve = self._r.register_script(_CHECK_AND_RESERVE_LUA)

    def _rpm_key(self, api_key: str) -> str:
        return f"openai:rl:{_key_hash(api_key)}:rpm:{_minute_epoch()}"

    def _rpd_key(self, api_key: str) -> str:
        return f"openai:rl:{_key_hash(api_key)}:rpd:{_day_epoch()}"

    def _tpm_key(self, api_key: str) -> str:
        return f"openai:rl:{_key_hash(api_key)}:tpm:{_minute_epoch()}"

    def _tpd_key(self, api_key: str) -> str:
        return f"openai:rl:{_key_hash(api_key)}:tpd:{_day_epoch()}"

    def check_and_reserve(self, api_key: str, estimated_tokens: int):
        """Atomically checks all four dimensions for this one key and
        reserves `estimated_tokens` worth of TPM/TPD if every dimension
        has room. Returns (granted: bool, reason: str | None, wait_seconds: int)
        — the caller (llm_client) uses `reason`/`wait_seconds` to decide
        between QuotaTemporarilyUnavailableException (a short, per-minute
        RPM/TPM cooldown) and QuotaDailyExhaustedException (a real RPD/TPD
        exhaustion, wait until tomorrow) rather than conflating the two.

        Real bug found and fixed during this phase's own audit: this used
        to return a bare bool, so llm_client could not tell an RPM/TPM
        denial (the common case — a per-minute cooldown, ADR 004 Section
        3's whole capacity table assumes ~65s waits like this) apart from
        a genuine RPD/TPD denial (rare, should wait until tomorrow) once
        every configured key was denied. Every all-keys-denied case fell
        through to the daily-exhaustion branch, so a busy but otherwise
        healthy deployment would incorrectly wait a full hour on what was
        actually a one-minute RPM blip — directly contradicting ADR 004's
        own math, not just a cosmetic inaccuracy.

        Fails OPEN (ADR 003 Decision 8): a Redis outage here returns
        granted=True (reservation "succeeds") rather than blocking a real
        evaluation — the harm of briefly not rate-limiting against the
        provider during a Redis blip is smaller than stalling evaluations
        over infrastructure the evaluation itself doesn't strictly need.
        """
        try:
            result = self._check_and_reserve(
                keys=[self._rpm_key(api_key), self._rpd_key(api_key), self._tpm_key(api_key), self._tpd_key(api_key)],
                args=[self.rpm_limit, self.rpd_limit, self.tpm_limit, self.tpd_limit, estimated_tokens],
            )
            granted = bool(result[0])
            if granted:
                return True, None, 0
            reason = result[1]
            wait_seconds = max(int(result[3] or 0), 1)
            return False, reason, wait_seconds
        except redis.exceptions.RedisError:
            return True, None, 0

    @classmethod
    def from_settings(cls, redis_client):
        """Reads OPENAI_QUOTA_* from Django settings, defaulting to
        CLAP's own verified numbers — see this module's own docstring for
        why those are a placeholder, not this platform's real tier."""
        return cls(
            redis_client,
            rpm_limit=getattr(settings, "OPENAI_QUOTA_RPM_LIMIT", 500),
            rpd_limit=getattr(settings, "OPENAI_QUOTA_RPD_LIMIT", 10_000),
            tpm_limit=getattr(settings, "OPENAI_QUOTA_TPM_LIMIT", 800_000),
            tpd_limit=getattr(settings, "OPENAI_QUOTA_TPD_LIMIT", 10_000_000),
            safety_margin=getattr(settings, "OPENAI_QUOTA_SAFETY_MARGIN", 0.90),
        )
