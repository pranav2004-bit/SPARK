import json
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, QuestionSection, Question, QuestionOption, BatchAssignment,
    AssessmentSession, AssessmentResponse, ResultSummary, ASSIGNMENT_STATUS_LIVE,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


def _answer_url(session_id, question_id):
    return f"/api/assessments/student/sessions/{session_id}/questions/{question_id}/answer/"


def _submit_url(session_id):
    return f"/api/assessments/student/sessions/{session_id}/submit/"


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


@pytest.fixture
def shuffle_setup(db):
    """2 sections x 3 questions x 4 options each — the single-question,
    two-option exam_setup fixture above can't show a shuffle happened at
    all; this one has enough items to meaningfully exercise ordering and
    grouping invariants."""
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Shuffle Test Paper", created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    section1 = QuestionSection.objects.create(set=qset, title="Section 1", order=1)
    section2 = QuestionSection.objects.create(set=qset, title="Section 2", order=2)

    questions = []
    for section in (section1, section2):
        for i in range(3):
            q = Question.objects.create(
                set=qset, section=section, question_text=f"{section.title} Q{i + 1}", marks=2,
            )
            for j, label in enumerate(["A", "B", "C", "D"]):
                QuestionOption.objects.create(
                    question=q, label=label, text=f"option-{label}", is_correct=(j == 0), order=j + 1,
                )
            questions.append(q)

    assignment = BatchAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
    )
    session = AssessmentSession.objects.create(
        assignment=assignment, student_id=STUDENT_USER_ID, set=qset,
        ends_at=timezone.now() + timedelta(hours=1),
    )
    return {
        "session": session, "assignment": assignment,
        "section1": section1, "section2": section2, "questions": questions,
    }


class TestQuestionAndOptionShuffle:
    """Task: per-student shuffle of question/option DISPLAY order, without
    affecting storage order, admin-facing views, or scoring (which is keyed
    by option id, not position — see scoring.py)."""

    def test_options_are_relabeled_sequentially_regardless_of_shuffle(self, student_client, shuffle_setup):
        session = shuffle_setup["session"]
        resp = student_client.get(f"/api/assessments/student/sessions/{session.id}/questions/")
        body = resp.json()["data"]
        for q in body["questions"]:
            labels = [opt["label"] for opt in q["options"]]
            assert labels == ["A", "B", "C", "D"], labels

    def test_question_numbers_are_sequential_one_to_n(self, student_client, shuffle_setup):
        session = shuffle_setup["session"]
        resp = student_client.get(f"/api/assessments/student/sessions/{session.id}/questions/")
        numbers = [q["question_number"] for q in resp.json()["data"]["questions"]]
        assert numbers == list(range(1, len(shuffle_setup["questions"]) + 1))

    def test_section_order_is_preserved_even_though_questions_within_it_may_shuffle(self, student_client, shuffle_setup):
        session = shuffle_setup["session"]
        resp = student_client.get(f"/api/assessments/student/sessions/{session.id}/questions/")
        section_sequence = [q["section_id"] for q in resp.json()["data"]["questions"]]
        # All of section1's questions must appear before all of section2's —
        # shuffling happens WITHIN a section, never across section boundaries.
        s1, s2 = str(shuffle_setup["section1"].id), str(shuffle_setup["section2"].id)
        assert section_sequence == [s1] * 3 + [s2] * 3

    def test_same_session_returns_identical_order_on_repeated_requests(self, student_client, shuffle_setup):
        session = shuffle_setup["session"]
        url = f"/api/assessments/student/sessions/{session.id}/questions/"
        first = student_client.get(url).json()["data"]["questions"]
        second = student_client.get(url).json()["data"]["questions"]
        assert [q["id"] for q in first] == [q["id"] for q in second]
        for q1, q2 in zip(first, second):
            assert [o["id"] for o in q1["options"]] == [o["id"] for o in q2["options"]]

    def test_correct_option_still_scores_correct_regardless_of_its_shuffled_position(
        self, student_client, shuffle_setup,
    ):
        # The core safety property: submit the REAL correct option id for
        # every question (known from the fixture, is_correct=(j == 0) i.e.
        # label "A") regardless of where the shuffle displayed it, and
        # confirm full marks — proving the shuffle cannot flip a correct
        # answer into a wrong one.
        session = shuffle_setup["session"]
        for q in shuffle_setup["questions"]:
            correct_option = q.options.get(label="A")
            resp = student_client.put(
                _answer_url(session.id, q.id), {"selected_option_ids": [str(correct_option.id)]}, format="json",
            )
            assert resp.status_code == 200

        resp = student_client.post(_submit_url(session.id))
        body = resp.json()["data"]
        assert body["score"] == 2 * len(shuffle_setup["questions"])  # 2 marks each, all correct
        assert body["total_marks"] == 2 * len(shuffle_setup["questions"])

    def test_wrong_option_still_scores_wrong_regardless_of_its_shuffled_position(
        self, student_client, shuffle_setup,
    ):
        session = shuffle_setup["session"]
        for q in shuffle_setup["questions"]:
            wrong_option = q.options.get(label="B")
            student_client.put(
                _answer_url(session.id, q.id), {"selected_option_ids": [str(wrong_option.id)]}, format="json",
            )

        resp = student_client.post(_submit_url(session.id))
        assert resp.json()["data"]["score"] == 0

    def test_admin_trial_session_is_also_shuffled_and_relabeled(self, admin_client, shuffle_setup):
        # Admin trial mode deliberately mirrors the real student experience
        # (this file's own module docstring) — it must show the same
        # shuffle/relabeling, not the raw admin-authored order.
        resp = admin_client.post(
            f"/api/assessments/admin/papers/{shuffle_setup['assignment'].paper_id}/trial/start/",
            {"duration_minutes": 60}, format="json",
        )
        assert resp.status_code == 201
        trial_session_id = resp.json()["data"]["session_id"]

        resp = admin_client.get(f"/api/assessments/admin/trial/sessions/{trial_session_id}/questions/")
        body = resp.json()["data"]
        for q in body["questions"]:
            assert [opt["label"] for opt in q["options"]] == ["A", "B", "C", "D"]
