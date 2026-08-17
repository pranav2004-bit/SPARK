import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, Question, QuestionOption, BatchAssignment,
    StudentSetAllocation, AssessmentSession, ResultSummary,
    ASSIGNMENT_STATUS_LIVE, SESSION_STATUS_IN_PROGRESS,
    SESSION_STATUS_SUBMITTED, SESSION_STATUS_AUTO_SUBMITTED,
)
from assessments.scoring import finalize_sessions
from assessments import views as assessments_views

from .conftest import INSTITUTION_A, ADMIN_USER_ID


@pytest.fixture
def dashboard_setup(db):
    """Hand-computable fixture.

    5 students allocated total. Of those: 2 SUBMITTED (one 100%, one 0% +
    flagged), 1 AUTO_SUBMITTED (50%), 1 still IN_PROGRESS, 1 never started
    a session at all.

    completion_rate = 3/5 * 100 = 60.0
    average_score_percentage = (100 + 0 + 50) / 3 = 50.0
    malpractice_incidents = 1
    on_time (SUBMITTED) = 2, auto_submitted = 1, on_time_percentage = 2/3*100 = 66.67
    student_count_in_progress = 1
    """
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Dashboard Test Paper",
        created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    q1 = Question.objects.create(set=qset, question_text="Q1", marks=10)
    q1_correct = QuestionOption.objects.create(question=q1, label="A", text="r", is_correct=True, order=1)
    q1_wrong = QuestionOption.objects.create(question=q1, label="B", text="w", order=2)

    assignment = BatchAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
        pass_cutoff_percentage=40,
    )

    students = {key: uuid.uuid4() for key in [
        "submitted_100", "submitted_0_flagged", "auto_submitted_50",
        "in_progress", "never_started",
    ]}

    for key, sid in students.items():
        StudentSetAllocation.objects.create(assignment=assignment, student_id=sid, set=qset)

    def _make_completed(student_key, status, score, flagged=False):
        sid = students[student_key]
        session = AssessmentSession.objects.create(
            assignment=assignment, student_id=sid, set=qset,
            ends_at=timezone.now() + timedelta(hours=1), status=status,
            started_at=timezone.now() - timedelta(minutes=10),
        )
        ResultSummary.objects.create(
            session=session, assignment=assignment, student_id=sid, institution_id=INSTITUTION_A,
            started_at=session.started_at, ended_at=timezone.now(), duration_seconds=600,
            score=score, total_marks=10, status=status,
            malpractice_flag=flagged, malpractice_reasons=["tab_switch"] if flagged else [],
        )
        return session

    _make_completed("submitted_100", SESSION_STATUS_SUBMITTED, 10)
    _make_completed("submitted_0_flagged", SESSION_STATUS_SUBMITTED, 0, flagged=True)
    _make_completed("auto_submitted_50", SESSION_STATUS_AUTO_SUBMITTED, 5)

    in_progress_session = AssessmentSession.objects.create(
        assignment=assignment, student_id=students["in_progress"], set=qset,
        ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_IN_PROGRESS,
        started_at=timezone.now() - timedelta(minutes=5),
    )

    return {
        "assignment": assignment, "students": students,
        "in_progress_session": in_progress_session,
        "question": q1, "correct_option": q1_correct,
    }


class TestDashboard:
    def test_hand_computed_values_match_exactly(self, admin_client, dashboard_setup):
        assignment = dashboard_setup["assignment"]
        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/dashboard/")
        assert resp.status_code == 200
        data = resp.json()["data"]

        assert data["student_count_total"] == 5
        assert data["student_count_completed"] == 3
        assert data["student_count_in_progress"] == 1
        assert data["completion_rate_percentage"] == 60.0
        assert data["average_score_percentage"] == 50.0
        assert data["malpractice_incidents"] == 1

        sb = data["submission_breakdown"]
        assert sb["on_time"] == 2
        assert sb["auto_submitted"] == 1
        assert sb["on_time_percentage"] == 66.67

        assert "metric_definitions" in data

    def test_cache_hit_avoids_recomputation(self, admin_client, dashboard_setup):
        assignment = dashboard_setup["assignment"]
        with patch.object(assessments_views, "_compute_dashboard", wraps=assessments_views._compute_dashboard) as mock_compute:
            admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/dashboard/")
            admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/dashboard/")
            admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/dashboard/")
            assert mock_compute.call_count == 1

    def test_cache_invalidated_on_new_submission_not_just_ttl(self, admin_client, dashboard_setup):
        assignment = dashboard_setup["assignment"]

        first = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/dashboard/")
        assert first.json()["data"]["student_count_completed"] == 3

        # A new submission finalizes via the shared scoring.finalize_sessions()
        # primitive — this must explicitly drop the cached dashboard, not
        # rely on the 300s defensive-backstop TTL expiring.
        finalized_count = finalize_sessions(
            AssessmentSession.objects.filter(id=dashboard_setup["in_progress_session"].id),
            SESSION_STATUS_SUBMITTED,
        )
        assert finalized_count == 1

        second = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/dashboard/")
        data = second.json()["data"]
        assert data["student_count_completed"] == 4
        assert data["student_count_in_progress"] == 0

    def test_cross_institution_404(self, admin_b_client, dashboard_setup):
        resp = admin_b_client.get(f"/api/assessments/admin/assignments/{dashboard_setup['assignment'].id}/dashboard/")
        assert resp.status_code == 404

    def test_student_forbidden(self, student_client, dashboard_setup):
        resp = student_client.get(f"/api/assessments/admin/assignments/{dashboard_setup['assignment'].id}/dashboard/")
        assert resp.status_code == 403

    def test_zero_students_no_division_by_zero(self, admin_client, dashboard_setup):
        paper = dashboard_setup["assignment"].paper
        empty_assignment = BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
        )
        resp = admin_client.get(f"/api/assessments/admin/assignments/{empty_assignment.id}/dashboard/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["student_count_total"] == 0
        assert data["completion_rate_percentage"] == 0.0
        assert data["average_score_percentage"] == 0.0
        assert data["submission_breakdown"]["on_time_percentage"] == 0.0


class TestDashboardExport:
    def test_export_contains_kpis(self, admin_client, dashboard_setup):
        assignment = dashboard_setup["assignment"]
        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/dashboard/export/")
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert content.startswith("﻿")
        for section in ["Assessment Dashboard", "Submission Breakdown"]:
            assert section in content
        assert "60.0" in content  # completion rate, sanity check real numbers made it in

    def test_cross_institution_404(self, admin_b_client, dashboard_setup):
        resp = admin_b_client.get(f"/api/assessments/admin/assignments/{dashboard_setup['assignment'].id}/dashboard/export/")
        assert resp.status_code == 404
