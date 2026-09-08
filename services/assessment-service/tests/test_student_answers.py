import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, Question, QuestionOption, BatchAssignment,
    AssessmentSession, AssessmentResponse, ResultSummary,
    ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_CLOSED,
    SESSION_STATUS_IN_PROGRESS, SESSION_STATUS_SUBMITTED, SESSION_STATUS_AUTO_SUBMITTED,
    MCQ_TYPE_SINGLE, MCQ_TYPE_MULTIPLE,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


@pytest.fixture
def exam_setup(db):
    """A paper with 3 questions: a 2-mark single-select, a 3-mark
    multi-select, and a 1-mark single-select — total 6 marks."""
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Answers Test Paper",
        created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)

    q1 = Question.objects.create(set=qset, question_text="Q1", marks=2, mcq_type=MCQ_TYPE_SINGLE)
    q1_correct = QuestionOption.objects.create(question=q1, label="A", text="right", is_correct=True, order=1)
    QuestionOption.objects.create(question=q1, label="B", text="wrong", order=2)

    q2 = Question.objects.create(set=qset, question_text="Q2", marks=3, mcq_type=MCQ_TYPE_MULTIPLE)
    q2_c1 = QuestionOption.objects.create(question=q2, label="A", text="right1", is_correct=True, order=1)
    q2_c2 = QuestionOption.objects.create(question=q2, label="B", text="right2", is_correct=True, order=2)
    QuestionOption.objects.create(question=q2, label="C", text="wrong", order=3)

    q3 = Question.objects.create(set=qset, question_text="Q3", marks=1, mcq_type=MCQ_TYPE_SINGLE)
    q3_correct = QuestionOption.objects.create(question=q3, label="A", text="right", is_correct=True, order=1)
    QuestionOption.objects.create(question=q3, label="B", text="wrong", order=2)

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
        "paper": paper, "qset": qset, "assignment": assignment, "session": session,
        "q1": q1, "q1_correct": q1_correct,
        "q2": q2, "q2_c1": q2_c1, "q2_c2": q2_c2,
        "q3": q3, "q3_correct": q3_correct,
    }


def _answer_url(session_id, question_id):
    return f"/api/assessments/student/sessions/{session_id}/questions/{question_id}/answer/"


def _submit_url(session_id):
    return f"/api/assessments/student/sessions/{session_id}/submit/"


# ── Answer PUT ───────────────────────────────────────────────────────────────

