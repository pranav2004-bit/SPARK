import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from assessments.models import (
    QuestionPaper, QuestionSet, Question, QuestionOption, BatchAssignment,
    AssessmentSession, AssessmentResponse, ASSIGNMENT_STATUS_LIVE,
    SESSION_STATUS_SUBMITTED,
)
from assessments.scoring import finalize_sessions

from .conftest import (
    INSTITUTION_A, INSTITUTION_B, ADMIN_USER_ID, ADMIN_B_USER_ID,
    COLLEAGUE_ADMIN_USER_ID, _make_token,
)


def _publish_url(assignment_id):
    return f"/api/assessments/admin/assignments/{assignment_id}/publish-results/"


def _answer_url(session_id, question_id):
    return f"/api/assessments/student/sessions/{session_id}/questions/{question_id}/answer/"


def _submit_url(session_id):
    return f"/api/assessments/student/sessions/{session_id}/submit/"


def _results_url():
    return "/api/assessments/student/results/"


def _client_for(student_id):
    token = _make_token(student_id, "student", institution_id=INSTITUTION_A, student_id=student_id)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def hidden_results_setup(db):
    """An assignment created with show_result_to_student=False — the
    starting state for every "publish results later" scenario."""
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Publish Results Test Paper", created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    q1 = Question.objects.create(set=qset, question_text="Q1", marks=5)
    opt_correct = QuestionOption.objects.create(question=q1, label="A", text="right", is_correct=True, order=1)
    QuestionOption.objects.create(question=q1, label="B", text="wrong", order=2)

    assignment = BatchAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_start_time=timezone.now() - timedelta(minutes=1),
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
        show_result_to_student=False,
    )
    return {"paper": paper, "qset": qset, "q1": q1, "opt_correct": opt_correct, "assignment": assignment}


def _complete_via_orm(assignment, qset, q1, opt_correct, student_id):
    """Directly completes a session for student_id — used for students who
    are already finished BEFORE the admin publishes, bypassing the HTTP
    layer purely for test setup speed (the actual proof of correctness is
    reading their result back through the real API afterward)."""
    session = AssessmentSession.objects.create(
        assignment=assignment, student_id=student_id, set=qset,
        ends_at=timezone.now() + timedelta(hours=1),
    )
    AssessmentResponse.objects.create(session=session, question=q1, selected_option_ids=[str(opt_correct.id)])
    finalize_sessions(AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_SUBMITTED)
    return session


class TestPublishResultsAccessControl:
    def test_admin_can_publish(self, admin_client, hidden_results_setup):
        assignment = hidden_results_setup["assignment"]
        resp = admin_client.patch(_publish_url(assignment.id))
        assert resp.status_code == 200
        assert resp.json()["data"]["show_result_to_student"] is True

    def test_student_forbidden(self, student_client, hidden_results_setup):
        resp = student_client.patch(_publish_url(hidden_results_setup["assignment"].id))
        assert resp.status_code == 403

    def test_cross_institution_404(self, admin_b_client, hidden_results_setup):
        resp = admin_b_client.patch(_publish_url(hidden_results_setup["assignment"].id))
        assert resp.status_code == 404

    def test_colleague_admin_at_same_institution_can_publish(self, colleague_admin_client, hidden_results_setup):
        # Assignment actions (start/close/status/extend) are institution-
        # wide, not owner-gated — this action follows the same convention,
        # not the paper-content-editing one.
        resp = colleague_admin_client.patch(_publish_url(hidden_results_setup["assignment"].id))
        assert resp.status_code == 200
        assert resp.json()["data"]["show_result_to_student"] is True

    def test_nonexistent_assignment_404(self, admin_client, db):
        resp = admin_client.patch(_publish_url(uuid.uuid4()))
        assert resp.status_code == 404


class TestPublishResultsIdempotency:
    def test_publishing_sets_flag_and_timestamp(self, admin_client, hidden_results_setup):
        assignment = hidden_results_setup["assignment"]
        assert assignment.results_published_at is None

        resp = admin_client.patch(_publish_url(assignment.id))
        assignment.refresh_from_db()
        assert assignment.show_result_to_student is True
        assert assignment.results_published_at is not None
        assert resp.json()["message"] == "Results published — visible to students now."

    def test_publishing_twice_keeps_the_original_timestamp(self, admin_client, hidden_results_setup):
        assignment = hidden_results_setup["assignment"]
        admin_client.patch(_publish_url(assignment.id))
        assignment.refresh_from_db()
        first_timestamp = assignment.results_published_at

        resp = admin_client.patch(_publish_url(assignment.id))
        assignment.refresh_from_db()
        assert resp.status_code == 200
        assert resp.json()["message"] == "Results are already visible to students."
        assert assignment.results_published_at == first_timestamp

    def test_assignment_created_with_results_already_visible_has_no_publish_timestamp(self, admin_client, db):
        paper = QuestionPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
        qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
        assignment = BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_start_time=timezone.now() - timedelta(minutes=1),
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
            show_result_to_student=True,  # visible from creation — never "published"
        )
        resp = admin_client.patch(_publish_url(assignment.id))
        assert resp.status_code == 200
        assert resp.json()["message"] == "Results are already visible to students."
        assignment.refresh_from_db()
        assert assignment.results_published_at is None


