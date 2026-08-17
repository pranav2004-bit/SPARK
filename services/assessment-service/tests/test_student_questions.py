import json
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, Question, QuestionOption, BatchAssignment,
    AssessmentSession, AssessmentResponse, ASSIGNMENT_STATUS_LIVE,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


@pytest.fixture
def exam_setup(db):
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Questions Endpoint Test",
        created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    q1 = Question.objects.create(set=qset, question_text="Q1", marks=2)
    opt_correct = QuestionOption.objects.create(question=q1, label="A", text="right", is_correct=True, order=1)
    opt_wrong = QuestionOption.objects.create(question=q1, label="B", text="wrong", order=2)

    assignment = BatchAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
    )
    session = AssessmentSession.objects.create(
        assignment=assignment, student_id=STUDENT_USER_ID, set=qset,
        ends_at=timezone.now() + timedelta(hours=1),
    )
    return {"session": session, "q1": q1, "opt_correct": opt_correct, "opt_wrong": opt_wrong}


class TestStudentSessionQuestions:
    def test_returns_questions_with_options(self, student_client, exam_setup):
        session = exam_setup["session"]
        resp = student_client.get(f"/api/assessments/student/sessions/{session.id}/questions/")

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["session_id"] == str(session.id)
        assert len(body["questions"]) == 1
        assert body["questions"][0]["question_text"] == "Q1"
        assert len(body["questions"][0]["options"]) == 2

    def test_never_leaks_is_correct_anywhere_in_the_response(self, student_client, exam_setup):
        # Security-critical: serialize the whole payload to text and search
        # for the literal key — catches any future field addition that
        # accidentally reintroduces it, not just the fields checked above.
        session = exam_setup["session"]
        resp = student_client.get(f"/api/assessments/student/sessions/{session.id}/questions/")
        raw = json.dumps(resp.json())
        assert "is_correct" not in raw

    def test_includes_previously_saved_answer(self, student_client, exam_setup):
        session, q1, opt = exam_setup["session"], exam_setup["q1"], exam_setup["opt_correct"]
        AssessmentResponse.objects.create(session=session, question=q1, selected_option_ids=[str(opt.id)])

        resp = student_client.get(f"/api/assessments/student/sessions/{session.id}/questions/")
        body = resp.json()["data"]
        assert body["questions"][0]["selected_option_ids"] == [str(opt.id)]

    def test_unanswered_question_has_empty_selection(self, student_client, exam_setup):
        session = exam_setup["session"]
        resp = student_client.get(f"/api/assessments/student/sessions/{session.id}/questions/")
        assert resp.json()["data"]["questions"][0]["selected_option_ids"] == []

    def test_another_students_session_not_accessible(self, student_client, exam_setup):
        other_session = AssessmentSession.objects.create(
            assignment=exam_setup["session"].assignment, student_id=uuid.uuid4(),
            set=exam_setup["session"].set, ends_at=timezone.now() + timedelta(hours=1),
        )
        resp = student_client.get(f"/api/assessments/student/sessions/{other_session.id}/questions/")
        assert resp.status_code == 404

    def test_admin_forbidden(self, admin_client, exam_setup):
        resp = admin_client.get(f"/api/assessments/student/sessions/{exam_setup['session'].id}/questions/")
        assert resp.status_code == 403
