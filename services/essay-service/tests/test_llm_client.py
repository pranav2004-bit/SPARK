"""
test_llm_client.py — mocks the OpenAI SDK and the quota tracker entirely;
no real network call is ever made in this test suite. Verifies the
transient/malformed/permanent error classification ported from CLAP's own
openai_client.py (verified by direct code reading).
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from essays.llm_client import (
    call_openai_evaluate, LLMTransientError, LLMMalformedResponseError, LLMPermanentError,
)
from essays.quota_tracker import QuotaDailyExhaustedException, QuotaTemporarilyUnavailableException

MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]


def _mock_response(content: dict):
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=json.dumps(content)))]
    return resp


@pytest.fixture(autouse=True)
def _one_api_key(settings):
    settings.OPENAI_API_KEYS = ["sk-test-key-1"]


@pytest.fixture
def mock_quota_always_grants():
    with patch("essays.llm_client.QuotaTracker.from_settings") as mock_from_settings:
        tracker = MagicMock()
        tracker.check_and_reserve.return_value = (True, None, 0)
        mock_from_settings.return_value = tracker
        yield tracker


@pytest.fixture(autouse=True)
def _no_real_redis():
    with patch("essays.llm_client._redis_client", return_value=MagicMock()):
        yield


class TestCallOpenaiEvaluateSuccess:
    def test_returns_parsed_json_on_success(self, mock_quota_always_grants):
        with patch("openai.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = _mock_response(
                {"score": 8, "feedback": {"overall": "Good", "breakdown": {}}}
            )
            result = call_openai_evaluate(MESSAGES)
        assert result.parsed == {"score": 8, "feedback": {"overall": "Good", "breakdown": {}}}

    def test_returns_trace_data_alongside_the_parsed_result(self, mock_quota_always_grants, settings):
        # Phase 7, Task 7.1's own "LLM trace/debug view" requirement:
        # call_openai_evaluate now returns an LLMEvaluationResult, not a
        # bare dict — the raw response text, OpenAI's own request id, and
        # the model used must all come through alongside the parsed score/
        # feedback, not just be silently dropped like before this phase.
        settings.OPENAI_MODEL = "gpt-4o-mini"
        with patch("openai.OpenAI") as MockClient:
            resp = _mock_response({"score": 8, "feedback": {"overall": "Good", "breakdown": {}}})
            resp.id = "chatcmpl-abc123"
            resp.model = "gpt-4o-mini-2024-07-18"
            MockClient.return_value.chat.completions.create.return_value = resp
            result = call_openai_evaluate(MESSAGES)
        assert result.raw_response == resp.choices[0].message.content
        assert result.request_id == "chatcmpl-abc123"
        assert result.model == "gpt-4o-mini-2024-07-18"

    def test_uses_json_mode_and_configured_model(self, mock_quota_always_grants, settings):
        settings.OPENAI_MODEL = "gpt-4o-mini"
        with patch("openai.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = _mock_response({"score": 5, "feedback": {"overall": "ok"}})
            call_openai_evaluate(MESSAGES)
            _, kwargs = MockClient.return_value.chat.completions.create.call_args
            assert kwargs["response_format"] == {"type": "json_object"}
            assert kwargs["model"] == "gpt-4o-mini"


class TestErrorClassification:
    def test_no_api_keys_configured_raises_permanent(self, settings):
        settings.OPENAI_API_KEYS = []
        with pytest.raises(LLMPermanentError):
            call_openai_evaluate(MESSAGES)

    def test_connection_error_raises_transient(self, mock_quota_always_grants):
        import openai
        with patch("openai.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.side_effect = openai.APIConnectionError(request=MagicMock())
            with pytest.raises(LLMTransientError):
                call_openai_evaluate(MESSAGES)

    def test_timeout_error_raises_transient(self, mock_quota_always_grants):
        import openai
        with patch("openai.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.side_effect = openai.APITimeoutError(request=MagicMock())
            with pytest.raises(LLMTransientError):
                call_openai_evaluate(MESSAGES)

    def test_malformed_json_response_raises_malformed(self, mock_quota_always_grants):
        with patch("openai.OpenAI") as MockClient:
            resp = MagicMock()
            resp.choices = [MagicMock(message=MagicMock(content="not valid json{"))]
            MockClient.return_value.chat.completions.create.return_value = resp
            with pytest.raises(LLMMalformedResponseError):
                call_openai_evaluate(MESSAGES)

    def test_generic_openai_error_raises_permanent(self, mock_quota_always_grants):
        import openai
        with patch("openai.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.side_effect = openai.AuthenticationError(
                message="invalid api key", response=MagicMock(status_code=401), body=None,
            )
            with pytest.raises(LLMPermanentError):
                call_openai_evaluate(MESSAGES)


class TestKeyRotationAndQuota:
    def test_skips_a_quota_exhausted_key_and_tries_the_next(self, settings):
        settings.OPENAI_API_KEYS = ["sk-key-1", "sk-key-2"]
        with patch("essays.llm_client.QuotaTracker.from_settings") as mock_from_settings:
            tracker = MagicMock()
            tracker.check_and_reserve.side_effect = [(False, "rpm", 60), (True, None, 0)]  # key-1 denied, key-2 granted
            mock_from_settings.return_value = tracker
            with patch("openai.OpenAI") as MockClient:
                MockClient.return_value.chat.completions.create.return_value = _mock_response(
                    {"score": 7, "feedback": {"overall": "fine"}}
                )
                result = call_openai_evaluate(MESSAGES)
        assert result.parsed["score"] == 7
        assert tracker.check_and_reserve.call_count == 2

    def test_all_keys_daily_exhausted_raises_daily_exhausted(self, settings):
        settings.OPENAI_API_KEYS = ["sk-key-1"]
        with patch("essays.llm_client.QuotaTracker.from_settings") as mock_from_settings:
            tracker = MagicMock()
            tracker.check_and_reserve.return_value = (False, "rpd", 3600)
            mock_from_settings.return_value = tracker
            with pytest.raises(QuotaDailyExhaustedException):
                call_openai_evaluate(MESSAGES)

    def test_all_keys_rpm_denied_raises_temporarily_unavailable_not_daily(self, settings):
        # Real bug found and fixed during this phase's own audit: an
        # RPM/TPM denial (a short per-minute cooldown) must never be
        # treated as a full daily exhaustion — that would make every busy
        # deployment wait an hour on what's actually a ~60s blip,
        # contradicting ADR 004 Section 3's own capacity math.
        settings.OPENAI_API_KEYS = ["sk-key-1"]
        with patch("essays.llm_client.QuotaTracker.from_settings") as mock_from_settings:
            tracker = MagicMock()
            tracker.check_and_reserve.return_value = (False, "rpm", 42)
            mock_from_settings.return_value = tracker
            with pytest.raises(QuotaTemporarilyUnavailableException) as exc_info:
                call_openai_evaluate(MESSAGES)
        assert exc_info.value.wait_seconds == 42

    def test_one_temporary_denial_among_keys_wins_over_a_daily_one(self, settings):
        # Even if a LATER key in rotation is daily-denied, one EARLIER
        # key's merely-temporary denial must still classify the whole
        # attempt as temporarily-unavailable, not daily-exhausted — not
        # just "whichever key happened to be checked last".
        settings.OPENAI_API_KEYS = ["sk-key-1", "sk-key-2"]
        with patch("essays.llm_client.QuotaTracker.from_settings") as mock_from_settings:
            tracker = MagicMock()
            tracker.check_and_reserve.side_effect = [(False, "rpm", 30), (False, "rpd", 3600)]
            mock_from_settings.return_value = tracker
            with pytest.raises(QuotaTemporarilyUnavailableException):
                call_openai_evaluate(MESSAGES)

    def test_rate_limited_key_rotates_and_raises_temporarily_unavailable_if_all_limited(self, mock_quota_always_grants):
        import openai
        mock_quota_always_grants.check_and_reserve.return_value = (True, None, 0)
        with patch("openai.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.side_effect = openai.RateLimitError(
                message="rate limited", response=MagicMock(status_code=429), body=None,
            )
            with pytest.raises(QuotaTemporarilyUnavailableException):
                call_openai_evaluate(MESSAGES)
