"""
test_quota_tracker.py — unit tests against a mocked Redis client, not a
real Redis connection (matching this project's own convention of mocking
external I/O in tests — e.g. user_service_client's calls are mocked, not
hit for real). QuotaTracker's own Lua script correctness was verified by
direct code reading against CLAP's real source (see quota_tracker.py's
own docstring); these tests verify essay-service's wrapper logic around
it: safety-margin math, key naming, and the fail-open behavior.
"""
from unittest.mock import MagicMock

import pytest
import redis.exceptions

from essays.quota_tracker import QuotaTracker, _key_hash


def _mock_redis(script_return):
    client = MagicMock()
    script = MagicMock(return_value=script_return)
    client.register_script.return_value = script
    return client, script


class TestQuotaTrackerConstructor:
    def test_safety_margin_applied_via_floor_not_raw_product(self):
        # CLAP's own verified arithmetic: floor(3 * 0.90) = floor(2.7) = 2,
        # not 2.7 — the exact bug ADR 004 Section 3's own self-audit found
        # and corrected in its capacity table.
        client, _ = _mock_redis([1, "ok", 0, 0])
        tracker = QuotaTracker(client, rpm_limit=3, safety_margin=0.90)
        assert tracker.rpm_limit == 2

    def test_default_limits_match_claps_verified_numbers(self):
        client, _ = _mock_redis([1, "ok", 0, 0])
        tracker = QuotaTracker(client)
        assert tracker.rpm_limit == 2       # floor(3 * 0.90)
        assert tracker.rpd_limit == 180      # floor(200 * 0.90)
        assert tracker.tpm_limit == 54000    # floor(60_000 * 0.90)
        assert tracker.tpd_limit == 180000   # floor(200_000 * 0.90)

    def test_floors_never_go_below_the_documented_minimums(self):
        client, _ = _mock_redis([1, "ok", 0, 0])
        tracker = QuotaTracker(client, rpm_limit=1, rpd_limit=1, tpm_limit=1, tpd_limit=1, safety_margin=0.1)
        assert tracker.rpm_limit == 1
        assert tracker.rpd_limit == 1
        assert tracker.tpm_limit == 100
        assert tracker.tpd_limit == 1000

    def test_from_settings_reads_django_settings(self, settings):
        settings.OPENAI_QUOTA_RPM_LIMIT = 10
        settings.OPENAI_QUOTA_SAFETY_MARGIN = 1.0
        client, _ = _mock_redis([1, "ok", 0, 0])
        tracker = QuotaTracker.from_settings(client)
        assert tracker.rpm_limit == 10


class TestKeyHashing:
    def test_never_stores_the_raw_key(self):
        h = _key_hash("sk-supersecretkey1234")
        assert "sk-supersecretkey1234" not in h

    def test_hash_is_deterministic(self):
        assert _key_hash("same-key") == _key_hash("same-key")

    def test_different_keys_hash_differently(self):
        assert _key_hash("key-a") != _key_hash("key-b")


class TestCheckAndReserve:
    def test_returns_granted_true_when_script_grants_reservation(self):
        client, script = _mock_redis([1, "ok", 0, 0])
        tracker = QuotaTracker(client)
        granted, reason, wait = tracker.check_and_reserve("sk-test", 500)
        assert granted is True
        assert reason is None
        assert wait == 0
        script.assert_called_once()

    def test_returns_denial_reason_and_wait_when_script_denies_reservation(self):
        client, _ = _mock_redis([0, "rpm", 2, 60])
        tracker = QuotaTracker(client)
        granted, reason, wait = tracker.check_and_reserve("sk-test", 500)
        assert granted is False
        assert reason == "rpm"
        assert wait == 60

    def test_reports_a_daily_denial_reason_distinctly_from_a_temporary_one(self):
        # Real bug this distinction fixes: llm_client used to be unable to
        # tell an RPM/TPM (short) denial apart from an RPD/TPD (daily)
        # one, so every all-keys-denied case fell through to a full-day
        # wait regardless of the actual cause.
        client, _ = _mock_redis([0, "rpd", 150, 43200])
        tracker = QuotaTracker(client)
        granted, reason, wait = tracker.check_and_reserve("sk-test", 500)
        assert granted is False
        assert reason == "rpd"
        assert wait == 43200

    def test_wait_seconds_is_never_zero_on_a_denial(self):
        # A TTL of 0 (e.g. a key expiring exactly now) must still produce
        # a positive wait — retrying with a 0s countdown would hammer
        # instead of backing off at all.
        client, _ = _mock_redis([0, "tpm", 100, 0])
        tracker = QuotaTracker(client)
        _, _, wait = tracker.check_and_reserve("sk-test", 500)
        assert wait >= 1

    def test_passes_all_four_limits_and_estimated_tokens_as_args(self):
        client, script = _mock_redis([1, "ok", 0, 0])
        tracker = QuotaTracker(client, rpm_limit=10, safety_margin=1.0)
        tracker.check_and_reserve("sk-test", 777)
        _, call_kwargs = script.call_args
        assert call_kwargs["args"][-1] == 777

    def test_fails_open_on_redis_error(self):
        client = MagicMock()
        script = MagicMock(side_effect=redis.exceptions.RedisError("connection refused"))
        client.register_script.return_value = script
        tracker = QuotaTracker(client)
        # ADR 003 Decision 8 point 1: a Redis outage must not block a real
        # evaluation a student is waiting on.
        granted, reason, wait = tracker.check_and_reserve("sk-test", 500)
        assert granted is True
        assert reason is None
