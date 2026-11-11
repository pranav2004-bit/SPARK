"""
Redis graceful degradation for DRF's throttle classes.

DRF's SimpleRateThrottle.allow_request() calls `self.cache.get(self.key, [])`
with no exception handling of its own. Left as-is, a Redis outage would
make almost every request in the service raise instead of just serving
slower or unthrottled — a single dependency failure cascading into a
near-total outage. Mirrors the pattern already proven on assessment-service
(Task 13.1).

The correct failure mode for a rate limiter specifically (unlike a cache
whose job is correctness-neutral speedup) is to *fail open*: if Redis is
down, the safe choice is to stop throttling temporarily, not to reject
every request. nginx remains the primary rate limiter throughout this
outage — losing this defense-in-depth layer for the outage's duration is
an acceptable, self-healing tradeoff; taking the whole service down is not.

ResilientThrottleMixin wraps allow_request() to catch exactly that failure
mode. Applied to every throttle class actually in use in this service
rather than monkeypatching DRF's own classes.
"""
import logging

import redis.exceptions
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

logger = logging.getLogger(__name__)


class ResilientThrottleMixin:
    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except redis.exceptions.RedisError as exc:
            logger.warning(
                "Redis unavailable during rate-limit check (%s: %s) — failing open "
                "(request allowed, unthrottled) rather than rejecting it. nginx's "
                "own rate limiting is unaffected and remains the primary defense "
                "for the duration of the outage.",
                type(self).__name__, exc,
            )
            return True


class ResilientAnonRateThrottle(ResilientThrottleMixin, AnonRateThrottle):
    pass


class ResilientUserRateThrottle(ResilientThrottleMixin, UserRateThrottle):
    pass


class FailClosedThrottleMixin:
    """The deliberate exception to this file's own "always fail open" rule
    (Phase 5, ADR 003 Decision 8 / ADR 004 Section 5) — for submission-
    creation rate limiting specifically, and nowhere else. An unmetered
    flood of new EssaySubmission rows during a Redis outage threatens the
    LLM cost ceiling directly (ADR 003 Decision 9 — real money), which
    outweighs briefly rejecting a legitimate student's submit (they can
    retry once Redis recovers, exactly like any other 429). Every other
    throttle on this platform fails open for availability; this one
    doesn't, because the risk it guards against is a different kind of
    harm. Do not "fix" this into fail-open to match the rest of this
    file without rereading that ADR reasoning first — that would silently
    undo an intentional design decision, not a bug."""
    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except redis.exceptions.RedisError as exc:
            logger.error(
                "Redis unavailable during submission rate-limit check (%s: %s) — "
                "failing CLOSED (request rejected) per ADR 003 Decision 8 / ADR "
                "004 Section 5.",
                type(self).__name__, exc,
            )
            # A real, previously-latent bug this exposed (found via Task
            # 5.1's own "Redis-outage-during-submission" test, live
            # end-to-end through the actual view, not just this mixin in
            # isolation): DRF calls throttle.wait() for every throttled
            # (False) response to compute Retry-After, and wait() reads
            # self.history — which the real SimpleRateThrottle.allow_request()
            # normally sets as a side effect before ever returning, but
            # never gets the chance to here since the RedisError fires
            # first. ResilientThrottleMixin above never hit this: it always
            # returns True, and DRF only calls wait() on a throttled
            # request. Set explicitly so a real Redis outage degrades to a
            # clean 429, not a 500 masking the outage.
            self.history = []
            return False


class FailClosedUserRateThrottle(FailClosedThrottleMixin, UserRateThrottle):
    pass
