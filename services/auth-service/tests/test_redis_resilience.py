"""
Redis graceful-degradation tests for auth-service's throttles.

Real live incident (2026-08-17): a Redis outage crashed POST /api/auth/login/
with an unhandled redis.exceptions.ConnectionError — DRF's throttle check has
no exception handling of its own, and this service's throttles (both
DEFAULT_THROTTLE_CLASSES and the custom per-account LoginAttemptThrottle)
weren't wrapped to catch it. A follow-up audit found the identical gap on
POST /api/auth/token/refresh/ — the endpoint every student's browser calls
automatically partway through any exam longer than the 15-minute access
token lifetime; a Redis blip there would force-log-out a student mid-exam
even though their exam session is completely intact server-side.

Fixed with core/throttling_resilience.py's ResilientThrottleMixin (mirrors
assessment-service's own Task 13.1 fix), applied to both the default
throttles and LoginAttemptThrottle. These tests reproduce the exact outage
condition against the real endpoints and assert they now degrade (fail
open — request allowed, unthrottled) instead of raising.

The test settings' CACHES backend is LocMemCache, not Redis, so it can
never actually raise redis.exceptions.RedisError on its own — patching
RedisCacheClient.get to raise directly simulates the outage without
needing a real Redis instance to kill (a live Docker-stack re-test —
actually simulating the outage against the running container — was also
done separately; see docs/assessment-service-operations.md's "Known
Incident" section).
"""
import json
from unittest.mock import patch

import pytest
import redis.exceptions
from django.test import Client


def _post(url, data):
    client = Client()
    return client.post(url, data=json.dumps(data), content_type="application/json")


@pytest.mark.django_db
def test_login_fails_open_when_redis_is_down(admin_user):
    with patch(
        "django.core.cache.backends.redis.RedisCacheClient.get",
        side_effect=redis.exceptions.ConnectionError("down"),
    ):
        resp = _post("/api/auth/login/", {"email": "admin@test.com", "password": "Admin@pass1", "role": "admin"})
    # A real login (right credentials) still succeeds — the throttle check
    # failing open must not block or corrupt the actual login logic.
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.django_db
def test_wrong_password_still_correctly_rejected_when_redis_is_down(admin_user):
    # Failing open on the throttle must not accidentally fail open on
    # actual credential validation too — a down Redis is not a bypass.
    with patch(
        "django.core.cache.backends.redis.RedisCacheClient.get",
        side_effect=redis.exceptions.ConnectionError("down"),
    ):
        resp = _post("/api/auth/login/", {"email": "admin@test.com", "password": "wrongpass", "role": "admin"})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_token_refresh_fails_open_when_redis_is_down(admin_user):
    tokens = _post(
        "/api/auth/login/", {"email": "admin@test.com", "password": "Admin@pass1", "role": "admin"}
    ).json()["data"]

    with patch(
        "django.core.cache.backends.redis.RedisCacheClient.get",
        side_effect=redis.exceptions.ConnectionError("down"),
    ):
        resp = _post("/api/auth/token/refresh/", {"refresh": tokens["refresh_token"]})

    # The scenario this closes: a student's access token expiring mid-exam
    # during a Redis blip must still refresh successfully, not force a
    # logout out of a live exam session.
    assert resp.status_code == 200
    assert "access" in resp.json()
