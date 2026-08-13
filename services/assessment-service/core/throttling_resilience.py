"""
Task 13.1 — Redis graceful degradation for DRF's throttle classes.

DRF's SimpleRateThrottle.allow_request() calls `self.cache.get(self.key, [])`
with no exception handling of its own — confirmed by reading the framework
source (rest_framework/throttling.py) before writing this fix, not assumed.
Every throttle in this service (the DEFAULT_THROTTLE_CLASSES applied to
nearly every request, plus AnswerSubmitRateThrottle and
ActivityLogRateThrottle) inherits this. Left as-is, a Redis outage would
make almost every request in the service raise instead of just serving
slower or unthrottled — a single dependency failure cascading into a
near-total outage, exactly what this task's objective says must not happen.

The correct failure mode for a rate limiter specifically (unlike a cache
whose job is correctness-neutral speedup) is to *fail open*: if Redis is
down, the safe choice is to stop throttling temporarily, not to reject
every request. nginx remains the primary rate limiter throughout this
outage (core/settings.py's REST_FRAMEWORK comment already documents that
convention) — losing this defense-in-depth layer for the outage's duration
is an acceptable, self-healing tradeoff; taking the whole service down is
not.

ResilientThrottleMixin wraps allow_request() to catch exactly that failure
mode. Applied to every throttle class actually in use in this service
(see throttling.py and settings.py's DEFAULT_THROTTLE_CLASSES) rather than
monkeypatching DRF's own classes.
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