class TestAnswerPut:
    def test_saves_answer_and_is_idempotent_upsert(self, student_client, exam_setup):
        session, q1, opt = exam_setup["session"], exam_setup["q1"], exam_setup["q1_correct"]

        resp1 = student_client.put(
            _answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json",
        )
        resp2 = student_client.put(
            _answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json",
        )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert AssessmentResponse.objects.filter(session=session, question=q1).count() == 1

    def test_changing_answer_overwrites_previous_selection(self, student_client, exam_setup):
        session, q1 = exam_setup["session"], exam_setup["q1"]
        wrong = q1.options.filter(is_correct=False).first()
        correct = exam_setup["q1_correct"]

        student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(wrong.id)]}, format="json")
        student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(correct.id)]}, format="json")

        response = AssessmentResponse.objects.get(session=session, question=q1)
        assert response.selected_option_ids == [str(correct.id)]

    def test_is_correct_not_computed_at_answer_time(self, student_client, exam_setup):
        session, q1, opt = exam_setup["session"], exam_setup["q1"], exam_setup["q1_correct"]
        student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json")
        response = AssessmentResponse.objects.get(session=session, question=q1)
        assert response.is_correct is False  # not scored until finalize
        assert response.marks_awarded == 0

    def test_rejects_option_from_a_different_question(self, student_client, exam_setup):
        session, q1 = exam_setup["session"], exam_setup["q1"]
        foreign_option = exam_setup["q2_c1"]  # belongs to q2, not q1

        resp = student_client.put(
            _answer_url(session.id, q1.id), {"selected_option_ids": [str(foreign_option.id)]}, format="json",
        )
        assert resp.status_code == 400

    def test_forged_answered_at_field_is_ignored(self, student_client, exam_setup):
        session, q1, opt = exam_setup["session"], exam_setup["q1"], exam_setup["q1_correct"]
        resp = student_client.put(
            _answer_url(session.id, q1.id),
            {"selected_option_ids": [str(opt.id)], "answered_at": "2000-01-01T00:00:00Z"},
            format="json",
        )
        assert resp.status_code == 200
        response = AssessmentResponse.objects.get(session=session, question=q1)
        assert response.answered_at.year > 2000

    def test_rejected_after_ends_at(self, student_client, exam_setup):
        session, q1, opt = exam_setup["session"], exam_setup["q1"], exam_setup["q1_correct"]
        AssessmentSession.objects.filter(pk=session.pk).update(ends_at=timezone.now() - timedelta(seconds=1))

        resp = student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json")
        assert resp.status_code == 403

    def test_rejected_when_assignment_closed(self, student_client, exam_setup):
        session, q1, opt = exam_setup["session"], exam_setup["q1"], exam_setup["q1_correct"]
        BatchAssignment.objects.filter(pk=exam_setup["assignment"].pk).update(status=ASSIGNMENT_STATUS_CLOSED)

        resp = student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json")
        assert resp.status_code == 403

    def test_answering_question_not_in_own_set_rejected(self, student_client, exam_setup):
        # A question that exists but belongs to a different set entirely.
        other_set = QuestionSet.objects.create(paper=exam_setup["paper"], label="Set B", order=2)
        other_question = Question.objects.create(set=other_set, question_text="foreign", marks=1)

        resp = student_client.put(
            _answer_url(exam_setup["session"].id, other_question.id), {"selected_option_ids": []}, format="json",
        )
        assert resp.status_code == 404

    def test_another_students_session_not_accessible(self, student_client, exam_setup):
        other_session = AssessmentSession.objects.create(
            assignment=exam_setup["assignment"], student_id=uuid.uuid4(), set=exam_setup["qset"],
            ends_at=timezone.now() + timedelta(hours=1),
        )
        resp = student_client.put(
            _answer_url(other_session.id, exam_setup["q1"].id), {"selected_option_ids": []}, format="json",
        )
        assert resp.status_code == 404


# ── Answer activity logging (2026-08-18) ─────────────────────────────────────
# StudentAnswerView writes its own ActivityLog entries for the admin
# timeline's "every single student action" requirement — a first answer and
# a genuine change are both real behavior worth showing; a resave of the
# exact same value (a debounced autosave retry, a network retry) is not.

