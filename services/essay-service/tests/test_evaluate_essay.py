"""
test_evaluate_essay.py — Task 5.2's own testing checklist: positive
(normal essay scores correctly), negative (malformed LLM JSON handled
without crashing), edge (word-limit boundary essay, PII confirmed
redacted before the outbound call via a mocked call inspecting the actual
payload), idempotency (re-running on an already-scored submission is a
no-op), and the retry-ceiling/DLQ branching from ADR 003 Decision 6.

call_openai_evaluate is always mocked — no real network/LLM call is ever
made anywhere in this suite.
"""
import types
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from essays.llm_client import LLMTransientError, LLMMalformedResponseError, LLMPermanentError, LLMEvaluationResult
from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt, EssaySubmission, EssayScore,
    EssayFailedJob, SUBMISSION_STATUS_PENDING, SUBMISSION_STATUS_LLM_PROCESSING,
    SUBMISSION_STATUS_LLM_COMPLETE, SUBMISSION_STATUS_LLM_FAILED, SUBMISSION_STATUS_REPORT_READY,
)
from essays.tasks import evaluate_essay, _retry_or_dlq

from .conftest import INSTITUTION_A, ADMIN_USER_ID


@pytest.fixture
def submission_with_response(db):
    def _make(draft_response="A thoughtful essay about the assigned topic.", rubric="Score on clarity and evidence."):
        paper = EssayPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
        eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
        EssayQuestion.objects.create(
            set=eset, question_text="Discuss the topic.", llm_rubric_prompt=rubric, word_limit=500, time_limit_minutes=30,
        )
        assignment = EssayAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
        )
        attempt = EssayAttempt.objects.create(
            assignment=assignment, student_id=uuid.uuid4(), set=eset,
            ends_at=timezone.now() + timedelta(hours=1), draft_response=draft_response,
        )
        submission = EssaySubmission.objects.create(attempt=attempt)
        return submission
    return _make


def _fake_self(retries=0):
    return types.SimpleNamespace(request=types.SimpleNamespace(retries=retries), retry=lambda **kw: Exception("retry-called"))


def _llm_result(score, feedback, raw_response="{}", request_id="req-test-1", model="gpt-4o-mini"):
    """Phase 7, Task 7.1 changed call_openai_evaluate's return contract
    from a bare parsed dict to LLMEvaluationResult (parsed + raw_response/
    request_id/model, for the new LLM trace/debug view) — every mock in
    this file that stands in for a real call_openai_evaluate call must
    return this same shape now, or _evaluate_essay_impl's own `result.parsed`
    read raises AttributeError on a bare dict instead of exercising the
    behavior the test actually means to exercise."""
    return LLMEvaluationResult(
        parsed={"score": score, "feedback": feedback}, raw_response=raw_response,
        request_id=request_id, model=model,
    )


class TestNoSubmissionGuard:
    def test_empty_draft_never_calls_llm(self, submission_with_response):
        submission = submission_with_response(draft_response="")
        with patch("essays.llm_client.call_openai_evaluate") as mock_call:
            evaluate_essay.apply(args=[str(submission.id)])
            mock_call.assert_not_called()

        score = EssayScore.objects.get(submission=submission)
        assert score.score == 0
        assert score.is_no_submission is True
        submission.refresh_from_db()
        # Phase 11: LLM_COMPLETE auto-chains into generate_essay_report
        # (dispatched from _transition_submission_status, essays/tasks.py)
        # — under CELERY_TASK_ALWAYS_EAGER (test_settings.py) that runs
        # synchronously within this same .apply() call, so the terminal
        # status by the time control returns here is REPORT_READY, not
        # the pre-Phase-11 LLM_COMPLETE.
        assert submission.status == SUBMISSION_STATUS_REPORT_READY

    def test_whitespace_only_draft_treated_as_no_submission(self, submission_with_response):
        submission = submission_with_response(draft_response="   \n\t  ")
        evaluate_essay.apply(args=[str(submission.id)])
        assert EssayScore.objects.get(submission=submission).is_no_submission is True


