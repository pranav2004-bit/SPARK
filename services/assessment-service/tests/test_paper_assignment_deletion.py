"""Tests for the paper-content-deletion + assignment-deletion feature
(2026-11-13, user decision) — see docs/assessment-service-api.md's
"Content deletion" sections for the full behavior this covers.

Three concerns, each with its own test class:
  1. Assignment delete itself (LIVE blocked / SCHEDULED hard-deleted /
     CLOSED archived) and the Assign-list archiving toggle.
  2. Paper content delete itself (eligibility, what's erased vs. frozen,
     S3 cleanup scheduling, idempotency).
  3. The user's own core requirement, verified directly rather than
     assumed: Results/Analytics/the Mock-Tests tab produce byte-identical
     output before and after a paper's content is deleted.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, QuestionSection, Question, QuestionOption,
    BatchAssignment, StudentSetAllocation, AssessmentSession, AssessmentResponse, ResultSummary,
    ASSIGNMENT_STATUS_SCHEDULED, ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_CLOSED,
    SESSION_STATUS_SUBMITTED, SESSION_STATUS_IN_PROGRESS,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID


def _roster_entry(user_id, department="CSE"):
    return {"user_id": str(user_id), "student_id": "ROLL-001", "fullname": "Student", "department": department}


@pytest.fixture
def paper_with_two_sets(db):
    """A paper with two sets, each one question/two options — the smallest
    shape AdminPaperDetailView.delete() still has real content, image
    keys, and a cross-set comparison to erase/freeze."""
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Deletable Paper", description="desc",
        created_by=ADMIN_USER_ID,
    )
    set_a = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    set_b = QuestionSet.objects.create(paper=paper, label="Set B", order=2)
    sec_a = QuestionSection.objects.create(set=set_a, title="Section 1", order=1)
    sec_b = QuestionSection.objects.create(set=set_b, title="Section 1", order=1)
    q_a = Question.objects.create(set=set_a, section=sec_a, question_text="A1", marks=5, question_image_key="uploads/question/a1.png")
    QuestionOption.objects.create(question=q_a, label="A", text="right", is_correct=True, order=1, image_key="uploads/option/a1opt.png")
    QuestionOption.objects.create(question=q_a, label="B", text="wrong", order=2)
    q_b = Question.objects.create(set=set_b, section=sec_b, question_text="B1", marks=5)
    QuestionOption.objects.create(question=q_b, label="A", text="right", is_correct=True, order=1)
    QuestionOption.objects.create(question=q_b, label="B", text="wrong", order=2)
    return {"paper": paper, "set_a": set_a, "set_b": set_b, "q_a": q_a, "q_b": q_b}


def _make_closed_assignment_with_results(paper_bundle):
    """A CLOSED assignment with one real submitted session + result on
    Set A — the shape every "zero impact after deletion" test needs: real
    AssessmentResponse/ResultSummary rows that PROTECT survival."""
    paper, set_a, q_a = paper_bundle["paper"], paper_bundle["set_a"], paper_bundle["q_a"]
    assignment = BatchAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_start_time=timezone.now() - timedelta(hours=2),
        global_expire_time=timezone.now() - timedelta(hours=1),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_CLOSED,
    )
    student_id = uuid.uuid4()
    StudentSetAllocation.objects.create(
        assignment=assignment, student_id=student_id, set=set_a, set_label_snapshot=set_a.label,
    )
    session = AssessmentSession.objects.create(
        assignment=assignment, student_id=student_id, set=set_a, set_label_snapshot=set_a.label, paper=paper,
        ends_at=timezone.now() - timedelta(minutes=30), status=SESSION_STATUS_SUBMITTED,
        started_at=timezone.now() - timedelta(hours=1),
    )
    opt_correct = q_a.options.get(is_correct=True)
    AssessmentResponse.objects.create(
        session=session, question=q_a, selected_option_ids=[str(opt_correct.id)],
        is_correct=True, marks_awarded=5,
    )
    ResultSummary.objects.create(
        session=session, assignment=assignment, student_id=student_id, institution_id=INSTITUTION_A,
        started_at=session.started_at, ended_at=timezone.now(), duration_seconds=1800,
        score=5, total_marks=5, status=SESSION_STATUS_SUBMITTED,
        malpractice_flag=False, malpractice_reasons=[],
    )
    return assignment, session, student_id


# ── Assignment delete ────────────────────────────────────────────────────────

class TestAssignmentDelete:
    def _assignment(self, status, **overrides):
        paper = QuestionPaper.objects.create(
            institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID,
        )
        defaults = dict(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_start_time=timezone.now() - timedelta(hours=1),
            global_expire_time=timezone.now() + timedelta(hours=1),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=status,
        )
        defaults.update(overrides)
        return BatchAssignment.objects.create(**defaults)

    def test_live_assignment_cannot_be_deleted(self, admin_client):
        assignment = self._assignment(ASSIGNMENT_STATUS_LIVE)
        resp = admin_client.delete(f"/api/assessments/admin/assignments/{assignment.id}/")
        assert resp.status_code == 403
        assert BatchAssignment.objects.filter(pk=assignment.pk).exists()

    def test_scheduled_assignment_is_hard_deleted_and_cascades(self, admin_client):
        assignment = self._assignment(ASSIGNMENT_STATUS_SCHEDULED)
        qset = QuestionSet.objects.create(paper=assignment.paper, label="Set A", order=1)
        StudentSetAllocation.objects.create(
            assignment=assignment, student_id=uuid.uuid4(), set=qset, set_label_snapshot="Set A",
        )
        resp = admin_client.delete(f"/api/assessments/admin/assignments/{assignment.id}/")
        assert resp.status_code == 200
        assert not BatchAssignment.objects.filter(pk=assignment.pk).exists()
        assert not StudentSetAllocation.objects.filter(assignment_id=assignment.pk).exists()

    def test_closed_assignment_is_archived_not_hard_deleted(self, admin_client):
        paper_bundle = {
            "paper": QuestionPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID),
        }
        paper_bundle["set_a"] = QuestionSet.objects.create(paper=paper_bundle["paper"], label="Set A", order=1)
        sec = QuestionSection.objects.create(set=paper_bundle["set_a"], title="S1", order=1)
        paper_bundle["q_a"] = Question.objects.create(set=paper_bundle["set_a"], section=sec, question_text="Q1", marks=5)
        QuestionOption.objects.create(question=paper_bundle["q_a"], label="A", text="r", is_correct=True, order=1)
        assignment, session, student_id = _make_closed_assignment_with_results(paper_bundle)

        resp = admin_client.delete(f"/api/assessments/admin/assignments/{assignment.id}/")
        assert resp.status_code == 200

        assignment.refresh_from_db()
        assert assignment.is_deleted is True
        assert assignment.deleted_at is not None
        # The row — and everything PROTECT'd against it — must still exist.
        assert BatchAssignment.objects.filter(pk=assignment.pk).exists()
        assert AssessmentSession.objects.filter(pk=session.pk).exists()
        assert ResultSummary.objects.filter(assignment=assignment).exists()

    def test_already_archived_assignment_returns_409(self, admin_client):
        assignment = self._assignment(ASSIGNMENT_STATUS_CLOSED, is_deleted=True, deleted_at=timezone.now())
        resp = admin_client.delete(f"/api/assessments/admin/assignments/{assignment.id}/")
        assert resp.status_code == 409

    def test_cross_institution_404(self, admin_b_client):
        assignment = self._assignment(ASSIGNMENT_STATUS_CLOSED)
        resp = admin_b_client.delete(f"/api/assessments/admin/assignments/{assignment.id}/")
        assert resp.status_code == 404


class TestAssignmentListArchiving:
    def test_list_excludes_archived_by_default(self, admin_client):
        paper = QuestionPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
        live = BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_start_time=timezone.now() - timedelta(hours=1),
            global_expire_time=timezone.now() + timedelta(hours=1),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_CLOSED,
        )
        archived = BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_start_time=timezone.now() - timedelta(hours=1),
            global_expire_time=timezone.now() + timedelta(hours=1),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_CLOSED,
            is_deleted=True, deleted_at=timezone.now(),
        )
        resp = admin_client.get("/api/assessments/admin/assignments/")
        ids = {row["id"] for row in resp.json()["results"]}
        assert str(live.id) in ids
        assert str(archived.id) not in ids

    def test_include_archived_shows_it(self, admin_client):
        paper = QuestionPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
        archived = BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_start_time=timezone.now() - timedelta(hours=1),
            global_expire_time=timezone.now() + timedelta(hours=1),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_CLOSED,
            is_deleted=True, deleted_at=timezone.now(),
        )
        resp = admin_client.get("/api/assessments/admin/assignments/?include_archived=true")
        ids = {row["id"] for row in resp.json()["results"]}
        assert str(archived.id) in ids


# ── Paper content delete ─────────────────────────────────────────────────────

class TestPaperContentDelete:
    def test_blocked_while_assignment_scheduled(self, admin_client, paper_with_two_sets):
        paper = paper_with_two_sets["paper"]
        BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_start_time=timezone.now() + timedelta(hours=1),
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_SCHEDULED,
        )
        resp = admin_client.delete(f"/api/assessments/admin/papers/{paper.id}/")
        assert resp.status_code == 403
        assert QuestionSet.objects.filter(paper=paper).exists()

    def test_blocked_while_assignment_live(self, admin_client, paper_with_two_sets):
        paper = paper_with_two_sets["paper"]
        BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_start_time=timezone.now() - timedelta(minutes=1),
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
        )
        resp = admin_client.delete(f"/api/assessments/admin/papers/{paper.id}/")
        assert resp.status_code == 403

    def test_blocked_while_trial_session_in_progress(self, admin_client, paper_with_two_sets):
        paper, set_a = paper_with_two_sets["paper"], paper_with_two_sets["set_a"]
        # A trial has no BatchAssignment (assignment=None) — is_content_deletable()
        # must still catch it via its own IN_PROGRESS-session check.
        AssessmentSession.objects.create(
            assignment=None, student_id=ADMIN_USER_ID, set=set_a, set_label_snapshot=set_a.label, paper=paper,
            ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_IN_PROGRESS,
            started_at=timezone.now(),
        )
        resp = admin_client.delete(f"/api/assessments/admin/papers/{paper.id}/")
        assert resp.status_code == 403

    @patch("assessments.views.delete_s3_images_task")
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    def test_erases_content_but_preserves_paper_row(self, mock_on_commit, mock_task, admin_client, paper_with_two_sets):
        paper, set_a, set_b, q_a = (
            paper_with_two_sets["paper"], paper_with_two_sets["set_a"],
            paper_with_two_sets["set_b"], paper_with_two_sets["q_a"],
        )
        resp = admin_client.delete(f"/api/assessments/admin/papers/{paper.id}/")
        assert resp.status_code == 200

        # Content genuinely gone.
        assert not QuestionSet.objects.filter(paper=paper).exists()
        assert not Question.objects.filter(id=q_a.id).exists()
        assert not QuestionOption.objects.filter(question_id=q_a.id).exists()

        # The paper row itself survives, flagged, with its display fields
        # frozen — title/description/created_by/created_at untouched.
        paper.refresh_from_db()
        assert paper.is_deleted is True
        assert paper.deleted_at is not None
        assert paper.deleted_set_count == 2
        assert paper.title == "Deletable Paper"
        assert paper.description == "desc"
        assert paper.created_by == ADMIN_USER_ID

        # Image keys (one on the question, one on an option) were collected
        # and handed to the cleanup task, scheduled via on_commit.
        mock_task.delay.assert_called_once()
        collected = set(mock_task.delay.call_args[0][0])
        assert collected == {"uploads/question/a1.png", "uploads/option/a1opt.png"}

    @patch("assessments.views.delete_s3_images_task")
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    def test_freezes_question_difficulty_snapshot_before_deleting(self, mock_on_commit, mock_task, admin_client, paper_with_two_sets):
        assignment, session, student_id = _make_closed_assignment_with_results(paper_with_two_sets)

        resp = admin_client.delete(f"/api/assessments/admin/papers/{paper_with_two_sets['paper'].id}/")
        assert resp.status_code == 200

        assignment.refresh_from_db()
        assert assignment.question_difficulty_snapshot is not None
        by_qid = {row["question_id"]: row for row in assignment.question_difficulty_snapshot}
        assert by_qid[str(paper_with_two_sets["q_a"].id)]["total_answered"] == 1
        assert by_qid[str(paper_with_two_sets["q_a"].id)]["correct_count"] == 1
        assert by_qid[str(paper_with_two_sets["q_a"].id)]["set_label"] == "Set A"

    @patch("assessments.views.delete_s3_images_task")
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    def test_already_deleted_returns_409(self, mock_on_commit, mock_task, admin_client, paper_with_two_sets):
        paper = paper_with_two_sets["paper"]
        admin_client.delete(f"/api/assessments/admin/papers/{paper.id}/")
        resp = admin_client.delete(f"/api/assessments/admin/papers/{paper.id}/")
        assert resp.status_code == 409

    @patch("assessments.views.delete_s3_images_task")
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    def test_deleted_paper_no_longer_listed_in_question_bank(self, mock_on_commit, mock_task, admin_client, paper_with_two_sets):
        paper = paper_with_two_sets["paper"]
        admin_client.delete(f"/api/assessments/admin/papers/{paper.id}/")
        resp = admin_client.get("/api/assessments/admin/papers/")
        ids = {row["id"] for row in resp.json()["results"]}
        assert str(paper.id) not in ids


# ── Zero impact: the user's own core requirement, verified directly ─────────

class TestZeroImpactAfterPaperDeletion:
    """"the results, dashboards, analytics, past results (in student
    interface) must have zero change before and after the paper is
    deleted" — the user's own words, confirmed multiple times before this
    feature was built. Verified here by literally comparing the same
    endpoint's response before and after a deletion, not by inspecting
    the code and assuming."""

    @patch("assessments.views.delete_s3_images_task")
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    @patch("assessments.views.fetch_batch_roster")
    def test_results_table_identical_before_and_after(self, mock_roster, mock_on_commit, mock_task, admin_client, paper_with_two_sets):
        assignment, session, student_id = _make_closed_assignment_with_results(paper_with_two_sets)
        mock_roster.return_value = [_roster_entry(student_id)]

        before = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/").json()
        resp = admin_client.delete(f"/api/assessments/admin/papers/{paper_with_two_sets['paper'].id}/")
        assert resp.status_code == 200
        after = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/").json()

        assert before == after

    @patch("assessments.views.delete_s3_images_task")
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    @patch("assessments.views.fetch_batch_roster")
    def test_analytics_identical_before_and_after(self, mock_roster, mock_on_commit, mock_task, admin_client, paper_with_two_sets):
        assignment, session, student_id = _make_closed_assignment_with_results(paper_with_two_sets)
        mock_roster.return_value = [_roster_entry(student_id)]

        before = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/").json()
        resp = admin_client.delete(f"/api/assessments/admin/papers/{paper_with_two_sets['paper'].id}/")
        assert resp.status_code == 200
        after = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/").json()

        # generated_at is a fresh timestamp on every (uncached) computation —
        # the one field that's SUPPOSED to differ. Redis is also cleared by
        # the autouse clear_cache fixture between these two calls? No — it
        # isn't, the cache key is per-assignment and the first GET already
        # populated it, so the second GET here is actually served from that
        # same 60s cache and is trivially identical. To genuinely re-derive
        # the numbers (not just hit the cache), clear it explicitly.
        from django.core.cache import cache
        cache.clear()
        after = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/").json()
        before["data"].pop("generated_at", None)
        after["data"].pop("generated_at", None)
        assert before == after

    @patch("assessments.views.delete_s3_images_task")
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    def test_mock_test_tab_survives_trial_results_after_deletion(self, mock_on_commit, mock_task, admin_client, paper_with_two_sets):
        paper, set_a = paper_with_two_sets["paper"], paper_with_two_sets["set_a"]
        trial_student = uuid.uuid4()
        session = AssessmentSession.objects.create(
            assignment=None, student_id=trial_student, set=set_a, set_label_snapshot=set_a.label, paper=paper,
            ends_at=timezone.now() - timedelta(minutes=5), status=SESSION_STATUS_SUBMITTED,
            started_at=timezone.now() - timedelta(minutes=35),
        )
        ResultSummary.objects.create(
            session=session, assignment=None, student_id=trial_student, institution_id=INSTITUTION_A,
            started_at=session.started_at, ended_at=timezone.now(), duration_seconds=1800,
            score=5, total_marks=5, status=SESSION_STATUS_SUBMITTED,
            malpractice_flag=False, malpractice_reasons=[],
        )

        before = admin_client.get(f"/api/assessments/admin/papers/{paper.id}/trial-results/").json()
        assert len(before["data"]) == 1
        assert before["data"][0]["set_label"] == "Set A"

        resp = admin_client.delete(f"/api/assessments/admin/papers/{paper.id}/")
        assert resp.status_code == 200

        after = admin_client.get(f"/api/assessments/admin/papers/{paper.id}/trial-results/").json()
        assert after["data"] == before["data"]


# ── Responses drill-down degrades gracefully ─────────────────────────────────

class TestResponsesDrilldownAfterDeletion:
    @patch("assessments.views.delete_s3_images_task")
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    def test_result_responses_shows_deleted_message(self, mock_on_commit, mock_task, admin_client, paper_with_two_sets):
        assignment, session, student_id = _make_closed_assignment_with_results(paper_with_two_sets)
        result = ResultSummary.objects.get(session=session)

        admin_client.delete(f"/api/assessments/admin/papers/{paper_with_two_sets['paper'].id}/")

        resp = admin_client.get(f"/api/assessments/admin/results/{result.id}/responses/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["paper_deleted"] is True
        assert data["questions"] == []

    @patch("assessments.views.delete_s3_images_task")
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    def test_question_responses_shows_deleted_message(self, mock_on_commit, mock_task, admin_client, paper_with_two_sets):
        assignment, session, student_id = _make_closed_assignment_with_results(paper_with_two_sets)
        question_id = paper_with_two_sets["q_a"].id

        admin_client.delete(f"/api/assessments/admin/papers/{paper_with_two_sets['paper'].id}/")

        resp = admin_client.get(
            f"/api/assessments/admin/assignments/{assignment.id}/questions/{question_id}/responses/"
        )
        assert resp.status_code == 200
        assert resp.json()["paper_deleted"] is True
        assert resp.json()["students"] == []
