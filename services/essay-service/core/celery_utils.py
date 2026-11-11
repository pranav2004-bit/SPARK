"""
celery_utils.py — graceful-degradation layer for Celery task dispatch,
mirroring core/cache_utils.py's safe_cache_* pattern for the broker side.

.delay()/.apply_async() does not raise redis.exceptions.RedisError when the
broker is unreachable (unlike Django's cache backend) — Celery dispatches
through Kombu's own transport abstraction, which wraps the underlying
connection failure as kombu.exceptions.OperationalError instead. Confirmed
live by reproducing a real Redis outage and catching the actual exception
type raised, not assumed from documentation. safe_task_dispatch() is a
drop-in wrapper that degrades to "not dispatched, already logged" instead of
raising, so a caller (an HTTP view or another Celery task) never crashes or
gets stuck mid-batch just because the broker was down at that exact moment.
"""
import logging

import kombu.exceptions
import redis.exceptions

BROKER_ERRORS = (kombu.exceptions.KombuError, redis.exceptions.RedisError)


def safe_task_dispatch(task, *args, dispatch_logger=None, context="", **kwargs):
    """Calls task.delay(*args, **kwargs), catching broker-unreachable
    errors. Returns True if the task was actually dispatched, False if the
    broker was unreachable (already logged as an error) — never raises
    BROKER_ERRORS itself."""
    try:
        task.delay(*args, **kwargs)
        return True
    except BROKER_ERRORS as exc:
        (dispatch_logger or logging.getLogger("essays.llm")).error(
            "%s dispatch failed (broker unreachable): %s", context or task.name, exc,
        )
        return False