class TestIdempotency:
    def test_already_scored_submission_is_a_noop(self, submission_with_response):
        submission = submission_with_response()
        EssayScore.objects.create(submission=submission, score=7, feedback={"overall": "ok"})
        with patch("essays.llm_client.call_openai_evaluate") as mock_call:
            result = evaluate_essay.apply(args=[str(submission.id)]).result
        mock_call.assert_not_called()
        assert result["reason"] == "already_scored"
        assert EssayScore.objects.filter(submission=submission).count() == 1

    def test_already_scored_but_stuck_status_is_self_healed(self, submission_with_response):
        # Real, narrow gap found by this phase's own final audit: a worker
        # crash between EssayScore creation and the LLM_COMPLETE
        # transition (two separate writes, no acks_late) would otherwise
        # leave a real score permanently stuck on an LLM_PROCESSING
        # submission with no DLQ entry for the sweeper to ever find. The
        # idempotency check itself must repair this, not just skip.
        submission = submission_with_response()
        EssayScore.objects.create(submission=submission, score=7, feedback={"overall": "ok"})
        submission.status = SUBMISSION_STATUS_LLM_PROCESSING
        submission.save(update_fields=["status"])

        with patch("essays.llm_client.call_openai_evaluate") as mock_call:
            evaluate_essay.apply(args=[str(submission.id)])

        mock_call.assert_not_called()
        submission.refresh_from_db()
        # Phase 11: see test_empty_draft_never_calls_llm's own comment above.
        assert submission.status == SUBMISSION_STATUS_REPORT_READY


class TestPositiveScoring:
    def test_normal_essay_scores_correctly(self, submission_with_response):
        submission = submission_with_response()
        with patch(
            "essays.llm_client.call_openai_evaluate",
            return_value=_llm_result(8, {"overall": "A strong response.", "breakdown": {}}),
        ):
            evaluate_essay.apply(args=[str(submission.id)])

        score = EssayScore.objects.get(submission=submission)
        assert score.score == 8
        assert score.is_no_submission is False
        assert score.evaluated_by == "llm"
        submission.refresh_from_db()
        # Phase 11: see test_empty_draft_never_calls_llm's own comment above.
        assert submission.status == SUBMISSION_STATUS_REPORT_READY
        assert submission.report_html and "8 / 10" in submission.report_html

    def test_llm_trace_persisted_on_successful_evaluation(self, submission_with_response):
        # Phase 7, Task 7.1's own "LLM trace/debug view" requirement — the
        # exact prompt, the raw response, the request id, and when it was
        # evaluated must all be genuinely persisted, not just threaded
        # through and silently dropped.
        from essays.models import EssayLLMTrace
        submission = submission_with_response()
        with patch(
            "essays.llm_client.call_openai_evaluate",
            return_value=_llm_result(
                8, {"overall": "A strong response.", "breakdown": {}},
                raw_response='{"score": 8, "feedback": {"overall": "A strong response."}}',
                request_id="chatcmpl-xyz789", model="gpt-4o-mini-2024-07-18",
            ),
        ):
            evaluate_essay.apply(args=[str(submission.id)])

        trace = EssayLLMTrace.objects.get(submission=submission)
        assert trace.raw_response == '{"score": 8, "feedback": {"overall": "A strong response."}}'
        assert trace.request_id == "chatcmpl-xyz789"
        assert trace.model_used == "gpt-4o-mini-2024-07-18"
        assert isinstance(trace.prompt_messages, list) and len(trace.prompt_messages) == 2
        assert trace.prompt_messages[0]["role"] == "system"

    def test_float_score_rounded_to_int(self, submission_with_response):
        submission = submission_with_response()
        with patch(
            "essays.llm_client.call_openai_evaluate",
            return_value=_llm_result(7.6, {"overall": "Good work overall.", "breakdown": {}}),
        ):
            evaluate_essay.apply(args=[str(submission.id)])
        assert EssayScore.objects.get(submission=submission).score == 8

    def test_pii_redacted_before_outbound_call(self, submission_with_response):
        submission = submission_with_response(draft_response="Contact me at student@example.com for more info about this essay.")
        with patch(
            "essays.llm_client.call_openai_evaluate",
            return_value=_llm_result(5, {"overall": "Adequate response.", "breakdown": {}}),
        ) as mock_call:
            evaluate_essay.apply(args=[str(submission.id)])

        messages = mock_call.call_args[0][0]
        full_payload = " ".join(m["content"] for m in messages)
        assert "student@example.com" not in full_payload
        assert "[REDACTED_EMAIL]" in full_payload

    def test_essay_at_exactly_word_limit_boundary(self, submission_with_response):
        essay_500_words = " ".join(["word"] * 500)
        submission = submission_with_response(draft_response=essay_500_words)
        with patch(
            "essays.llm_client.call_openai_evaluate",
            return_value=_llm_result(6, {"overall": "Reasonable coverage.", "breakdown": {}}),
        ):
            evaluate_essay.apply(args=[str(submission.id)])
        assert EssayScore.objects.get(submission=submission).score == 6

    def test_non_english_mixed_script_essay(self, submission_with_response):
        submission = submission_with_response(draft_response="气候变化 is a mixed-script response with 中文 and English text.")
        with patch(
            "essays.llm_client.call_openai_evaluate",
            return_value=_llm_result(4, {"overall": "Understandable but limited.", "breakdown": {}}),
        ):
            evaluate_essay.apply(args=[str(submission.id)])
        assert EssayScore.objects.get(submission=submission).score == 4