class TestAnswerActivityLogging:
    def test_first_answer_logs_question_answered(self, student_client, exam_setup):
        from assessments.models import ActivityLog
        session, q1, opt = exam_setup["session"], exam_setup["q1"], exam_setup["q1_correct"]

        student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json")

        logs = ActivityLog.objects.filter(session=session)
        assert logs.count() == 1
        assert logs.first().event_type == "question_answered"
        assert logs.first().metadata == {"question_number": q1.question_number}

    def test_changing_the_answer_logs_question_answer_changed(self, student_client, exam_setup):
        from assessments.models import ActivityLog
        session, q1 = exam_setup["session"], exam_setup["q1"]
        wrong = q1.options.filter(is_correct=False).first()
        correct = exam_setup["q1_correct"]

        student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(wrong.id)]}, format="json")
        student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(correct.id)]}, format="json")

        logs = list(ActivityLog.objects.filter(session=session).order_by("occurred_at"))
        assert [l.event_type for l in logs] == ["question_answered", "question_answer_changed"]

    def test_resaving_the_identical_answer_logs_nothing_new(self, student_client, exam_setup):
        # A debounced autosave firing twice, or a network retry, with the
        # exact same payload — not a "change", must not spam the timeline.
        from assessments.models import ActivityLog
        session, q1, opt = exam_setup["session"], exam_setup["q1"], exam_setup["q1_correct"]

        student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json")
        student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json")

        logs = ActivityLog.objects.filter(session=session)
        assert logs.count() == 1  # just the original "answered", not a second event

    def test_answering_multiple_questions_logs_each_separately(self, student_client, exam_setup):
        from assessments.models import ActivityLog
        session = exam_setup["session"]

        student_client.put(_answer_url(session.id, exam_setup["q1"].id), {"selected_option_ids": [str(exam_setup["q1_correct"].id)]}, format="json")
        student_client.put(_answer_url(session.id, exam_setup["q3"].id), {"selected_option_ids": [str(exam_setup["q3_correct"].id)]}, format="json")

        logs = ActivityLog.objects.filter(session=session, event_type="question_answered")
        assert {l.metadata.get("question_number") for l in logs} == {exam_setup["q1"].question_number, exam_setup["q3"].question_number}

    def test_lost_upsert_race_does_not_double_log(self, student_client, exam_setup, monkeypatch):
        # Simulates two near-simultaneous identical PUTs colliding on the
        # same (session, question) unique constraint — the losing request's
        # own IntegrityError branch must not also write an activity event,
        # since the winner's request already logged the one real write.
        from unittest.mock import patch
        from django.db import IntegrityError
        from assessments.models import ActivityLog, AssessmentResponse

        session, q1, opt = exam_setup["session"], exam_setup["q1"], exam_setup["q1_correct"]
        # Pre-create the row out-of-band, simulating the concurrent winner,
        # then force this request's update_or_create to still raise
        # IntegrityError as if it lost the race.
        AssessmentResponse.objects.create(session=session, question=q1, selected_option_ids=[str(opt.id)])

        with patch("assessments.models.AssessmentResponse.objects.update_or_create", side_effect=IntegrityError("dup")):
            resp = student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json")

        assert resp.status_code == 200
        assert ActivityLog.objects.filter(session=session).count() == 0


# ── Submit & scoring ─────────────────────────────────────────────────────────

