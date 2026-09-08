import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, Question, BatchAssignment, StudentSetAllocation,
    AssessmentSession, ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_SCHEDULED,
    ASSIGNMENT_STATUS_CLOSED, SESSION_STATUS_IN_PROGRESS,
    SESSION_STATUS_SUBMITTED, SESSION_STATUS_AUTO_SUBMITTED,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


@pytest.fixture
def paper_with_set(db):
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Student Flow Test Paper",
        created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    return paper, qset


def _assignment(paper, **overrides):
    defaults = dict(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID,
        status=ASSIGNMENT_STATUS_LIVE,
    )
    defaults.update(overrides)
    return BatchAssignment.objects.create(**defaults)


def _allocate(assignment, qset, student_id=STUDENT_USER_ID):
    return StudentSetAllocation.objects.create(assignment=assignment, student_id=student_id, set=qset)


# ── List ─────────────────────────────────────────────────────────────────────

class TestStudentAssignmentList:
    def test_allocated_assignment_appears_automatically(self, student_client, paper_with_set):
        paper, qset = paper_with_set
        assignment = _assignment(paper)
        _allocate(assignment, qset)

        resp = student_client.get("/api/assessments/student/assignments/")

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert len(body) == 1
        assert body[0]["assignment_id"] == str(assignment.id)
        assert body[0]["status"] == ASSIGNMENT_STATUS_LIVE
        assert body[0]["paper_title"] == "Student Flow Test Paper"
        assert body[0]["session_status"] is None

    def test_unallocated_assignment_does_not_appear(self, student_client, paper_with_set):
        paper, qset = paper_with_set
        _assignment(paper)  # not allocated to this student

        resp = student_client.get("/api/assessments/student/assignments/")
        assert resp.json()["data"] == []

    def test_includes_session_status_once_started(self, student_client, paper_with_set):
        paper, qset = paper_with_set
        assignment = _assignment(paper)
        _allocate(assignment, qset)
        AssessmentSession.objects.create(
            assignment=assignment, student_id=STUDENT_USER_ID, set=qset,
            ends_at=timezone.now() + timedelta(minutes=30),
        )

        resp = student_client.get("/api/assessments/student/assignments/")
        assert resp.json()["data"][0]["session_status"] == SESSION_STATUS_IN_PROGRESS

    def test_only_own_allocations_not_another_students(self, student_client, paper_with_set):
        paper, qset = paper_with_set
        assignment = _assignment(paper)
        _allocate(assignment, qset, student_id=uuid.uuid4())  # a different student

        resp = student_client.get("/api/assessments/student/assignments/")
        assert resp.json()["data"] == []

    def test_admin_forbidden(self, admin_client):
        resp = admin_client.get("/api/assessments/student/assignments/")
        assert resp.status_code == 403

    def test_includes_total_marks_and_question_count_for_the_students_own_set(self, student_client, paper_with_set):
        # Added 2026-08-27 for the pre-exam briefing screen. Deliberately
        # from THIS student's own allocated set, not just "any set of the
        # paper" — proven distinct here by giving a second set of the same
        # paper a different question count/marks total; only the allocated
        # set's numbers may leak into the response.
        paper, qset = paper_with_set
        Question.objects.create(set=qset, question_text="Q1", marks=2)
        Question.objects.create(set=qset, question_text="Q2", marks=3)
        other_set = QuestionSet.objects.create(paper=paper, label="Set B", order=2)
        Question.objects.create(set=other_set, question_text="Q1", marks=10)

        assignment = _assignment(paper)
        _allocate(assignment, qset)

        resp = student_client.get("/api/assessments/student/assignments/")

        row = resp.json()["data"][0]
        assert row["total_marks"] == 5
        assert row["question_count"] == 2


# ── Start / resume session ──────────────────────────────────────────────────

