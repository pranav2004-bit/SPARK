"""
test_dlq.py — Task 5.3's own testing checklist: a forced permanent LLM
failure lands in the DLQ with full context and the submission reflects
LLM_FAILED rather than hanging in LLM_PROCESSING (covered in
test_evaluate_essay.py's TestPermanentErrorImmediateDlq); the automatic
sweeper picks up an entry after the grace period without admin action;
and the circuit breaker actually stops retrying once the ceiling is hit.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt, EssaySubmission, EssayScore,
    EssayFailedJob,
)
from essays.tasks import sweep_dlq_entries, DLQ_GRACE_PERIOD_MINUTES, DLQ_RETRY_CEILING, _EVAL_MAX_INLINE_RETRIES, _record_dlq

from .conftest import INSTITUTION_A, ADMIN_USER_ID


def _make_submission():
    paper = EssayPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
    assignment = EssayAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
    )
    attempt = EssayAttempt.objects.create(
        assignment=assignment, student_id=uuid.uuid4(), set=eset,
        ends_at=timezone.now() + timedelta(hours=1), draft_response="An essay response.",
    )
    return EssaySubmission.objects.create(attempt=attempt)


@pytest.fixture
def submission(db):
    return _make_submission()


def _make_dlq_entry(submission, *, age_minutes=10, dlq_retry_count=0, resolved_at=None):
    entry = EssayFailedJob.objects.create(
        task_name="evaluate_essay", args=[str(submission.id)], error="LLM permanent error",
        attempts=3, dlq_retry_count=dlq_retry_count, resolved_at=resolved_at,
    )
    EssayFailedJob.objects.filter(pk=entry.pk).update(created_at=timezone.now() - timedelta(minutes=age_minutes))
    entry.refresh_from_db()
    return entry


@pytest.fixture(autouse=True)
def _no_real_advisory_lock_conflict():
    """The sqlite test DB has no pg_try_advisory_lock — tests run against
    sqlite (core/test_settings.py), so the sweeper's raw SQL would fail.
    Mock the lock as always-acquired/released so the sweeper's own
    business logic (the part these tests actually verify) can run."""
    with patch("essays.tasks.connection") as mock_connection:
        cursor = mock_connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = [True]
        yield


class TestGracePeriod:
    def test_entry_younger_than_grace_period_not_swept(self, submission):
        _make_dlq_entry(submission, age_minutes=1)
        with patch("essays.tasks.evaluate_essay.delay") as mock_delay:
            result = sweep_dlq_entries.apply().result
        assert result["retried"] == 0
        mock_delay.assert_not_called()

    def test_entry_past_grace_period_is_swept(self, submission):
        _make_dlq_entry(submission, age_minutes=DLQ_GRACE_PERIOD_MINUTES + 1)
        with patch("essays.tasks.evaluate_essay.delay") as mock_delay:
            result = sweep_dlq_entries.apply().result
        assert result["retried"] == 1
        # Task 17.2 — correlation_id is now this sweep run's own Celery
        # task id (a fresh UUID each run, not assertable as a literal), so
        # this checks the call shape rather than the exact kwarg value.
        mock_delay.assert_called_once()
        assert mock_delay.call_args.args == (str(submission.id),)
        assert mock_delay.call_args.kwargs.get("correlation_id")


class TestAutomaticRetryAndCircuitBreaker:
    def test_retry_increments_dlq_retry_count(self, submission):
        entry = _make_dlq_entry(submission, age_minutes=10, dlq_retry_count=1)
        with patch("essays.tasks.evaluate_essay.delay"):
            sweep_dlq_entries.apply()
        entry.refresh_from_db()
        assert entry.dlq_retry_count == 2
        assert entry.resolved_at is None

    def test_circuit_breaker_resolves_entry_at_ceiling_without_retrying(self, submission):
        entry = _make_dlq_entry(submission, age_minutes=10, dlq_retry_count=DLQ_RETRY_CEILING - 1)
        with patch("essays.tasks.evaluate_essay.delay") as mock_delay:
            result = sweep_dlq_entries.apply().result

        entry.refresh_from_db()
        # This pass's own retry pushes it to the ceiling, then the same
        # pass's circuit-breaker check resolves it.
        assert entry.dlq_retry_count == DLQ_RETRY_CEILING
        assert entry.resolved_at is not None
        assert result["circuit_broken"] == 1
        mock_delay.assert_called_once()

    def test_entry_already_at_ceiling_is_never_dispatched_again(self, submission):
        _make_dlq_entry(submission, age_minutes=10, dlq_retry_count=DLQ_RETRY_CEILING)
        with patch("essays.tasks.evaluate_essay.delay") as mock_delay:
            sweep_dlq_entries.apply()
        mock_delay.assert_not_called()


class TestSelfHealing:
    def test_entry_resolved_without_redispatch_if_already_scored(self, submission):
        EssayScore.objects.create(submission=submission, score=6, feedback={"overall": "fine"})
        entry = _make_dlq_entry(submission, age_minutes=10)
        with patch("essays.tasks.evaluate_essay.delay") as mock_delay:
            result = sweep_dlq_entries.apply().result

        entry.refresh_from_db()
        assert entry.resolved_at is not None
        assert entry.dlq_retry_count == 0  # never actually re-dispatched
        mock_delay.assert_not_called()
        assert result["self_healed"] == 1


class TestUnrelatedTaskNamesLeftForManualTriage:
    def test_unknown_task_name_not_touched(self, submission):
        entry = EssayFailedJob.objects.create(task_name="sweep_expired_assignments", args=[], error="x", attempts=3)
        EssayFailedJob.objects.filter(pk=entry.pk).update(created_at=timezone.now() - timedelta(minutes=10))
        sweep_dlq_entries.apply()
        entry.refresh_from_db()
        assert entry.resolved_at is None  # left alone, not silently resolved


class TestAlreadyResolvedEntriesIgnored:
    def test_resolved_entry_not_swept_again(self, submission):
        _make_dlq_entry(submission, age_minutes=10, resolved_at=timezone.now())
        with patch("essays.tasks.evaluate_essay.delay") as mock_delay:
            sweep_dlq_entries.apply()
        mock_delay.assert_not_called()


class TestRecordDlqDoesNotDuplicateRows:
    """Real bug found by this task's own live verification: a fresh
    evaluate_essay dispatch (e.g. from the automatic sweeper) that fails
    again for the same submission must update the existing unresolved
    EssayFailedJob row, not create a second, independent one that would
    then be its own separately-swept, separately-circuit-broken entry."""

    def test_second_failure_for_the_same_submission_updates_the_existing_row(self, submission):
        args = [str(submission.id)]
        _record_dlq("evaluate_essay", args, {}, RuntimeError("first failure"), attempts=0)
        _record_dlq("evaluate_essay", args, {}, RuntimeError("second failure"), attempts=1)

        assert EssayFailedJob.objects.filter(task_name="evaluate_essay", args=args).count() == 1
        entry = EssayFailedJob.objects.get(task_name="evaluate_essay", args=args)
        assert "second failure" in entry.error
        assert entry.attempts == 1

    def test_a_resolved_prior_entry_does_not_block_a_new_one(self, submission):
        args = [str(submission.id)]
        _record_dlq("evaluate_essay", args, {}, RuntimeError("old, already resolved"), attempts=0)
        EssayFailedJob.objects.filter(task_name="evaluate_essay", args=args).update(resolved_at=timezone.now())

        _record_dlq("evaluate_essay", args, {}, RuntimeError("new failure"), attempts=0)

        assert EssayFailedJob.objects.filter(task_name="evaluate_essay", args=args).count() == 2

    def test_different_submissions_get_independent_rows(self, submission, db):
        # A real second submission, not a bare uuid4() — Phase 6's own
        # EssaySubmissionEvent audit trail (Task 6.1) means _record_dlq now
        # also writes an event row FK'd to the real submission, which a
        # fabricated, backing-row-less id can't satisfy (caught by this
        # test itself once Task 6.1 added that write: a real, live
        # regression, not a hypothetical one — SQLite defers FK checking to
        # commit time, so the dangling reference only surfaced at test
        # teardown, not at the point of the actual bad write).
        other_submission = _make_submission()
        _record_dlq("evaluate_essay", [str(submission.id)], {}, RuntimeError("x"), attempts=0)
        _record_dlq("evaluate_essay", [str(other_submission.id)], {}, RuntimeError("y"), attempts=0)
        assert EssayFailedJob.objects.filter(task_name="evaluate_essay").count() == 2


class TestCostCeilingMatchesTheDocumentedNumber:
    def test_worst_case_call_count_matches_adr_003_decision_9(self):
        # ADR 003 Decision 9: "1 initial + 3 inline retries + up to 5
        # DLQ-sweep retries = 9 calls maximum". A direct assertion against
        # the actual constants, not just a comment claiming they agree —
        # catches the exact class of drift ADR 004 Section 3's own
        # self-audit found once already (a stale number nobody re-derived
        # after a related constant changed).
        worst_case_calls = 1 + _EVAL_MAX_INLINE_RETRIES + DLQ_RETRY_CEILING
        assert worst_case_calls == 9
