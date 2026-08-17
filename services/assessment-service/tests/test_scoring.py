import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, Question, BatchAssignment, AssessmentSession,
    ResultSummary, SESSION_STATUS_IN_PROGRESS, SESSION_STATUS_SUBMITTED,
    SESSION_STATUS_AUTO_SUBMITTED,
)
from assessments.scoring import finalize_sessions

from .conftest import INSTITUTION_A, ADMIN_USER_ID


@pytest.fixture
def paper_with_set(db):
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Scoring Test Paper",
        created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    Question.objects.create(set=qset, question_text="Q1", marks=3)
    Question.objects.create(set=qset, question_text="Q2", marks=2)
    return paper, qset


@pytest.fixture
def assignment(paper_with_set):
    paper, _ = paper_with_set
    return BatchAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID,
    )


def _make_session(assignment, qset, ends_at=None, status=SESSION_STATUS_IN_PROGRESS):
    return AssessmentSession.objects.create(
        assignment=assignment, student_id=uuid.uuid4(), set=qset,
        ends_at=ends_at or (timezone.now() + timedelta(hours=1)),
        status=status,
    )


class TestFinalizeSessions:
    def test_finalizes_in_progress_session_and_creates_result(self, assignment, paper_with_set):
        _, qset = paper_with_set
        session = _make_session(assignment, qset)

        count = finalize_sessions(
            AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_AUTO_SUBMITTED,
        )

        assert count == 1
        session.refresh_from_db()
        assert session.status == SESSION_STATUS_AUTO_SUBMITTED

        result = ResultSummary.objects.get(session=session)
        assert result.status == SESSION_STATUS_AUTO_SUBMITTED
        assert result.total_marks == 5  # 3 + 2
        assert result.score == 0  # stub until Task 5.2
        assert result.assignment_id == assignment.id
        assert result.student_id == session.student_id
        assert result.institution_id == INSTITUTION_A

    def test_second_call_on_already_finalized_session_is_a_noop(self, assignment, paper_with_set):
        _, qset = paper_with_set
        session = _make_session(assignment, qset)

        first = finalize_sessions(
            AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_AUTO_SUBMITTED,
        )
        second = finalize_sessions(
            AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_AUTO_SUBMITTED,
        )

        assert first == 1
        assert second == 0
        assert ResultSummary.objects.filter(session=session).count() == 1

    def test_manual_submit_wins_race_against_sweep(self, assignment, paper_with_set):
        # Simulates: a manual submit (Task 5.2, not yet built) claims the
        # session first, then the sweep's own finalize_sessions call for
        # the same session arrives a moment later — the sweep must be a
        # clean no-op, never overwriting the SUBMITTED result.
        _, qset = paper_with_set
        session = _make_session(assignment, qset)

        manual = finalize_sessions(
            AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_SUBMITTED,
        )
        sweep = finalize_sessions(
            AssessmentSession.objects.filter(pk=session.pk, ends_at__lte=timezone.now() + timedelta(days=1)),
            SESSION_STATUS_AUTO_SUBMITTED,
        )

        assert manual == 1
        assert sweep == 0
        session.refresh_from_db()
        assert session.status == SESSION_STATUS_SUBMITTED  # not overwritten
        result = ResultSummary.objects.get(session=session)
        assert result.status == SESSION_STATUS_SUBMITTED

    def test_no_candidates_returns_zero_no_crash(self, assignment, paper_with_set):
        count = finalize_sessions(
            AssessmentSession.objects.filter(pk=uuid.uuid4()), SESSION_STATUS_AUTO_SUBMITTED,
        )
        assert count == 0

    def test_already_terminal_session_not_touched(self, assignment, paper_with_set):
        _, qset = paper_with_set
        session = _make_session(assignment, qset, status=SESSION_STATUS_SUBMITTED)

        count = finalize_sessions(
            AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_AUTO_SUBMITTED,
        )
        assert count == 0
        assert ResultSummary.objects.filter(session=session).count() == 0

    def test_multiple_sessions_across_different_sets_scored_independently(self, assignment, paper_with_set):
        paper, qset_a = paper_with_set
        qset_b = QuestionSet.objects.create(paper=paper, label="Set B", order=2)
        Question.objects.create(set=qset_b, question_text="B1", marks=10)

        session_a = _make_session(assignment, qset_a)
        session_b = _make_session(assignment, qset_b)

        count = finalize_sessions(
            AssessmentSession.objects.filter(assignment=assignment), SESSION_STATUS_AUTO_SUBMITTED,
        )
        assert count == 2

        result_a = ResultSummary.objects.get(session=session_a)
        result_b = ResultSummary.objects.get(session=session_b)
        assert result_a.total_marks == 5
        assert result_b.total_marks == 10

    def test_invalid_target_status_raises(self, assignment, paper_with_set):
        _, qset = paper_with_set
        session = _make_session(assignment, qset)
        with pytest.raises(ValueError):
            finalize_sessions(AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_IN_PROGRESS)

    def test_load_many_sessions_finalized_in_one_call(self, assignment, paper_with_set):
        _, qset = paper_with_set
        sessions = [_make_session(assignment, qset) for _ in range(200)]

        count = finalize_sessions(
            AssessmentSession.objects.filter(assignment=assignment), SESSION_STATUS_AUTO_SUBMITTED,
        )
        assert count == 200
        assert ResultSummary.objects.filter(assignment=assignment).count() == 200
