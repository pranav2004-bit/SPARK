"""Content cache (LIVETRACKER4.md section 2.10).

Versioned keys: every content write bumps the institution's version counter, so
every cached list for that institution becomes unreachable at once. No pattern
deletes are needed, and nothing outside the `content:` prefix is touched.
Cache failures never reach the client: reads fall through to the DB.
"""
import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("content.cache")

PREFIX = "content:institution:{inst}"


def _version_key(inst):
    return f"{PREFIX.format(inst=inst)}:version"


def _current_version(inst):
    try:
        version = cache.get(_version_key(inst))
        if version is None:
            cache.add(_version_key(inst), 1, timeout=None)
            version = cache.get(_version_key(inst)) or 1
        return version
    except Exception:
        logger.warning("content cache unavailable reading version; bypassing cache")
        return None


def _key(inst, suffix, version):
    digest = hashlib.sha256(suffix.encode("utf-8")).hexdigest()[:24]
    return f"{PREFIX.format(inst=inst)}:v{version}:{digest}"


def get(inst, suffix):
    version = _current_version(inst)
    if version is None:
        return None
    try:
        return cache.get(_key(inst, suffix, version))
    except Exception:
        logger.warning("content cache read failed; falling through to database")
        return None


def set(inst, suffix, value):
    version = _current_version(inst)
    if version is None:
        return
    try:
        cache.set(_key(inst, suffix, version), value, timeout=getattr(settings, "CONTENT_CACHE_TTL_SECONDS", 60))
    except Exception:
        logger.warning("content cache write failed; response served uncached")


def bump(inst):
    try:
        cache.incr(_version_key(inst))
    except ValueError:
        cache.add(_version_key(inst), 2, timeout=None)
    except Exception:
        logger.warning("content cache invalidation failed; entries expire by TTL")
