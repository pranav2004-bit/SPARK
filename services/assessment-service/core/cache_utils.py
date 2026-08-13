"""
cache_utils.py — Task 13.1's graceful-degradation layer for Redis.

Django's native RedisCache backend (core/settings.py's CACHES) does not
catch connection failures itself — a `cache.get()`/`cache.set()` call
against a down Redis raises `redis.exceptions.RedisError` straight through
to the caller. Verified this is a real, current gap before writing this
fix, not an assumption: with Redis stopped, both the Analytics/Dashboard
views (which read/write the cache directly) and — more seriously — every
throttled request (DRF's SimpleRateThrottle.allow_request() calls
`self.cache.get()` with no exception handling of its own) would 500
instead of degrading, meaning a Redis outage would currently take down
most of the service's traffic, not just the two views the tracker names as
the example.

safe_cache_get()/safe_cache_set() are drop-in replacements for
cache.get()/cache.set() that degrade to "cache miss" / "write silently
skipped" on a Redis-level failure instead of raising — used by the
Analytics/Dashboard views and by scoring.py's finalize_sessions() (whose
own cache.delete() call, Task 9.1's dashboard-invalidation hook, sits on
the critical exam-submission path and must never be able to fail a
submit). See core/throttling_resilience.py for the equivalent fix on the
throttle-class side, which needs different handling (fail *open*, not just
"treat as empty").
"""
import logging

import redis.exceptions
from django.core.cache import cache

logger = logging.getLogger(__name__)


def safe_cache_get(key, default=None):
    try:
        return cache.get(key, default)
    except redis.exceptions.RedisError as exc:
        logger.warning("Redis unavailable on cache read (key=%s): %s — treating as a cache miss.", key, exc)
        return default


def safe_cache_set(key, value, timeout):
    try:
        cache.set(key, value, timeout)
    except redis.exceptions.RedisError as exc:
        logger.warning("Redis unavailable on cache write (key=%s): %s — result not cached.", key, exc)


def safe_cache_delete(key):
    try:
        cache.delete(key)
    except redis.exceptions.RedisError as exc:
        logger.warning(
            "Redis unavailable on cache invalidation (key=%s): %s — stale data may be served "
            "until the entry's own TTL expires (a defensive-backstop TTL exists for exactly "
            "this case; see scoring.py/views.py's cache-key comments).", key, exc,
        )
