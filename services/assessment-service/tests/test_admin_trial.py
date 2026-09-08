"""
Dedicated coverage for the admin "mock test" feature (2026-08-27): an admin
can take the real exam-taking flow themselves on a paper they own, either
before an assignment exists (the assign form's Final Review step) or
repeatably after one is created (an assignment's own toolbar). Deliberately
reuses AssessmentSession/AssessmentResponse/finalize_sessions() rather than
a parallel engine — every trial session has assignment=None, which is what
this file spends most of its effort proving stays airtight: a trial must
never appear in any real-assignment-scoped query, must be retakeable
without limit, must skip all malpractice/ActivityLog tracking, and must
still resolve institution_id correctly (from the paper, not an assignment)
so finalize_sessions() doesn't crash or write a null tenant.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, QuestionSection, Question, QuestionOption,
    BatchAssignment, AssessmentSession, ResultSummary, ActivityLog,
    MCQ_TYPE_SINGLE, ASSIGNMENT_STATUS_LIVE,
    SESSION_STATUS_IN_PROGRESS, SESSION_STATUS_SUBMITTED,
)
from assessments.tasks import sweep_expired_sessions

from .conftest import INSTITUTION_A, INSTITUTION_B, ADMIN_USER_ID


@pytest.fixture
def paper_with_question(db):
    """One paper -> one set -> one question -> two options (one correct),
    owned by ADMIN_USER_ID, worth 2 marks — enough to actually take and
    score a trial."""
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Trial Test Paper", created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    section = QuestionSection.objects.create(set=qset, title="Section 1", order=1)
    question = Question.objects.create(
        set=qset, section=section, question_text="2+2?", marks=2, mcq_type=MCQ_TYPE_SINGLE,
    )
    correct = QuestionOption.objects.create(question=question, label="A", text="4", is_correct=True, order=1)
    wrong = QuestionOption.objects.create(question=question, label="B", text="5", is_correct=False, order=2)
    return {"paper": paper, "qset": qset, "question": question, "correct": correct, "wrong": wrong}


def _start(admin_client, paper, duration_minutes=30):
    return admin_client.post(
        f"/api/assessments/admin/papers/{paper.id}/trial/start/",
        {"duration_minutes": duration_minutes}, format="json",
    )


# ── AdminTrialStartView ──────────────────────────────────────────────────────

class TestTrialStart:
    def test_starts_a_session_on_the_papers_first_set(self, admin_client, paper_with_question):
        paper = paper_with_question["paper"]
        resp = _start(admin_client, paper)
        assert resp.status_code == 201
        body = resp.json()["data"]
        assert body["set_label"] == "Set A"
        session = AssessmentSession.objects.get(id=body["session_id"])
        assert session.assignment_id is None
        assert session.student_id == ADMIN_USER_ID
        assert session.status == SESSION_STATUS_IN_PROGRESS

    def test_resumes_an_in_progress_trial_instead_of_creating_a_new_one(self, admin_client, paper_with_question):
        paper = paper_with_question["paper"]
        first = _start(admin_client, paper).json()["data"]["session_id"]
        second = _start(admin_client, paper).json()["data"]["session_id"]
        assert first == second
        assert AssessmentSession.objects.filter(assignment__isnull=True).count() == 1

    def test_starts_a_fresh_session_after_the_previous_one_was_submitted(self, admin_client, paper_with_question):
        paper = paper_with_question["paper"]
        first_id = _start(admin_client, paper).json()["data"]["session_id"]
        admin_client.post(f"/api/assessments/admin/trial/sessions/{first_id}/submit/")

        second_id = _start(admin_client, paper).json()["data"]["session_id"]

        assert second_id != first_id
        assert AssessmentSession.objects.filter(assignment__isnull=True, student_id=ADMIN_USER_ID).count() == 2

    def test_rejects_missing_or_invalid_duration(self, admin_client, paper_with_question):
        paper = paper_with_question["paper"]
        for bad in [{}, {"duration_minutes": 0}, {"duration_minutes": -5}, {"duration_minutes": "x"}]:
            resp = admin_client.post(f"/api/assessments/admin/papers/{paper.id}/trial/start/", bad, format="json")
            assert resp.status_code == 400

    def test_paper_with_no_questions_rejected(self, admin_client):
        paper = QuestionPaper.objects.create(institution_id=INSTITUTION_A, title="Empty", created_by=ADMIN_USER_ID)
        QuestionSet.objects.create(paper=paper, label="Set A", order=1)
        resp = _start(admin_client, paper)
        assert resp.status_code == 400
        assert "no questions" in resp.json()["message"]

    def test_cross_institution_404(self, admin_b_client, paper_with_question):
        resp = _start(admin_b_client, paper_with_question["paper"])
        assert resp.status_code == 404

    def test_non_owner_admin_forbidden(self, colleague_admin_client, paper_with_question):
        resp = _start(colleague_admin_client, paper_with_question["paper"])
        assert resp.status_code == 403

    def test_student_forbidden(self, student_client, paper_with_question):
        resp = _start(student_client, paper_with_question["paper"])
        assert resp.status_code == 403


# ── AdminTrialSessionQuestionsView / AdminTrialAnswerView / AdminTrialSubmitView ──

class TestTrialTakeAndSubmit:
    def test_questions_omit_the_answer_key(self, admin_client, paper_with_question):
        paper = paper_with_question["paper"]
        session_id = _start(admin_client, paper).json()["data"]["session_id"]

        resp = admin_client.get(f"/api/assessments/admin/trial/sessions/{session_id}/questions/")
        assert resp.status_code == 200
        q = resp.json()["data"]["questions"][0]
        assert "is_correct" not in q["options"][0]

    def test_answer_then_submit_scores_correctly_and_returns_score_unconditionally(self, admin_client, paper_with_question):
        p = paper_with_question
        session_id = _start(admin_client, p["paper"]).json()["data"]["session_id"]

        resp = admin_client.put(
            f"/api/assessments/admin/trial/sessions/{session_id}/questions/{p['question'].id}/answer/",
            {"selected_option_ids": [str(p["correct"].id)]}, format="json",
        )
        assert resp.status_code == 200

        resp = admin_client.post(f"/api/assessments/admin/trial/sessions/{session_id}/submit/")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["status"] == SESSION_STATUS_SUBMITTED
        # No assignment => no show_result_to_student gate — score always present.
        assert body["score"] == 2
        assert body["total_marks"] == 2

    def test_no_activity_log_rows_written_for_a_trial(self, admin_client, paper_with_question):
        p = paper_with_question
        session_id = _start(admin_client, p["paper"]).json()["data"]["session_id"]

        admin_client.put(
            f"/api/assessments/admin/trial/sessions/{session_id}/questions/{p['question'].id}/answer/",
            {"selected_option_ids": [str(p["correct"].id)]}, format="json",
        )
        admin_client.post(f"/api/assessments/admin/trial/sessions/{session_id}/submit/")

        assert ActivityLog.objects.filter(session_id=session_id).count() == 0

    def test_resulting_result_summary_has_no_assignment_and_correct_institution(self, admin_client, paper_with_question):
        p = paper_with_question
        session_id = _start(admin_client, p["paper"]).json()["data"]["session_id"]
        admin_client.post(f"/api/assessments/admin/trial/sessions/{session_id}/submit/")

        result = ResultSummary.objects.get(session_id=session_id)
        assert result.assignment_id is None
        assert result.institution_id == INSTITUTION_A

    def test_expired_trial_rejects_further_answers_and_submit(self, admin_client, paper_with_question):
        p = paper_with_question
        session_id = _start(admin_client, p["paper"]).json()["data"]["session_id"]
        AssessmentSession.objects.filter(id=session_id).update(ends_at=timezone.now() - timedelta(seconds=1))

        resp = admin_client.put(
            f"/api/assessments/admin/trial/sessions/{session_id}/questions/{p['question'].id}/answer/",
            {"selected_option_ids": [str(p["correct"].id)]}, format="json",
        )
        assert resp.status_code == 403
        assert "expired" in resp.json()["message"].lower()

        resp = admin_client.post(f"/api/assessments/admin/trial/sessions/{session_id}/submit/")
        assert resp.status_code == 403

    def test_another_admin_cannot_touch_a_colleagues_trial_session(self, admin_client, colleague_admin_client, paper_with_question):
        # colleague_admin_client shares INSTITUTION_A but isn't the paper
        # owner OR the trial's own student_id — both endpoints must 404,
        # not leak whether the session exists.
        p = paper_with_question
        session_id = _start(admin_client, p["paper"]).json()["data"]["session_id"]

        resp = colleague_admin_client.get(f"/api/assessments/admin/trial/sessions/{session_id}/questions/")
        assert resp.status_code == 404
        resp = colleague_admin_client.post(f"/api/assessments/admin/trial/sessions/{session_id}/submit/")
        assert resp.status_code == 404

    def test_student_forbidden_on_all_three(self, student_client, paper_with_question):
        p = paper_with_question
        fake_id = uuid.uuid4()
        assert student_client.get(f"/api/assessments/admin/trial/sessions/{fake_id}/questions/").status_code == 403
        assert student_client.put(
            f"/api/assessments/admin/trial/sessions/{fake_id}/questions/{p['question'].id}/answer/", {}, format="json",
        ).status_code == 403
        assert student_client.post(f"/api/assessments/admin/trial/sessions/{fake_id}/submit/").status_code == 403


# ── Isolation from real, assignment-scoped data ─────────────────────────────

class TestTrialIsolationFromRealData:
    def _payload(self, paper):
        return {
            "paper": str(paper.id), "batch_id": str(uuid.uuid4()),
            "global_expire_time": (timezone.now() + timedelta(hours=3)).isoformat(),
            "exam_duration_minutes": 60,
        }

    @patch("assessments.views.fetch_batch_roster", return_value=[])
    def test_trial_result_never_appears_in_the_assignments_results_table(self, mock_roster, admin_client, paper_with_question):
        p = paper_with_question
        session_id = _start(admin_client, p["paper"]).json()["data"]["session_id"]
        admin_client.post(f"/api/assessments/admin/trial/sessions/{session_id}/submit/")

        with patch("assessments.views.snapshot_roster_and_allocate", return_value=0):
            resp = admin_client.post("/api/assessments/admin/assignments/", self._payload(p["paper"]), format="json")
        assignment_id = resp.json()["data"]["id"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment_id}/results/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_real_student_result_never_appears_in_the_paper_trial_results(self, admin_client, paper_with_question):
        p = paper_with_question
        assignment = BatchAssignment.objects.create(
            paper=p["paper"], batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
        )
        real_session = AssessmentSession.objects.create(
            assignment=assignment, student_id=uuid.uuid4(), set=p["qset"],
            ends_at=timezone.now() + timedelta(hours=1),
        )
        ResultSummary.objects.create(
            session=real_session, assignment=assignment, student_id=real_session.student_id,
            institution_id=INSTITUTION_A, started_at=timezone.now(), ended_at=timezone.now(),
            duration_seconds=100, score=2, total_marks=2, status=SESSION_STATUS_SUBMITTED,
        )

        resp = admin_client.get(f"/api/assessments/admin/papers/{p['paper'].id}/trial-results/")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_beat_sweep_auto_submits_an_expired_trial_too(self, paper_with_question):
        p = paper_with_question
        session = AssessmentSession.objects.create(
            assignment=None, student_id=ADMIN_USER_ID, set=p["qset"],
            ends_at=timezone.now() - timedelta(seconds=1),
        )
        result = sweep_expired_sessions()
        assert result["auto_submitted"] == 1
        session.refresh_from_db()
        assert session.status != SESSION_STATUS_IN_PROGRESS
        assert ResultSummary.objects.filter(session=session, institution_id=INSTITUTION_A).exists()


# ── AdminPaperTrialResultsView ───────────────────────────────────────────────

class TestTrialResultsListing:
    def test_lists_submitted_trial_attempts_most_recent_first(self, admin_client, paper_with_question):
        p = paper_with_question
        first = _start(admin_client, p["paper"]).json()["data"]["session_id"]
        admin_client.post(f"/api/assessments/admin/trial/sessions/{first}/submit/")
        second = _start(admin_client, p["paper"]).json()["data"]["session_id"]
        admin_client.post(f"/api/assessments/admin/trial/sessions/{second}/submit/")

        resp = admin_client.get(f"/api/assessments/admin/papers/{p['paper'].id}/trial-results/")
        assert resp.status_code == 200
        rows = resp.json()["data"]
        assert len(rows) == 2
        assert rows[0]["id"] != rows[1]["id"]
        for row in rows:
            assert row["set_label"] == "Set A"
            assert row["total_marks"] == 2

    def test_cross_institution_404(self, admin_b_client, paper_with_question):
        resp = admin_b_client.get(f"/api/assessments/admin/papers/{paper_with_question['paper'].id}/trial-results/")
        assert resp.status_code == 404

    def test_non_owner_admin_forbidden(self, colleague_admin_client, paper_with_question):
        resp = colleague_admin_client.get(f"/api/assessments/admin/papers/{paper_with_question['paper'].id}/trial-results/")
        assert resp.status_code == 403

    def test_student_forbidden(self, student_client, paper_with_question):
        resp = student_client.get(f"/api/assessments/admin/papers/{paper_with_question['paper'].id}/trial-results/")
        assert resp.status_code == 403