class TestStartSession:
    def test_starts_session_when_live(self, student_client, paper_with_set):
        paper, qset = paper_with_set
        assignment = _assignment(paper)
        _allocate(assignment, qset)

        resp = student_client.post(f"/api/assessments/student/assignments/{assignment.id}/start-session/")

        assert resp.status_code == 201
        body = resp.json()["data"]
        assert body["status"] == SESSION_STATUS_IN_PROGRESS
        assert AssessmentSession.objects.filter(assignment=assignment, student_id=STUDENT_USER_ID).exists()

    def test_rejected_before_live(self, student_client, paper_with_set):
        paper, qset = paper_with_set
        assignment = _assignment(paper, status=ASSIGNMENT_STATUS_SCHEDULED)
        _allocate(assignment, qset)

        resp = student_client.post(f"/api/assessments/student/assignments/{assignment.id}/start-session/")

        assert resp.status_code == 403
        assert "not yet live" in resp.json()["message"].lower()
        assert not AssessmentSession.objects.filter(assignment=assignment).exists()

    def test_refresh_resumes_same_session_same_ends_at(self, student_client, paper_with_set):
        paper, qset = paper_with_set
        assignment = _assignment(paper)
        _allocate(assignment, qset)

        first = student_client.post(f"/api/assessments/student/assignments/{assignment.id}/start-session/")
        second = student_client.post(f"/api/assessments/student/assignments/{assignment.id}/start-session/")

        assert first.status_code == 201
        assert second.status_code == 200
        assert first.json()["data"]["session_id"] == second.json()["data"]["session_id"]
        assert first.json()["data"]["ends_at"] == second.json()["data"]["ends_at"]
        assert AssessmentSession.objects.filter(assignment=assignment, student_id=STUDENT_USER_ID).count() == 1

    def test_not_allocated_returns_404(self, student_client, paper_with_set):
        paper, qset = paper_with_set
        assignment = _assignment(paper)
        # deliberately no allocation created

        resp = student_client.post(f"/api/assessments/student/assignments/{assignment.id}/start-session/")
        assert resp.status_code == 404

    def test_ends_at_capped_to_global_expire_time(self, student_client, paper_with_set):
        paper, qset = paper_with_set
        expire = timezone.now() + timedelta(seconds=1)
        assignment = _assignment(paper, global_expire_time=expire, exam_duration_minutes=60)
        _allocate(assignment, qset)

        resp = student_client.post(f"/api/assessments/student/assignments/{assignment.id}/start-session/")

        # Might already be expired by the time this runs (1s window) — that's
        # also a valid, correctly-rejected outcome; assert on whichever branch fires.
        if resp.status_code == 201:
            session = AssessmentSession.objects.get(pk=resp.json()["data"]["session_id"])
            assert abs((session.ends_at - expire).total_seconds()) < 1
        else:
            assert resp.status_code == 403

    def test_expired_assignment_rejected_even_if_still_marked_live(self, student_client, paper_with_set):
        # Simulates sweep lag (ADR 001) — status hasn't flipped to CLOSED
        # yet, but global_expire_time has already passed.
        paper, qset = paper_with_set
        assignment = _assignment(paper, global_expire_time=timezone.now() - timedelta(seconds=5))
        _allocate(assignment, qset)

        resp = student_client.post(f"/api/assessments/student/assignments/{assignment.id}/start-session/")

        assert resp.status_code == 403
        assert not AssessmentSession.objects.filter(assignment=assignment).exists()

    def test_can_resume_after_assignment_closed(self, student_client, paper_with_set):
        # A student who started while LIVE must still be able to see their
        # own session after the admin closes it — not get locked out of
        # their own resume call.
        paper, qset = paper_with_set
        assignment = _assignment(paper)
        _allocate(assignment, qset)
        student_client.post(f"/api/assessments/student/assignments/{assignment.id}/start-session/")

        BatchAssignment.objects.filter(pk=assignment.pk).update(status=ASSIGNMENT_STATUS_CLOSED)

        resp = student_client.post(f"/api/assessments/student/assignments/{assignment.id}/start-session/")
        assert resp.status_code == 200

    def test_admin_forbidden(self, admin_client, paper_with_set):
        paper, qset = paper_with_set
        assignment = _assignment(paper)
        resp = admin_client.post(f"/api/assessments/student/assignments/{assignment.id}/start-session/")
        assert resp.status_code == 403


# ── status/ extended with student_count_completed ──────────────────────────

class TestStatusWithCompletedCount:
    def test_completed_count_reflects_only_terminal_sessions(self, admin_client, paper_with_set):
        paper, qset = paper_with_set
        assignment = _assignment(paper)
        for _ in range(5):
            _allocate(assignment, qset, student_id=uuid.uuid4())

        # 2 completed (1 SUBMITTED, 1 AUTO_SUBMITTED), 1 still IN_PROGRESS, 2 never started
        AssessmentSession.objects.create(
            assignment=assignment, student_id=uuid.uuid4(), set=qset,
            ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_SUBMITTED,
        )
        AssessmentSession.objects.create(
            assignment=assignment, student_id=uuid.uuid4(), set=qset,
            ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_AUTO_SUBMITTED,
        )
        AssessmentSession.objects.create(
            assignment=assignment, student_id=uuid.uuid4(), set=qset,
            ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_IN_PROGRESS,
        )

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/status/")

        body = resp.json()["data"]
        assert body["student_count_total"] == 5
        assert body["student_count_completed"] == 2