class TestMalformedAndSemanticGuardRetry:
    def test_malformed_response_shape_retries_not_immediate_dlq(self, submission_with_response):
        submission = submission_with_response()
        # Real gap found while wiring Phase 7's LLMEvaluationResult return
        # change: this mock previously returned a bare dict (the pre-Phase-7
        # shape), which made _evaluate_essay_impl's `result.parsed` read
        # raise AttributeError instead of ever reaching the malformed-shape
        # check this test is actually meant to exercise — masked because
        # `pytest.raises(Exception)` doesn't check *which* exception. Fixed
        # by mocking the real post-Phase-7 shape (a valid LLMEvaluationResult
        # wrapping an invalid *parsed* payload), so this test once again
        # exercises the code path its own name promises.
        with patch("essays.llm_client.call_openai_evaluate", return_value=_llm_result("not-a-number", {})):
            with pytest.raises(Exception):  # Retry propagates in eager mode
                evaluate_essay.apply(args=[str(submission.id)], throw=True)
        assert EssayFailedJob.objects.count() == 0
        submission.refresh_from_db()
        assert submission.status == SUBMISSION_STATUS_LLM_PROCESSING  # not yet failed

    def test_semantic_guard_rejection_retries_not_immediate_dlq(self, submission_with_response):
        submission = submission_with_response()
        with patch(
            "essays.llm_client.call_openai_evaluate",
            return_value=_llm_result(10, {"overall": "A very weak and poor attempt.", "breakdown": {}}),
        ):
            with pytest.raises(Exception):
                evaluate_essay.apply(args=[str(submission.id)], throw=True)
        assert EssayFailedJob.objects.count() == 0

    def test_malformed_json_from_llm_client_retries(self, submission_with_response):
        submission = submission_with_response()
        with patch("essays.llm_client.call_openai_evaluate", side_effect=LLMMalformedResponseError("bad json")):
            with pytest.raises(Exception):
                evaluate_essay.apply(args=[str(submission.id)], throw=True)
        assert EssayFailedJob.objects.count() == 0