class TestSubmitAndScoring:
    def test_full_correct_answers_scores_max_marks(self, student_client, exam_setup):
        session = exam_setup["session"]
        student_client.put(_answer_url(session.id, exam_setup["q1"].id),
                            {"selected_option_ids": [str(exam_setup["q1_correct"].id)]}, format="json")
        student_client.put(_answer_url(session.id, exam_setup["q2"].id),
                            {"selected_option_ids": [str(exam_setup["q2_c1"].id), str(exam_setup["q2_c2"].id)]}, format="json")
        student_client.put(_answer_url(session.id, exam_setup["q3"].id),
                            {"selected_option_ids": [str(exam_setup["q3_correct"].id)]}, format="json")

        resp = student_client.post(_submit_url(session.id))

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["status"] == SESSION_STATUS_SUBMITTED
        assert body["score"] == 6  # 2 + 3 + 1
        assert body["total_marks"] == 6

    def test_partial_multiselect_gets_zero_no_partial_credit(self, student_client, exam_setup):
        # Exact-match policy (Decision #1) — selecting only ONE of the two
        # correct options for a multi-select question earns 0, not partial.
        session = exam_setup["session"]
        student_client.put(_answer_url(session.id, exam_setup["q2"].id),
                            {"selected_option_ids": [str(exam_setup["q2_c1"].id)]}, format="json")

        student_client.post(_submit_url(session.id))

        response = AssessmentResponse.objects.get(session=session, question=exam_setup["q2"])
        assert response.is_correct is False
        assert response.marks_awarded == 0

    def test_overselecting_multiselect_gets_zero(self, student_client, exam_setup):
        # Selecting the 2 correct + 1 wrong option is not an exact match.
        session = exam_setup["session"]
        q2 = exam_setup["q2"]
        wrong_opt = q2.options.filter(is_correct=False).first()
        student_client.put(_answer_url(session.id, q2.id), {
            "selected_option_ids": [str(exam_setup["q2_c1"].id), str(exam_setup["q2_c2"].id), str(wrong_opt.id)],
        }, format="json")

        student_client.post(_submit_url(session.id))

        response = AssessmentResponse.objects.get(session=session, question=q2)
        assert response.marks_awarded == 0

    def test_unanswered_question_scores_zero_not_error(self, student_client, exam_setup):
        session = exam_setup["session"]
        student_client.put(_answer_url(session.id, exam_setup["q1"].id),
                            {"selected_option_ids": [str(exam_setup["q1_correct"].id)]}, format="json")
        # q2 and q3 never answered at all.

        resp = student_client.post(_submit_url(session.id))

        assert resp.status_code == 200
        assert resp.json()["data"]["score"] == 2  # only q1's marks
        assert resp.json()["data"]["total_marks"] == 6

    def test_submit_shows_score_when_result_visible_by_default(self, student_client, exam_setup):
        session = exam_setup["session"]
        student_client.put(_answer_url(session.id, exam_setup["q1"].id),
                            {"selected_option_ids": [str(exam_setup["q1_correct"].id)]}, format="json")
        resp = student_client.post(_submit_url(session.id))
        body = resp.json()["data"]
        assert body["results_visible"] is True
        assert body["score"] == 2
        assert body["total_marks"] == 6

    def test_submit_hides_score_when_show_result_to_student_is_false(self, student_client, exam_setup):
        BatchAssignment.objects.filter(pk=exam_setup["assignment"].pk).update(show_result_to_student=False)
        session = exam_setup["session"]
        student_client.put(_answer_url(session.id, exam_setup["q1"].id),
                            {"selected_option_ids": [str(exam_setup["q1_correct"].id)]}, format="json")
        resp = student_client.post(_submit_url(session.id))
        body = resp.json()["data"]
        assert body["results_visible"] is False
        assert body["score"] is None
        assert body["total_marks"] is None
        # The real score is still computed and stored — only the API
        # response to the student is masked, admins still see it in full.
        result = ResultSummary.objects.get(session=session)
        assert result.score == 2

    def test_submit_is_idempotent_second_call_no_error(self, student_client, exam_setup):
        session = exam_setup["session"]
        first = student_client.post(_submit_url(session.id))
        second = student_client.post(_submit_url(session.id))

        assert first.status_code == 200
        assert second.status_code == 403  # session_is_writable rejects — already SUBMITTED
        assert ResultSummary.objects.filter(session=session).count() == 1

    def test_answer_retry_no_duplicate_no_double_score(self, student_client, exam_setup):
        # Simulated network retry: the exact same PUT sent twice before submit.
        session, q1, opt = exam_setup["session"], exam_setup["q1"], exam_setup["q1_correct"]
        student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json")
        student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json")

        resp = student_client.post(_submit_url(session.id))

        assert AssessmentResponse.objects.filter(session=session, question=q1).count() == 1
        assert resp.json()["data"]["score"] == 2  # not double-counted

    def test_manual_submit_and_sweep_race_exactly_one_wins(self, exam_setup):
        from assessments.scoring import finalize_sessions

        session = exam_setup["session"]
        manual = finalize_sessions(AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_SUBMITTED)
        sweep = finalize_sessions(AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_AUTO_SUBMITTED)

        assert manual == 1
        assert sweep == 0
        session.refresh_from_db()
        assert session.status == SESSION_STATUS_SUBMITTED
        assert ResultSummary.objects.filter(session=session).count() == 1

    def test_submit_rejected_after_assignment_closed(self, student_client, exam_setup):
        BatchAssignment.objects.filter(pk=exam_setup["assignment"].pk).update(status=ASSIGNMENT_STATUS_CLOSED)
        resp = student_client.post(_submit_url(exam_setup["session"].id))
        assert resp.status_code == 403

    def test_submit_someone_elses_session_404s(self, student_client, exam_setup):
        other_session = AssessmentSession.objects.create(
            assignment=exam_setup["assignment"], student_id=uuid.uuid4(), set=exam_setup["qset"],
            ends_at=timezone.now() + timedelta(hours=1),
        )
        resp = student_client.post(_submit_url(other_session.id))
        assert resp.status_code == 404


