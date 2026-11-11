"""
test_student_results.py — Phase 14's own testing checklist (Task 14.1):
JWT-scoped to the student's own results only (never another student's —
ET3), correctness against a known fixture, no admin-only fields exposed.

Mirrors assessment-service's own test_student_results.py (verified,
already read) — same fixture shape (two different assignments, since
ADR 002 Decision 3 means no retake/re-attempt so multiple past results
require multiple assignments, not multiple attempts on one), same
cross-student isolation proof. Adapted: essay-service has no
show_result_to_student admin toggle at all (confirmed by reading the
whole EssayAssignment model — no such field exists), so there's no
"score hidden" case to test; in its place, this file covers the states
that ARE real here and aren't in the assessment-service precedent: an
in-progress (non-terminal) attempt must not appear at all, and a
terminal attempt whose evaluation hasn't finished yet must still appear
with score/feedback left null (matching assessment-service's own "never
hide that you completed it" precedent, applied to this service's own
different pipeline shape).
"""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt, EssaySubmission, EssayScore,
    ASSIGNMENT_STATUS_LIVE,
    ATTEMPT_STATUS_IN_PROGRESS, ATTEMPT_STATUS_SUBMITTED, ATTEMPT_STATUS_AUTO_SUBMITTED,
    SUBMISSION_STATUS_LLM_COMPLETE, SUBMISSION_STATUS_LLM_PROCESSING, SUBMISSION_STATUS_LLM_FAILED,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


@pytest.fixture
def results_setup(db):
    paper = EssayPaper.objects.create(institution_id=INSTITUTION_A, title="Results Test Paper", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    question = EssayQuestion.objects.create(
        set=eset, question_text="Discuss the causes of X.", llm_rubric_prompt="Score on clarity and evidence.",
        word_limit=500, time_limit_minutes=30, max_score=10,
    )

    def _make_assignment():
        return EssayAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            status=ASSIGNMENT_STATUS_LIVE, created_by=ADMIN_USER_ID,
        )

    assignment_1 = _make_assignment()
    assignment_2 = _make_assignment()
    assignment_3 = _make_assignment()  # will hold the in-progress (non-terminal) attempt
    assignment_4 = _make_assignment()  # will hold the still-processing (terminal, unscored) attempt

    other_student_id = uuid.uuid4()

    def _make_attempt(assignment, student_id, status, started_ago_days=0):
        attempt = EssayAttempt.objects.create(
            assignment=assignment, student_id=student_id, set=eset,
            ends_at=timezone.now() + timedelta(hours=1), draft_response="An essay response.",
        )
        EssayAttempt.objects.filter(pk=attempt.pk).update(
            status=status, started_at=timezone.now() - timedelta(days=started_ago_days),
        )
        attempt.refresh_from_db()
        return attempt

    def _score(attempt, score, *, feedback=None, is_no_submission=False, submitted_ago_days=0):
        submission = EssaySubmission.objects.create(attempt=attempt)
        EssaySubmission.objects.filter(pk=submission.pk).update(
            status=SUBMISSION_STATUS_LLM_COMPLETE, created_at=timezone.now() - timedelta(days=submitted_ago_days),
        )
        submission.refresh_from_db()
        EssayScore.objects.create(
            submission=submission, score=score,
            feedback=feedback or {"overall": "x", "breakdown": {}}, is_no_submission=is_no_submission,
        )
        return submission

    # Deliberately crossed: attempt_older STARTED first (3 days ago) but
    # COMPLETED most recently (1 day ago) — a long-running attempt.
    # attempt_newer STARTED second (2 days ago, after attempt_older) but
    # COMPLETED earlier (2 days ago) — a quick one. Proves ordering is by
    # completion time, not start time (see the view's own comment on this).
    attempt_older = _make_attempt(assignment_2, STUDENT_USER_ID, ATTEMPT_STATUS_AUTO_SUBMITTED, started_ago_days=3)
    submission_older = _score(
        attempt_older, 3, submitted_ago_days=1,
        feedback={"overall": "Needs work.", "breakdown": {"clarity": {"score": 1, "maxScore": 5, "feedback": "unclear"}}},
    )

    attempt_newer = _make_attempt(assignment_1, STUDENT_USER_ID, ATTEMPT_STATUS_SUBMITTED, started_ago_days=2)
    submission_newer = _score(
        attempt_newer, 8, submitted_ago_days=2,
        feedback={"overall": "Strong essay.", "breakdown": {"clarity": {"score": 4, "maxScore": 5, "feedback": "clear"}}},
    )

    # A different student's own attempt on the SAME assignment_1 — must
    # never leak into STUDENT_USER_ID's own results.
    other_attempt = _make_attempt(assignment_1, other_student_id, ATTEMPT_STATUS_SUBMITTED, started_ago_days=1)
    _score(other_attempt, 10)

    # Non-terminal — must not appear in "past results" at all.
    in_progress_attempt = _make_attempt(assignment_3, STUDENT_USER_ID, ATTEMPT_STATUS_IN_PROGRESS)

    # Terminal, but evaluation hasn't finished — must appear with score/feedback null.
    processing_attempt = _make_attempt(assignment_4, STUDENT_USER_ID, ATTEMPT_STATUS_SUBMITTED, started_ago_days=0)
    processing_submission = EssaySubmission.objects.create(attempt=processing_attempt)
    EssaySubmission.objects.filter(pk=processing_submission.pk).update(status=SUBMISSION_STATUS_LLM_PROCESSING)

    return {
        "paper": paper, "question": question,
        "assignment_1": assignment_1, "assignment_2": assignment_2,
        "assignment_3": assignment_3, "assignment_4": assignment_4,
        "attempt_older": attempt_older, "attempt_newer": attempt_newer,
        "other_attempt": other_attempt, "in_progress_attempt": in_progress_attempt,
        "processing_attempt": processing_attempt,
    }


