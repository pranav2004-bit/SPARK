import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt, EssayMalpracticeEvent,
    EssaySubmission, ATTEMPT_STATUS_IN_PROGRESS, ATTEMPT_STATUS_SUBMITTED, ATTEMPT_STATUS_AUTO_SUBMITTED,
    MALPRACTICE_EVENT_TAB_SWITCH, MALPRACTICE_EVENT_FULLSCREEN_EXIT, MALPRACTICE_EVENT_PASTE_ATTEMPT,
)
from essays.scoring import finalize_attempts

from .conftest import INSTITUTION_A, ADMIN_USER_ID


@pytest.fixture
def paper_with_set(db):
    paper = EssayPaper.objects.create(
        institution_id=INSTITUTION_A, title="Scoring Test Paper", created_by=ADMIN_USER_ID,
    )
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(
        set=eset, question_text="Q1", llm_rubric_prompt="R1", word_limit=500, time_limit_minutes=30,
    )
    return paper, eset


@pytest.fixture
def assignment(paper_with_set):
    paper, _ = paper_with_set
    return EssayAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
    )


def _make_attempt(assignment, eset, ends_at=None, status=ATTEMPT_STATUS_IN_PROGRESS, started_ago=timedelta(minutes=10)):
    # Backdated by default (Task 15.2's own cadence signal, added this
    # round): a create-then-immediately-finalize test attempt would
    # otherwise spuriously trip CADENCE_THRESHOLD_SECONDS (duration < 3s)
    # on every test in this file that doesn't care about cadence —
    # test_cadence_under_threshold_flags below is the one place that
    # deliberately passes started_ago=timedelta(seconds=0) instead.
    attempt = EssayAttempt.objects.create(
        assignment=assignment, student_id=uuid.uuid4(), set=eset,
        ends_at=ends_at or (timezone.now() + timedelta(hours=1)),
        status=status,
    )
    EssayAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - started_ago)
    attempt.refresh_from_db()
    return attempt


class TestFinalizeAttempts:
    def test_finalizes_in_progress_attempt(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset)

        count = finalize_attempts(
            EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_AUTO_SUBMITTED,
        )

        assert count == 1
        attempt.refresh_from_db()
        assert attempt.status == ATTEMPT_STATUS_AUTO_SUBMITTED

    def test_second_call_on_already_finalized_attempt_is_a_noop(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset)

        first = finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_AUTO_SUBMITTED)
        second = finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_AUTO_SUBMITTED)

        assert first == 1
        assert second == 0

    def test_manual_submit_wins_race_against_sweep(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset)

        manual = finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_SUBMITTED)
        sweep = finalize_attempts(
            EssayAttempt.objects.filter(pk=attempt.pk, ends_at__lte=timezone.now() + timedelta(days=1)),
            ATTEMPT_STATUS_AUTO_SUBMITTED,
        )

        assert manual == 1
        assert sweep == 0
        attempt.refresh_from_db()
        assert attempt.status == ATTEMPT_STATUS_SUBMITTED  # not overwritten

    def test_no_candidates_returns_zero_no_crash(self, assignment, paper_with_set):
        count = finalize_attempts(
            EssayAttempt.objects.filter(pk=uuid.uuid4()), ATTEMPT_STATUS_AUTO_SUBMITTED,
        )
        assert count == 0

    def test_already_terminal_attempt_not_touched(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset, status=ATTEMPT_STATUS_SUBMITTED)

        count = finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_AUTO_SUBMITTED)
        assert count == 0

    def test_invalid_target_status_raises(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset)
        with pytest.raises(ValueError):
            finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_IN_PROGRESS)