class TestPublishResultsScenarios:
    """The three real-world cases this feature exists for, each proven
    through the actual HTTP endpoints a student/admin would hit — not just
    asserting the raw model flag."""

    def test_case1_already_completed_student_sees_results_after_publish(
        self, admin_client, hidden_results_setup,
    ):
        s = hidden_results_setup
        student_id = uuid.uuid4()
        _complete_via_orm(s["assignment"], s["qset"], s["q1"], s["opt_correct"], student_id)

        client = _client_for(student_id)
        before = client.get(_results_url()).json()["data"][0]
        assert before["results_visible"] is False
        assert before["score"] is None

        admin_client.patch(_publish_url(s["assignment"].id))

        after = client.get(_results_url()).json()["data"][0]
        assert after["results_visible"] is True
        assert after["score"] == 5
        assert after["total_marks"] == 5

    def test_case2_student_who_has_not_started_sees_results_immediately_on_completion_after_publish(
        self, admin_client, hidden_results_setup,
    ):
        s = hidden_results_setup
        admin_client.patch(_publish_url(s["assignment"].id))  # published before anyone even starts

        student_id = uuid.uuid4()
        client = _client_for(student_id)
        session = AssessmentSession.objects.create(
            assignment=s["assignment"], student_id=student_id, set=s["qset"],
            ends_at=timezone.now() + timedelta(hours=1),
        )
        client.put(
            _answer_url(session.id, s["q1"].id),
            {"selected_option_ids": [str(s["opt_correct"].id)]}, format="json",
        )
        resp = client.post(_submit_url(session.id))
        body = resp.json()["data"]
        assert body["results_visible"] is True
        assert body["score"] == 5
        assert body["total_marks"] == 5

    def test_case3_mixed_already_done_in_progress_and_not_started_all_see_results_correctly(
        self, admin_client, hidden_results_setup,
    ):
        s = hidden_results_setup

        # Student A: already completed BEFORE publish.
        student_a = uuid.uuid4()
        _complete_via_orm(s["assignment"], s["qset"], s["q1"], s["opt_correct"], student_a)

        # Student B: mid-exam at the moment of publish (session open, unanswered yet).
        student_b = uuid.uuid4()
        client_b = _client_for(student_b)
        session_b = AssessmentSession.objects.create(
            assignment=s["assignment"], student_id=student_b, set=s["qset"],
            ends_at=timezone.now() + timedelta(hours=1),
        )

        # Student C: hasn't started at all yet, allocated only after publish.
        student_c = uuid.uuid4()

        # --- admin publishes, with A done, B mid-exam, C not yet started ---
        admin_client.patch(_publish_url(s["assignment"].id))

        # A: already-completed student now sees their result.
        client_a = _client_for(student_a)
        result_a = client_a.get(_results_url()).json()["data"][0]
        assert result_a["results_visible"] is True
        assert result_a["score"] == 5

        # B: finishes the exam that was already in progress at publish time.
        client_b.put(
            _answer_url(session_b.id, s["q1"].id),
            {"selected_option_ids": [str(s["opt_correct"].id)]}, format="json",
        )
        resp_b = client_b.post(_submit_url(session_b.id))
        body_b = resp_b.json()["data"]
        assert body_b["results_visible"] is True
        assert body_b["score"] == 5

        # C: starts and finishes entirely after publish.
        client_c = _client_for(student_c)
        session_c = AssessmentSession.objects.create(
            assignment=s["assignment"], student_id=student_c, set=s["qset"],
            ends_at=timezone.now() + timedelta(hours=1),
        )
        client_c.put(
            _answer_url(session_c.id, s["q1"].id),
            {"selected_option_ids": [str(s["opt_correct"].id)]}, format="json",
        )
        resp_c = client_c.post(_submit_url(session_c.id))
        body_c = resp_c.json()["data"]
        assert body_c["results_visible"] is True
        assert body_c["score"] == 5
