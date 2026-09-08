"""
Redis graceful degradation for DRF's throttle classes.

DRF's SimpleRateThrottle.allow_request() calls `self.cache.get(self.key, [])`
with no exception handling of its own. Every throttle in this service
(DEFAULT_THROTTLE_CLASSES, applied to nearly every request) inherits this.
Left as-is, a Redis outage makes almost every request in the service raise
a 500 instead of just serving unthrottled — a single dependency failure
cascading into a near-total outage.

Real live incident (2026-08-17): this exact gap crashed auth-service's
login endpoint with an unhandled redis.exceptions.ConnectionError when the
shared Redis container went down, and a follow-up audit found the same gap
in every other service's default throttle setup, including this one.
assessment-service already had this fix (its own core/throttling_resilience.py,
Task 13.1); this mirrors that pattern here rather than inventing a new one.

The correct failure mode for a rate limiter specifically (unlike a cache
whose job is correctness-neutral speedup) is to *fail open*: if Redis is
down, the safe choice is to stop throttling temporarily, not reject every
request. nginx's own per-IP rate limiting is unaffected and remains the
primary defense for the duration of the outage.

ResilientThrottleMixin wraps allow_request() to catch exactly that failure
mode. Applied to every throttle class actually in use in this service.
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
