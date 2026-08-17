import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, BatchAssignment, AssessmentSession,
    ASSIGNMENT_STATUS_LIVE, SESSION_STATUS_IN_PROGRESS,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


@pytest.fixture
def live_assignment_and_set(db):
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Server Time Test Paper",
        created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    assignment = BatchAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID,
        status=ASSIGNMENT_STATUS_LIVE,
    )
    return assignment, qset


class TestStudentServerTime:
    def test_returns_server_time_with_no_active_session(self, student_client):
        resp = student_client.get("/api/assessments/student/server-time/")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert "server_time" in body
        assert "session_id" not in body
        assert "ends_at" not in body

    def test_returns_ends_at_for_own_in_progress_session(self, student_client, live_assignment_and_set):
        assignment, qset = live_assignment_and_set
        ends_at = timezone.now() + timedelta(minutes=42)
        session = AssessmentSession.objects.create(
            assignment=assignment, student_id=STUDENT_USER_ID, set=qset,
            ends_at=ends_at, status=SESSION_STATUS_IN_PROGRESS,
        )

        resp = student_client.get("/api/assessments/student/server-time/")

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["session_id"] == str(session.id)
        assert "ends_at" in body

    def test_does_not_return_another_students_session(self, student_client, live_assignment_and_set):
        # IDOR safety (AT3) — only the requesting student's own JWT
        # identity is used to look up a session, never anything else.
        assignment, qset = live_assignment_and_set
        AssessmentSession.objects.create(
            assignment=assignment, student_id=uuid.uuid4(), set=qset,  # a different student
            ends_at=timezone.now() + timedelta(minutes=10),
            status=SESSION_STATUS_IN_PROGRESS,
        )

        resp = student_client.get("/api/assessments/student/server-time/")

        assert resp.status_code == 200
        assert "session_id" not in resp.json()["data"]

    def test_ignores_non_in_progress_sessions(self, student_client, live_assignment_and_set):
        from assessments.models import SESSION_STATUS_SUBMITTED

        assignment, qset = live_assignment_and_set
        AssessmentSession.objects.create(
            assignment=assignment, student_id=STUDENT_USER_ID, set=qset,
            ends_at=timezone.now() + timedelta(minutes=10),
            status=SESSION_STATUS_SUBMITTED,
        )

        resp = student_client.get("/api/assessments/student/server-time/")

        assert "session_id" not in resp.json()["data"]

    def test_admin_forbidden(self, admin_client):
        resp = admin_client.get("/api/assessments/student/server-time/")
        assert resp.status_code == 403

    def test_anonymous_forbidden(self, anon_client):
        resp = anon_client.get("/api/assessments/student/server-time/")
        assert resp.status_code in (401, 403)