class TestStudentEssayResults:
    def test_returns_own_results_only(self, student_client, results_setup):
        resp = student_client.get("/api/essay/student/results/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # assignment_1, assignment_2, assignment_4 (processing) — NOT assignment_3 (in-progress)
        assert len(data) == 3
        assignment_ids = {r["assignment_id"] for r in data}
        assert assignment_ids == {
            str(results_setup["assignment_1"].id),
            str(results_setup["assignment_2"].id),
            str(results_setup["assignment_4"].id),
        }
        scores = sorted(r["score"] for r in data if r["score"] is not None)
        assert scores == [3, 8]  # the other student's 10 never appears

    def test_ordered_newest_first(self, student_client, results_setup):
        resp = student_client.get("/api/essay/student/results/")
        data = resp.json()["data"]
        # By completion time (submitted_at), not start time:
        # processing_attempt (submission just created, ~now)
        # > attempt_older/assignment_2 (completed 1 day ago, despite STARTING 3 days ago — first)
        # > attempt_newer/assignment_1 (completed 2 days ago, despite STARTING 2 days ago — after attempt_older started)
        assert data[0]["assignment_id"] == str(results_setup["assignment_4"].id)
        assert data[1]["assignment_id"] == str(results_setup["assignment_2"].id)
        assert data[2]["assignment_id"] == str(results_setup["assignment_1"].id)

    def test_ordered_by_completion_not_start_time(self, student_client, results_setup):
        # The precise regression this proves: attempt_older started BEFORE
        # attempt_newer (3 days ago vs 2 days ago) but finished AFTER it
        # (completed 1 day ago vs 2 days ago) — a long-running attempt.
        # Ordering by started_at (the pre-fix behavior) would have put
        # attempt_newer (assignment_1) first; ordering by completion time
        # (the fix, matching assessment-service's own -ended_at precedent)
        # correctly puts attempt_older (assignment_2) first instead.
        resp = student_client.get("/api/essay/student/results/")
        data = resp.json()["data"]
        scored = [r for r in data if r["score"] is not None]
        assert scored[0]["assignment_id"] == str(results_setup["assignment_2"].id)
        assert scored[1]["assignment_id"] == str(results_setup["assignment_1"].id)

    def test_score_and_feedback_returned_correctly(self, student_client, results_setup):
        resp = student_client.get("/api/essay/student/results/")
        data = resp.json()["data"]
        by_assignment = {r["assignment_id"]: r for r in data}

        row = by_assignment[str(results_setup["assignment_1"].id)]
        assert row["score"] == 8
        assert row["max_score"] == 10
        assert row["feedback"]["overall"] == "Strong essay."
        assert row["feedback"]["breakdown"]["clarity"]["score"] == 4
        assert row["paper_title"] == "Results Test Paper"
        assert row["set_label"] == "Set A"
        assert row["attempt_status"] == ATTEMPT_STATUS_SUBMITTED
        assert row["exam_status"] == "completed"
        assert row["is_no_submission"] is False

    def test_still_processing_attempt_shows_row_with_null_score(self, student_client, results_setup):
        resp = student_client.get("/api/essay/student/results/")
        data = resp.json()["data"]
        by_assignment = {r["assignment_id"]: r for r in data}

        row = by_assignment[str(results_setup["assignment_4"].id)]
        assert row["score"] is None
        assert row["feedback"] is None
        assert row["exam_status"] == "processing"

    def test_permanently_failed_evaluation_shows_distinct_exam_status(self, student_client, results_setup):
        # A genuinely different state from "processing" — this one is
        # stuck in the admin-only DLQ until someone manually retriggers
        # it, not something that resolves on its own. The frontend's own
        # copy depends on telling these two apart correctly (found during
        # Phase 14's third audit round: it originally didn't).
        attempt = EssayAttempt.objects.create(
            assignment=EssayAssignment.objects.create(
                paper=results_setup["paper"], batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
                global_expire_time=timezone.now() + timedelta(hours=3),
                status=ASSIGNMENT_STATUS_LIVE, created_by=ADMIN_USER_ID,
            ),
            student_id=STUDENT_USER_ID, set=results_setup["question"].set,
            ends_at=timezone.now() + timedelta(hours=1),
        )
        EssayAttempt.objects.filter(pk=attempt.pk).update(status=ATTEMPT_STATUS_SUBMITTED)
        submission = EssaySubmission.objects.create(attempt=attempt)
        EssaySubmission.objects.filter(pk=submission.pk).update(status=SUBMISSION_STATUS_LLM_FAILED)

        resp = student_client.get("/api/essay/student/results/")
        data = resp.json()["data"]
        row = next(r for r in data if r["assignment_id"] == str(attempt.assignment_id))
        assert row["score"] is None
        assert row["exam_status"] == "failed"

    def test_in_progress_attempt_not_included(self, student_client, results_setup):
        resp = student_client.get("/api/essay/student/results/")
        data = resp.json()["data"]
        assignment_ids = {r["assignment_id"] for r in data}
        assert str(results_setup["assignment_3"].id) not in assignment_ids

    def test_no_admin_only_fields_exposed(self, student_client, results_setup):
        resp = student_client.get("/api/essay/student/results/")
        data = resp.json()["data"]
        for row in data:
            assert "malpractice_flag" not in row
            assert "malpractice_reasons" not in row
            assert "evaluated_by" not in row
            assert "institution_id" not in row
            assert "student_id" not in row

    def test_no_submission_flag_included(self, student_client, results_setup):
        # A student who submitted nothing still gets a real, findable row —
        # not silently indistinguishable from a genuinely low written score.
        attempt = EssayAttempt.objects.create(
            assignment=EssayAssignment.objects.create(
                paper=results_setup["paper"], batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
                global_expire_time=timezone.now() + timedelta(hours=3),
                status=ASSIGNMENT_STATUS_LIVE, created_by=ADMIN_USER_ID,
            ),
            student_id=STUDENT_USER_ID, set=results_setup["question"].set,
            ends_at=timezone.now() + timedelta(hours=1),
        )
        EssayAttempt.objects.filter(pk=attempt.pk).update(status=ATTEMPT_STATUS_AUTO_SUBMITTED)
        submission = EssaySubmission.objects.create(attempt=attempt)
        EssaySubmission.objects.filter(pk=submission.pk).update(status=SUBMISSION_STATUS_LLM_COMPLETE)
        submission.refresh_from_db()
        EssayScore.objects.create(submission=submission, score=0, feedback={}, is_no_submission=True)

        resp = student_client.get("/api/essay/student/results/")
        data = resp.json()["data"]
        row = next(r for r in data if r["assignment_id"] == str(attempt.assignment_id))
        assert row["score"] == 0
        assert row["is_no_submission"] is True

    def test_empty_when_no_results(self, student_client):
        resp = student_client.get("/api/essay/student/results/")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_admin_forbidden(self, admin_client, results_setup):
        resp = admin_client.get("/api/essay/student/results/")
        assert resp.status_code == 403

    def test_anonymous_forbidden(self, anon_client, results_setup):
        resp = anon_client.get("/api/essay/student/results/")
        assert resp.status_code in (401, 403)