class TestTransientRetry:
    def test_transient_error_retries_not_immediate_dlq(self, submission_with_response):
        from celery.exceptions import Retry
        submission = submission_with_response()
        with patch("essays.llm_client.call_openai_evaluate", side_effect=LLMTransientError("connection reset")):
            # Task 17.1 — was `pytest.raises(Exception)`, broad enough to
            # also pass on a genuine bug: a real TypeError ("got multiple
            # values for argument 'submission_id'") from _retry_or_dlq's
            # retry() call reusing the original positional args alongside
            # its own kwargs override, found via live verification (not
            # this mocked suite), never this specific Retry type. Narrowed
            # so this exact regression can't silently pass again.
            with pytest.raises(Retry):
                evaluate_essay.apply(args=[str(submission.id)], throw=True)
        assert EssayFailedJob.objects.count() == 0
        submission.refresh_from_db()
        assert submission.status == SUBMISSION_STATUS_LLM_PROCESSING

    def test_transient_error_then_recovery_completes_without_crashing(self, submission_with_response):
        """Task 17.1's own real finding, made permanent: `_retry_or_dlq`
        used to call `self.retry(kwargs={"submission_id": ..., ...})` with
        no `args=` override, so Celery reused the ORIGINAL request's
        positional args (every real call site dispatches
        `evaluate_essay.delay(submission_id)` positionally) alongside the
        new kwargs — a `TypeError: evaluate_essay() got multiple values
        for argument 'submission_id'` fired at Celery's own argument-
        binding stage, before the task body (or any of its except-clauses)
        ever ran again. That silently broke automatic retry for every
        transient LLM error on every submission: a real outage would leave
        the submission stuck at LLM_PROCESSING forever, with no DLQ entry
        (since _record_dlq was never reached) and no operator visibility.
        The unit-level `_retry_or_dlq` tests below never caught this — they
        call it directly with a fake `self`, never exercising Celery's
        real argument-rebinding on the retried call the way `.apply()`
        does. This test drives the real end-to-end path: outage on the
        first call, provider recovered by the automatic retry, exactly
        Task 17.1's own live-verification scenario against the real dev
        stack, reproduced here so it can't regress silently again."""
        from celery.exceptions import Retry
        submission = submission_with_response()

        # Step 1: the outage. Confirms Retry (not a crash) and, critically,
        # inspects the Retry's own carried request to confirm _retry_or_dlq
        # built it with an empty `args` tuple — the actual bug was that
        # this was left as the original positional args, colliding with
        # the kwargs override below once Celery tried to rebind them.
        with patch("essays.llm_client.call_openai_evaluate", side_effect=LLMTransientError("connection refused (simulated outage)")):
            with pytest.raises(Retry) as exc_info:
                evaluate_essay.apply(args=[str(submission.id)], throw=True)
        retried_sig = exc_info.value.sig
        assert retried_sig.args == ()
        assert retried_sig.kwargs == {
            "submission_id": str(submission.id), "inline_retry_count": 1, "correlation_id": None,
        }

        # Step 2: the provider has recovered by the time the retry lands.
        # Celery's own real broker round-trip re-invokes evaluate_essay
        # with exactly `retried_request.args`/`.kwargs` — reproduced here
        # directly (not by relying on .apply() to auto-loop the retry,
        # which it does not do outside a real worker+broker) so this test
        # exercises the actual argument shape the fix produces, not an
        # environment-specific auto-retry behavior.
        fake_result = LLMEvaluationResult(
            parsed={"score": 8, "feedback": {"overall": "Well argued.", "breakdown": {}}},
            raw_response='{"score": 8, "feedback": {"overall": "Well argued.", "breakdown": {}}}',
            request_id="req_recovered", model="gpt-4o-mini",
        )
        with patch("essays.llm_client.call_openai_evaluate", return_value=fake_result):
            result = evaluate_essay.apply(args=retried_sig.args, kwargs=retried_sig.kwargs)

        assert result.state == "SUCCESS", result.traceback
        assert result.result["status"] == "ok"
        assert EssayFailedJob.objects.count() == 0
        submission.refresh_from_db()
        # LLM_COMPLETE is the direct outcome of this task; test settings
        # dispatch generate_essay_report eagerly on that transition (an
        # unrelated, expected downstream consequence, not a failure), so
        # REPORT_READY is an equally valid confirmation of success here.
        assert submission.status in (SUBMISSION_STATUS_LLM_COMPLETE, SUBMISSION_STATUS_REPORT_READY)
        assert submission.score.score == 8


class TestPermanentErrorImmediateDlq:
    def test_permanent_error_dlqs_immediately_no_retry(self, submission_with_response):
        submission = submission_with_response()
        with patch("essays.llm_client.call_openai_evaluate", side_effect=LLMPermanentError("content policy violation")):
            result = evaluate_essay.apply(args=[str(submission.id)]).result

        assert result["status"] == "failed"
        job = EssayFailedJob.objects.get(task_name="evaluate_essay")
        assert "content policy violation" in job.error
        assert job.attempts == 0  # never retried at all
        submission.refresh_from_db()
        assert submission.status == SUBMISSION_STATUS_LLM_FAILED


class TestSoftTimeLimitHandledCleanly:
    """Real gap found by this phase's own second final-audit round: ported
    from CLAP's own evaluate_writing (verified: time_limit=200,
    soft_time_limit=175 there) but never actually carried over — without
    it, a hung OpenAI call or hung Redis connection could block a worker
    slot indefinitely. Confirms the added time_limit/soft_time_limit pair
    is wired to a real DLQ-recording handler, not just decorator noise."""

    def test_soft_time_limit_exceeded_dlqs_and_marks_failed_then_reraises(self, submission_with_response):
        from celery.exceptions import SoftTimeLimitExceeded
        submission = submission_with_response()

        with patch("essays.tasks._evaluate_essay_impl", side_effect=SoftTimeLimitExceeded()):
            with pytest.raises(SoftTimeLimitExceeded):
                evaluate_essay.apply(args=[str(submission.id)], throw=True)

        job = EssayFailedJob.objects.get(task_name="evaluate_essay")
        assert "SoftTimeLimitExceeded" in job.error
        submission.refresh_from_db()
        assert submission.status == SUBMISSION_STATUS_LLM_FAILED


