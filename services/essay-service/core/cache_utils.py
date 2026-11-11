"""
cache_utils.py — graceful-degradation layer for Redis.

Django's native RedisCache backend (core/settings.py's CACHES) does not
catch connection failures itself — a cache.get()/cache.set() call against a
down Redis raises redis.exceptions.RedisError straight through to the
caller. safe_cache_get()/safe_cache_set()/safe_cache_delete() are drop-in
replacements that degrade to "cache miss" / "write silently skipped" on a
Redis-level failure instead of raising. Mirrors the pattern already proven
on assessment-service (Task 13.1) — see core/throttling_resilience.py for
the equivalent fix on the throttle-class side, which needs different
handling (fail *open*, not just "treat as empty").
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
            "until the entry's own TTL expires.", key, exc,
        )