# ── Load ─────────────────────────────────────────────────────────────────────

class TestSubmitLoad:
    def test_2000_sessions_finalized_in_one_call(self, db, exam_setup):
        import time
        from assessments.scoring import finalize_sessions

        assignment, qset = exam_setup["assignment"], exam_setup["qset"]
        q1, q1_correct = exam_setup["q1"], exam_setup["q1_correct"]

        sessions = AssessmentSession.objects.bulk_create([
            AssessmentSession(
                assignment=assignment, student_id=uuid.uuid4(), set=qset,
                ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_IN_PROGRESS,
            )
            for _ in range(2000)
        ])
        AssessmentResponse.objects.bulk_create([
            AssessmentResponse(session=s, question=q1, selected_option_ids=[str(q1_correct.id)])
            for s in sessions
        ])

        session_ids = [s.id for s in sessions]
        start = time.monotonic()
        count = finalize_sessions(
            AssessmentSession.objects.filter(id__in=session_ids, status=SESSION_STATUS_IN_PROGRESS),
            SESSION_STATUS_SUBMITTED,
        )
        elapsed = time.monotonic() - start

        assert count == 2000
        assert ResultSummary.objects.filter(assignment=assignment, score=2).count() == 2000
        assert elapsed < 60, f"finalize took {elapsed:.1f}s for 2000 sessions"


class TestAnswerRateLimit:
    """Task 11.2 — per-student rate limit on the answer-autosave endpoint
    (AnswerSubmitRateThrottle, 120/min)."""

    def test_legitimate_rapid_answering_never_throttled(self, student_client, exam_setup):
        # 100 rapid PUTs, well under the 120/min budget — simulates a fast
        # student re-selecting/correcting answers in quick succession.
        session, q1, opt = exam_setup["session"], exam_setup["q1"], exam_setup["q1_correct"]
        for _ in range(100):
            resp = student_client.put(
                _answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json",
            )
            assert resp.status_code == 200

    def test_rate_limit_engages_past_threshold(self, student_client, exam_setup):
        session, q1, opt = exam_setup["session"], exam_setup["q1"], exam_setup["q1_correct"]
        statuses = []
        for _ in range(130):
            resp = student_client.put(
                _answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json",
            )
            statuses.append(resp.status_code)

        assert 429 in statuses
        # Requests before the limit engaged still succeeded — the whole
        # endpoint doesn't go dark, just gets capped.
        assert 200 in statuses

    def test_rate_limit_is_per_student_not_global(self, student_client, admin_client, exam_setup):
        # A different student hitting their own session must not be
        # affected by another student's throttle state.
        assignment, qset = exam_setup["assignment"], exam_setup["qset"]
        q1, opt = exam_setup["q1"], exam_setup["q1_correct"]
        other_student_id = uuid.uuid4()
        other_session = AssessmentSession.objects.create(
            assignment=assignment, student_id=other_student_id, set=qset,
            ends_at=timezone.now() + timedelta(hours=1),
        )

        session = exam_setup["session"]
        for _ in range(130):
            student_client.put(_answer_url(session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json")

        from .conftest import _make_token
        from rest_framework.test import APIClient
        other_token = _make_token(other_student_id, "student", INSTITUTION_A, student_id=other_student_id)
        other_client = APIClient()
        other_client.credentials(HTTP_AUTHORIZATION=f"Bearer {other_token}")

        resp = other_client.put(
            _answer_url(other_session.id, q1.id), {"selected_option_ids": [str(opt.id)]}, format="json",
        )
        assert resp.status_code == 200