class TestRetryCeilingHelper:
    """Directly exercises _retry_or_dlq's branching — the ceiling-exceeded
    path can't be driven end-to-end through Celery's eager-mode retry
    semantics in a single test invocation (each .apply() call starts a
    fresh inline_retry_count=0), so this tests the same real function the
    task calls, with a controlled fake `self`."""

    def test_retries_while_under_ceiling(self, submission_with_response):
        submission = submission_with_response()
        fake_self = _fake_self()
        with pytest.raises(Exception):
            _retry_or_dlq(fake_self, submission, "evaluate_essay", str(submission.id), 0, LLMTransientError("x"))
        assert EssayFailedJob.objects.count() == 0

    def test_dlqs_once_ceiling_reached(self, submission_with_response):
        submission = submission_with_response()
        fake_self = _fake_self()
        # inline_retry_count=3: already had its 3 retries (4 total attempts).
        result = _retry_or_dlq(fake_self, submission, "evaluate_essay", str(submission.id), 3, LLMTransientError("still failing"))
        assert result["status"] == "failed"
        assert result["reason"] == "retry_ceiling_exceeded"
        job = EssayFailedJob.objects.get(task_name="evaluate_essay")
        assert job.attempts == 3
        submission.refresh_from_db()
        assert submission.status == SUBMISSION_STATUS_LLM_FAILED


class TestQuotaRetriesDoNotPolluteTheInlineBudget:
    """Real bug found and fixed during this phase's own audit: Celery's
    own `self.request.retries` increments identically on every
    self.retry() call regardless of cause (verified directly in Celery's
    source). Using it as evaluate_essay's inline-retry ceiling meant a
    submission that had already waited out several quota-exhaustion
    retries (which ADR 003 Decision 9 says must NEVER count against that
    budget) would see its very next genuine transient error DLQ'd
    immediately — appearing to have exhausted a budget it never actually
    touched. Fixed with an explicit `inline_retry_count` kwarg that only
    the transient/malformed retry path increments."""

    def test_many_quota_retries_then_a_transient_error_still_gets_the_full_inline_budget(self, submission_with_response):
        from essays.quota_tracker import QuotaTemporarilyUnavailableException

        submission = submission_with_response()
        call_count = {"n": 0}

        def flaky_call(messages):
            call_count["n"] += 1
            if call_count["n"] <= 5:
                # Simulate 5 quota-wait cycles — none of these should ever
                # count against the 3-attempt inline retry budget.
                raise QuotaTemporarilyUnavailableException(wait_seconds=0)
            raise LLMTransientError("still down after quota cleared")

        with patch("essays.llm_client.call_openai_evaluate", side_effect=flaky_call):
            # Each quota-wait retry and each inline retry raises (eager
            # mode doesn't auto-loop retries) — drive the chain manually,
            # exactly as Celery would via inline_retry_count passthrough.
            inline_retry_count = 0
            for _ in range(5):  # the 5 quota-wait cycles
                with pytest.raises(Exception):
                    evaluate_essay.apply(args=[str(submission.id), inline_retry_count], throw=True)
                # Quota-wait retries never change inline_retry_count.

            # Now the transient error starts — this must still get all 3
            # inline retries (not 0, which is what the pre-fix shared
            # counter would have given it after 5 prior retries).
            for expected_retry in range(3):
                with pytest.raises(Exception):
                    evaluate_essay.apply(args=[str(submission.id), inline_retry_count], throw=True)
                inline_retry_count += 1

            # Ceiling reached only now, after the full 3 inline attempts —
            # not after the first post-quota transient failure. Still
            # inside the patch context so this final call also hits the
            # mocked flaky_call, not the real (unconfigured) LLM client.
            assert EssayFailedJob.objects.filter(task_name="evaluate_essay").count() == 0
            result = evaluate_essay.apply(args=[str(submission.id), inline_retry_count]).result

        assert result["status"] == "failed"
        assert result["reason"] == "retry_ceiling_exceeded"
