import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, BatchAssignment, AssessmentSession, ResultSummary,
    ASSIGNMENT_STATUS_LIVE, SESSION_STATUS_SUBMITTED, SESSION_STATUS_AUTO_SUBMITTED,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


@pytest.fixture
def results_setup(db):
    """STUDENT_USER_ID (the `student_client` fixture's own JWT identity) has
    two past results on two DIFFERENT assignments (a student can only ever
    have one session per assignment — Decision #3, no retake/re-attempt in
    V1 — so multiple past results require multiple assignments, not
    multiple sessions on one). A different student has a result on the
    first assignment too, to prove cross-student isolation. Hand-computable:
    result_1 (assignment_1): score 8/10 = 80%, cutoff 40 -> passed
    result_2 (assignment_2): score 3/10 = 30%, cutoff 40 -> not passed
    other_student's result must never appear for STUDENT_USER_ID's requests.
    """
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Results Test Paper",
        created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)

    def _make_assignment():
        return BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
            pass_cutoff_percentage=40,
        )

    assignment_1 = _make_assignment()
    assignment_2 = _make_assignment()

    other_student_id = uuid.uuid4()

    def _make(assignment, student_id, status, score, total_marks, ended_at, flagged=False):
        session = AssessmentSession.objects.create(
            assignment=assignment, student_id=student_id, set=qset,
            ends_at=timezone.now() + timedelta(hours=1), status=status,
            started_at=ended_at - timedelta(minutes=10),
        )
        return ResultSummary.objects.create(
            session=session, assignment=assignment, student_id=student_id, institution_id=INSTITUTION_A,
            started_at=session.started_at, ended_at=ended_at, duration_seconds=600,
            score=score, total_marks=total_marks, status=status,
            malpractice_flag=flagged, malpractice_reasons=["tab_switch"] if flagged else [],
        )

    now = timezone.now()
    result_older = _make(assignment_2, STUDENT_USER_ID, SESSION_STATUS_AUTO_SUBMITTED, 3, 10, now - timedelta(days=2))
    result_newer = _make(assignment_1, STUDENT_USER_ID, SESSION_STATUS_SUBMITTED, 8, 10, now - timedelta(days=1), flagged=True)
    other_result = _make(assignment_1, other_student_id, SESSION_STATUS_SUBMITTED, 10, 10, now)

    return {
        "assignment": assignment_1, "assignment_1": assignment_1, "assignment_2": assignment_2, "paper": paper,
        "result_older": result_older, "result_newer": result_newer, "other_result": other_result,
    }


class TestStudentResults:
    def test_returns_own_results_only(self, student_client, results_setup):
        resp = student_client.get("/api/assessments/student/results/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        assignment_ids = {r["assignment_id"] for r in data}
        assert assignment_ids == {str(results_setup["assignment_1"].id), str(results_setup["assignment_2"].id)}
        # the other student's result must never leak in, even though it's on
        # the same assignment_1 the requesting student also has a result on
        scores = sorted(r["score"] for r in data)
        assert scores == [3, 8]

    def test_ordered_newest_first(self, student_client, results_setup):
        resp = student_client.get("/api/assessments/student/results/")
        data = resp.json()["data"]
        assert data[0]["score"] == 8  # result_newer
        assert data[1]["score"] == 3  # result_older

    def test_percentage_and_passed_computed_correctly(self, student_client, results_setup):
        resp = student_client.get("/api/assessments/student/results/")
        data = resp.json()["data"]
        by_score = {r["score"]: r for r in data}

        passed_row = by_score[8]
        assert passed_row["percentage"] == 80.0
        assert passed_row["pass_cutoff_percentage"] == 40
        assert passed_row["passed"] is True
        assert passed_row["status"] == SESSION_STATUS_SUBMITTED
        assert passed_row["paper_title"] == "Results Test Paper"

        failed_row = by_score[3]
        assert failed_row["percentage"] == 30.0
        assert failed_row["passed"] is False
        assert failed_row["status"] == SESSION_STATUS_AUTO_SUBMITTED

    def test_score_hidden_when_show_result_to_student_is_false(self, student_client, results_setup):
        BatchAssignment.objects.filter(pk=results_setup["assignment_1"].pk).update(show_result_to_student=False)
        resp = student_client.get("/api/assessments/student/results/")
        data = resp.json()["data"]
        by_assignment = {r["assignment_id"]: r for r in data}

        hidden_row = by_assignment[str(results_setup["assignment_1"].id)]
        assert hidden_row["results_visible"] is False
        assert hidden_row["score"] is None
        assert hidden_row["total_marks"] is None
        assert hidden_row["percentage"] is None
        assert hidden_row["passed"] is None

        # assignment_2 wasn't touched — still fully visible.
        visible_row = by_assignment[str(results_setup["assignment_2"].id)]
        assert visible_row["results_visible"] is True
        assert visible_row["score"] == 3

    def test_no_admin_only_fields_exposed(self, student_client, results_setup):
        resp = student_client.get("/api/assessments/student/results/")
        data = resp.json()["data"]
        for row in data:
            assert "malpractice_flag" not in row
            assert "malpractice_reasons" not in row
            assert "institution_id" not in row

    def test_query_param_cannot_impersonate_another_student(self, student_client, results_setup):
        # Attempting to pass another student's id via any query param must be
        # silently ignored — the view only ever reads request.user.id (AT3).
        other_id = results_setup["other_result"].student_id
        resp = student_client.get(f"/api/assessments/student/results/?student_id={other_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        assert all(r["score"] != 10 for r in data)  # the other student's 10/10 never appears

    def test_empty_when_no_results(self, student_client):
        resp = student_client.get("/api/assessments/student/results/")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_admin_forbidden(self, admin_client, results_setup):
        resp = admin_client.get("/api/assessments/student/results/")
        assert resp.status_code == 403

    def test_anonymous_forbidden(self, anon_client, results_setup):
        resp = anon_client.get("/api/assessments/student/results/")
        assert resp.status_code in (401, 403)