class TestFinalizeAttemptsMalpractice:
    def test_no_events_no_flag(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset)
        finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_AUTO_SUBMITTED)
        attempt.refresh_from_db()
        assert attempt.malpractice_flag is False
        assert attempt.malpractice_reasons == []

    def test_tab_switch_over_threshold_flags(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset)
        for _ in range(6):  # threshold is >5
            EssayMalpracticeEvent.objects.create(
                attempt=attempt, event_type=MALPRACTICE_EVENT_TAB_SWITCH, occurred_at=timezone.now(),
            )
        finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_AUTO_SUBMITTED)
        attempt.refresh_from_db()
        assert attempt.malpractice_flag is True
        assert "tab_switch" in attempt.malpractice_reasons

    def test_tab_switch_at_threshold_does_not_flag(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset)
        for _ in range(5):  # exactly at threshold, not over
            EssayMalpracticeEvent.objects.create(
                attempt=attempt, event_type=MALPRACTICE_EVENT_TAB_SWITCH, occurred_at=timezone.now(),
            )
        finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_AUTO_SUBMITTED)
        attempt.refresh_from_db()
        assert attempt.malpractice_flag is False

    def test_fullscreen_exit_over_threshold_flags(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset)
        for _ in range(4):  # threshold is >3
            EssayMalpracticeEvent.objects.create(
                attempt=attempt, event_type=MALPRACTICE_EVENT_FULLSCREEN_EXIT, occurred_at=timezone.now(),
            )
        finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_AUTO_SUBMITTED)
        attempt.refresh_from_db()
        assert attempt.malpractice_flag is True
        assert "fullscreen_exit" in attempt.malpractice_reasons

    def test_any_paste_attempt_flags(self, assignment, paper_with_set):
        # Deliberately a lower bar than tab_switch/fullscreen_exit — see
        # scoring.py's PASTE_ATTEMPT_THRESHOLD comment: any paste into an
        # essay response is a strong signal, not just a tolerance breach.
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset)
        EssayMalpracticeEvent.objects.create(
            attempt=attempt, event_type=MALPRACTICE_EVENT_PASTE_ATTEMPT, occurred_at=timezone.now(),
        )
        finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_AUTO_SUBMITTED)
        attempt.refresh_from_db()
        assert attempt.malpractice_flag is True
        assert attempt.malpractice_reasons == ["paste_attempt"]

    def test_multiple_reasons_all_recorded(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset)
        for _ in range(6):
            EssayMalpracticeEvent.objects.create(
                attempt=attempt, event_type=MALPRACTICE_EVENT_TAB_SWITCH, occurred_at=timezone.now(),
            )
        EssayMalpracticeEvent.objects.create(
            attempt=attempt, event_type=MALPRACTICE_EVENT_PASTE_ATTEMPT, occurred_at=timezone.now(),
        )
        finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_AUTO_SUBMITTED)
        attempt.refresh_from_db()
        assert set(attempt.malpractice_reasons) == {"tab_switch", "paste_attempt"}

    def test_cadence_under_threshold_flags(self, assignment, paper_with_set):
        # Task 15.2's own bot-defense signal — reused from assessment-
        # service's Decision #5 (CADENCE_THRESHOLD_SECONDS = 3) unchanged.
        # An attempt started and finalized within under 3 real seconds
        # (a scripted/automated submission bypassing the exam UI, AT9 —
        # no genuine human writes anything meaningful that fast) is flagged.
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset, started_ago=timedelta(seconds=1))
        finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_SUBMITTED)
        attempt.refresh_from_db()
        assert attempt.malpractice_flag is True
        assert "cadence" in attempt.malpractice_reasons

    def test_cadence_at_threshold_does_not_flag(self, assignment, paper_with_set):
        # Exactly at the 3s threshold — not flagged, matching the other
        # thresholds' own strict-greater-than (not >=) boundary convention.
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset, started_ago=timedelta(seconds=3))
        finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_SUBMITTED)
        attempt.refresh_from_db()
        assert attempt.malpractice_flag is False
        assert "cadence" not in attempt.malpractice_reasons

    def test_malpractice_not_recomputed_on_second_finalize_call(self, assignment, paper_with_set):
        # Once terminal, a second finalize_attempts() call is a no-op for
        # this attempt (test_second_call_on_already_finalized_attempt_is_a_noop
        # already proves the count) — confirm malpractice fields aren't
        # touched either, since candidates are filtered to IN_PROGRESS only.
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset)
        finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_AUTO_SUBMITTED)
        attempt.refresh_from_db()
        assert attempt.malpractice_flag is False

        # Add events AFTER finalize — a second call must not retroactively flag it.
        for _ in range(10):
            EssayMalpracticeEvent.objects.create(
                attempt=attempt, event_type=MALPRACTICE_EVENT_TAB_SWITCH, occurred_at=timezone.now(),
            )
        finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_AUTO_SUBMITTED)
        attempt.refresh_from_db()
        assert attempt.malpractice_flag is False


