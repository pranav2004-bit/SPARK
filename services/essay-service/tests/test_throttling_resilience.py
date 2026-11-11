"""
test_throttling_resilience.py — FailClosedThrottleMixin (Phase 5, ADR 003
Decision 8 / ADR 004 Section 5), the deliberate exception to this
service's otherwise-universal fail-open throttle policy. No existing test
covered ResilientThrottleMixin either (verified — none existed before
this file), so this also gives the fail-open mixin its first direct unit
test for contrast, alongside the new fail-closed one.
"""
from unittest.mock import MagicMock, patch

import redis.exceptions

from core.throttling_resilience import ResilientThrottleMixin, FailClosedThrottleMixin, FailClosedUserRateThrottle


class _AlwaysErrorsBase:
    def allow_request(self, request, view):
        raise redis.exceptions.RedisError("connection refused")


class _AlwaysAllowsBase:
    def allow_request(self, request, view):
        return True


class ResilientTestThrottle(ResilientThrottleMixin, _AlwaysErrorsBase):
    pass


class FailClosedTestThrottle(FailClosedThrottleMixin, _AlwaysErrorsBase):
    pass


class FailClosedPassthroughThrottle(FailClosedThrottleMixin, _AlwaysAllowsBase):
    pass


class TestResilientThrottleMixinFailsOpen:
    def test_redis_error_allows_the_request(self):
        throttle = ResilientTestThrottle()
        assert throttle.allow_request(MagicMock(), MagicMock()) is True


class TestFailClosedThrottleMixinFailsClosed:
    def test_redis_error_rejects_the_request(self):
        throttle = FailClosedTestThrottle()
        assert throttle.allow_request(MagicMock(), MagicMock()) is False

    def test_no_error_defers_to_the_real_throttle_result(self):
        throttle = FailClosedPassthroughThrottle()
        assert throttle.allow_request(MagicMock(), MagicMock()) is True

    def test_logs_at_error_level_not_warning(self, caplog):
        import logging
        throttle = FailClosedTestThrottle()
        with caplog.at_level(logging.ERROR, logger="core.throttling_resilience"):
            throttle.allow_request(MagicMock(), MagicMock())
        assert any(r.levelname == "ERROR" for r in caplog.records)

    def test_sets_history_so_drfs_own_wait_call_does_not_crash(self):
        # Real, previously-latent bug this test caught (found via a live,
        # view-level Redis-outage test on the actual submit endpoint, not
        # first spotted here): DRF calls throttle.wait() for every
        # throttled (False) response to compute Retry-After, and the real
        # SimpleRateThrottle.wait() reads self.history — never set here
        # since the RedisError fires before the real allow_request() gets
        # a chance to set it. A fail-open mixin never surfaces this (DRF
        # only calls wait() on a throttled request), which is why this bug
        # stayed hidden until the fail-closed mixin returned False for the
        # first time. Uses the real FailClosedUserRateThrottle (real DRF
        # SimpleRateThrottle underneath), not a fake stub, so wait()'s own
        # other attribute reads (self.duration etc.) are exercised for real.
        throttle = FailClosedUserRateThrottle()
        throttle.scope = "user"
        with patch("django.core.cache.cache.get", side_effect=redis.exceptions.RedisError("down")):
            assert throttle.allow_request(MagicMock(user=MagicMock(pk=1), META={}), MagicMock()) is False
        throttle.wait()  # must not raise AttributeError