class TestFinalizeAttemptsSubmissionCreation:
    """Task 5.1's own extension: finalize_attempts() creates the
    EssaySubmission row and dispatches the evaluation pipeline — the "one
    unified entry point" decision (no separate create_submission path)."""

    def test_creates_submission_and_dispatches_evaluation(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset)

        with patch("essays.tasks.evaluate_essay") as mock_evaluate, \
             patch("essays.tasks.check_text_similarity") as mock_similarity:
            finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_SUBMITTED)

        submission = EssaySubmission.objects.get(attempt=attempt)
        # Task 17.2 — correlation_id is get_request_id(), None in this
        # plain-function test context (no HTTP request or Celery task ever
        # bound one), so it's an explicit part of the expected call shape.
        mock_evaluate.delay.assert_called_once_with(str(submission.id), correlation_id=None)
        mock_similarity.delay.assert_called_once_with(str(attempt.id))

    def test_no_submission_created_when_nothing_finalized(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset, status=ATTEMPT_STATUS_SUBMITTED)
        # Already terminal AND already has a submission — the ordinary
        # "nothing to do" case, not the orphan-repair case below.
        EssaySubmission.objects.create(attempt=attempt)

        with patch("essays.tasks.evaluate_essay") as mock_evaluate:
            finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_SUBMITTED)

        mock_evaluate.delay.assert_not_called()
        assert EssaySubmission.objects.filter(attempt=attempt).count() == 1

    def test_two_racing_dispatch_calls_for_the_same_attempt_only_evaluate_once(self, assignment, paper_with_set):
        """Real bug found by this phase's own 4th final-audit round,
        reproduced deterministically here (no threads needed): two calls
        to the internal dispatch helper for the SAME attempt_id — exactly
        what happens when two concurrent finalize/repair passes both see
        the attempt as orphaned before either one's insert commits — used
        to dispatch evaluate_essay/check_text_similarity TWICE, a real
        duplicate OpenAI call, even though the OneToOneField constraint
        already guaranteed only one EssaySubmission row would ever exist.
        Fixed via get_or_create()'s own atomicity; this pins it."""
        from essays.scoring import _create_and_dispatch_submissions

        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset, status=ATTEMPT_STATUS_SUBMITTED)

        with patch("essays.tasks.evaluate_essay") as mock_evaluate, \
             patch("essays.tasks.check_text_similarity") as mock_similarity:
            _create_and_dispatch_submissions([attempt.id])
            _create_and_dispatch_submissions([attempt.id])

        assert EssaySubmission.objects.filter(attempt=attempt).count() == 1
        mock_evaluate.delay.assert_called_once()
        mock_similarity.delay.assert_called_once()


class TestOrphanedSubmissionRepair:
    """Real bug found by this task's own genuine OS-thread concurrency
    test (test_concurrency.py), reproduced here deterministically: an
    attempt that is already terminal but has no EssaySubmission — e.g. a
    prior finalize_attempts() call flipped its status, then failed before
    creating the submission — must be discovered and repaired the next
    time finalize_attempts() runs over it, not silently ignored forever."""

    def test_orphaned_terminal_attempt_gets_a_submission_on_next_call(self, assignment, paper_with_set):
        _, eset = paper_with_set
        # Simulates the exact failure window: status already flipped,
        # submission never created (as if a prior call died in between).
        attempt = _make_attempt(assignment, eset, status=ATTEMPT_STATUS_SUBMITTED)
        assert not EssaySubmission.objects.filter(attempt=attempt).exists()

        with patch("essays.tasks.evaluate_essay") as mock_evaluate:
            count = finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_SUBMITTED)

        assert count == 0  # this call didn't finalize it (already terminal) — but it DID repair it
        submission = EssaySubmission.objects.get(attempt=attempt)
        mock_evaluate.delay.assert_called_once_with(str(submission.id), correlation_id=None)

    def test_repair_is_scoped_to_the_callers_own_queryset(self, assignment, paper_with_set):
        # An orphaned attempt OUTSIDE the caller's queryset scope must not
        # be touched — repair is not a global sweep, it only ever looks at
        # what the caller already asked about.
        _, eset = paper_with_set
        in_scope = _make_attempt(assignment, eset, status=ATTEMPT_STATUS_SUBMITTED)
        out_of_scope = _make_attempt(assignment, eset, status=ATTEMPT_STATUS_SUBMITTED)

        with patch("essays.tasks.evaluate_essay"):
            finalize_attempts(EssayAttempt.objects.filter(pk=in_scope.pk), ATTEMPT_STATUS_SUBMITTED)

        assert EssaySubmission.objects.filter(attempt=in_scope).exists()
        assert not EssaySubmission.objects.filter(attempt=out_of_scope).exists()

    def test_repair_does_not_touch_a_still_in_progress_attempt(self, assignment, paper_with_set):
        _, eset = paper_with_set
        attempt = _make_attempt(assignment, eset, status=ATTEMPT_STATUS_IN_PROGRESS)

        with patch("essays.tasks.evaluate_essay") as mock_evaluate:
            finalize_attempts(EssayAttempt.objects.filter(pk=uuid.uuid4()), ATTEMPT_STATUS_SUBMITTED)  # unrelated no-op call

        mock_evaluate.delay.assert_not_called()
        assert not EssaySubmission.objects.filter(attempt=attempt).exists()
