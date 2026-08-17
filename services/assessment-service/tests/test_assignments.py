import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, Question, QuestionOption, BatchAssignment, AssessmentSession,
    ASSIGNMENT_STATUS_SCHEDULED, ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_CLOSED,
)

from .conftest import INSTITUTION_A, INSTITUTION_B, ADMIN_USER_ID, STUDENT_USER_ID


@pytest.fixture
def published_paper(db):
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Assign Test Paper",
        created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    q = Question.objects.create(set=qset, question_text="2+2?", marks=1)
    QuestionOption.objects.create(question=q, label="A", text="4", is_correct=True, order=1)
    QuestionOption.objects.create(question=q, label="B", text="5", order=2)
    return paper


@pytest.fixture
def paper_with_empty_set(db):
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Empty Set Paper", created_by=ADMIN_USER_ID,
    )
    QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    return paper


@pytest.fixture
def paper_no_sets(db):
    return QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="No Sets Paper",
        created_by=ADMIN_USER_ID,
    )


def _payload(paper, **overrides):
    data = {
        "paper": str(paper.id),
        "batch_id": str(uuid.uuid4()),
        "global_expire_time": (timezone.now() + timedelta(hours=3)).isoformat(),
        "exam_duration_minutes": 60,
    }
    data.update(overrides)
    return data


# ── Creation ─────────────────────────────────────────────────────────────────

class TestCreateAssignment:
    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_creates_assignment_scheduled_by_default(self, mock_snap, admin_client, published_paper):
        mock_snap.return_value = 0
        resp = admin_client.post("/api/assessments/admin/assignments/", _payload(published_paper), format="json")
        assert resp.status_code == 201
        body = resp.json()["data"]
        assert body["status"] == ASSIGNMENT_STATUS_SCHEDULED
        assert body["pass_cutoff_percentage"] == 40  # default
        mock_snap.assert_called_once()

    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_departments_defaults_to_empty_list_when_omitted(self, mock_snap, admin_client, published_paper):
        mock_snap.return_value = 0
        resp = admin_client.post("/api/assessments/admin/assignments/", _payload(published_paper), format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["departments"] == []

    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_departments_accepted_and_stored(self, mock_snap, admin_client, published_paper):
        mock_snap.return_value = 0
        payload = _payload(published_paper, departments=["CSE", "CSD"])
        resp = admin_client.post("/api/assessments/admin/assignments/", payload, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["departments"] == ["CSE", "CSD"]
        assignment = BatchAssignment.objects.get(pk=resp.json()["data"]["id"])
        assert assignment.departments == ["CSE", "CSD"]

    def test_departments_rejects_non_list(self, admin_client, published_paper):
        payload = _payload(published_paper, departments="CSE")  # string, not a list
        resp = admin_client.post("/api/assessments/admin/assignments/", payload, format="json")
        assert resp.status_code == 400

    def test_departments_rejects_non_string_entries(self, admin_client, published_paper):
        payload = _payload(published_paper, departments=[123])
        resp = admin_client.post("/api/assessments/admin/assignments/", payload, format="json")
        assert resp.status_code == 400

    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_roster_failure_rolls_back_whole_assignment(self, mock_snap, admin_client, published_paper):
        mock_snap.side_effect = RuntimeError("user-service unreachable")
        resp = admin_client.post("/api/assessments/admin/assignments/", _payload(published_paper), format="json")
        assert resp.status_code == 502
        assert BatchAssignment.objects.filter(paper=published_paper).count() == 0

    def test_paper_with_no_sets_rejected(self, admin_client, paper_no_sets):
        resp = admin_client.post("/api/assessments/admin/assignments/", _payload(paper_no_sets), format="json")
        assert resp.status_code == 400

    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_expire_before_start_rejected(self, mock_snap, admin_client, published_paper):
        now = timezone.now()
        payload = _payload(
            published_paper,
            global_start_time=(now + timedelta(hours=2)).isoformat(),
            global_expire_time=(now + timedelta(hours=1)).isoformat(),
        )
        resp = admin_client.post("/api/assessments/admin/assignments/", payload, format="json")
        assert resp.status_code == 400
        mock_snap.assert_not_called()

    def test_cross_institution_paper_404s(self, admin_b_client, published_paper):
        resp = admin_b_client.post("/api/assessments/admin/assignments/", _payload(published_paper), format="json")
        assert resp.status_code == 404

    def test_non_admin_forbidden(self, student_client, published_paper):
        resp = student_client.post("/api/assessments/admin/assignments/", _payload(published_paper), format="json")
        assert resp.status_code == 403


# ── Assignment-readiness checks (moved here from publish/, 2026-08-14) ─────
# publish/unpublish no longer gates anything — every one of these used to be
# a publish-time-only check (some just a warning, not even a hard block);
# now they're all enforced at assignment-creation time instead, since
# "assign" is the sole readiness gate left in the admin workflow.

class TestAssignmentReadinessChecks:
    def _paper_with_sets(self, set_specs):
        """set_specs: list of lists of (marks, mcq_type, correct_count) per question."""
        from assessments.models import MCQ_TYPE_MULTIPLE
        paper = QuestionPaper.objects.create(
            institution_id=INSTITUTION_A, title="Readiness Test Paper", created_by=ADMIN_USER_ID,
        )
        for i, questions in enumerate(set_specs):
            qset = QuestionSet.objects.create(paper=paper, label=f"Set {chr(65+i)}", order=i + 1)
            for j, (marks, mcq_type, correct_count) in enumerate(questions):
                q = Question.objects.create(set=qset, question_text=f"Q{j}?", marks=marks, mcq_type=mcq_type)
                QuestionOption.objects.create(question=q, label="A", text="opt A", is_correct=correct_count >= 1, order=1)
                QuestionOption.objects.create(question=q, label="B", text="opt B", is_correct=correct_count >= 2, order=2)
        return paper

    def test_unequal_question_counts_across_sets_rejected(self, admin_client):
        from assessments.models import MCQ_TYPE_SINGLE
        paper = self._paper_with_sets([
            [(1, MCQ_TYPE_SINGLE, 1)],
            [(1, MCQ_TYPE_SINGLE, 1), (1, MCQ_TYPE_SINGLE, 1)],
        ])
        resp = admin_client.post("/api/assessments/admin/assignments/", _payload(paper), format="json")
        assert resp.status_code == 400
        assert "unequal question counts" in resp.json()["message"]

    def test_unequal_marks_across_sets_rejected(self, admin_client):
        from assessments.models import MCQ_TYPE_SINGLE
        paper = self._paper_with_sets([
            [(1, MCQ_TYPE_SINGLE, 1)],
            [(2, MCQ_TYPE_SINGLE, 1)],
        ])
        resp = admin_client.post("/api/assessments/admin/assignments/", _payload(paper), format="json")
        assert resp.status_code == 400
        assert "unequal total marks" in resp.json()["message"]

    def test_multiple_correct_question_with_only_one_correct_rejected(self, admin_client):
        from assessments.models import MCQ_TYPE_MULTIPLE
        paper = self._paper_with_sets([[(1, MCQ_TYPE_MULTIPLE, 1)]])
        resp = admin_client.post("/api/assessments/admin/assignments/", _payload(paper), format="json")
        assert resp.status_code == 400
        assert "more than one correct option" in resp.json()["message"]

    def test_multiple_correct_question_with_two_correct_accepted(self, admin_client):
        from assessments.models import MCQ_TYPE_MULTIPLE
        paper = self._paper_with_sets([[(1, MCQ_TYPE_MULTIPLE, 2)]])
        with patch("assessments.views.snapshot_roster_and_allocate", return_value=0):
            resp = admin_client.post("/api/assessments/admin/assignments/", _payload(paper), format="json")
        assert resp.status_code == 201

    def test_set_with_no_questions_rejected(self, admin_client):
        paper = QuestionPaper.objects.create(
            institution_id=INSTITUTION_A, title="Empty Set Paper", created_by=ADMIN_USER_ID,
        )
        QuestionSet.objects.create(paper=paper, label="Set A", order=1)
        resp = admin_client.post("/api/assessments/admin/assignments/", _payload(paper), format="json")
        assert resp.status_code == 400
        assert "has no questions" in resp.json()["message"]

    def test_equal_sets_with_valid_questions_accepted(self, admin_client, paper_with_empty_set):
        # paper_with_empty_set's single set has zero questions, so give it
        # one valid question first, then confirm readiness only cares about
        # real content (question count/options/correct-answer rules).
        from assessments.models import MCQ_TYPE_SINGLE
        qset = paper_with_empty_set.sets.first()
        q = Question.objects.create(set=qset, question_text="2+2?", marks=1, mcq_type=MCQ_TYPE_SINGLE)
        QuestionOption.objects.create(question=q, label="A", text="4", is_correct=True, order=1)
        QuestionOption.objects.create(question=q, label="B", text="5", is_correct=False, order=2)
        with patch("assessments.views.snapshot_roster_and_allocate", return_value=0):
            resp = admin_client.post("/api/assessments/admin/assignments/", _payload(paper_with_empty_set), format="json")
        assert resp.status_code == 201


# ── Immutability lock (completes Task 2.2's stub) ───────────────────────────

class TestImmutabilityLock:
    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_paper_locks_once_assigned(self, mock_snap, admin_client, published_paper):
        mock_snap.return_value = 0
        assert published_paper.is_locked() is False
        admin_client.post("/api/assessments/admin/assignments/", _payload(published_paper), format="json")
        published_paper.refresh_from_db()
        assert published_paper.is_locked() is True

    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_locked_paper_rejects_question_edits(self, mock_snap, admin_client, published_paper):
        mock_snap.return_value = 0
        admin_client.post("/api/assessments/admin/assignments/", _payload(published_paper), format="json")
        question = published_paper.sets.first().questions.first()
        resp = admin_client.patch(
            f"/api/assessments/admin/questions/{question.id}/",
            {"question_text": "changed"}, format="json",
        )
        assert resp.status_code == 403
        question.refresh_from_db()
        assert question.question_text == "2+2?"


# ── Start ────────────────────────────────────────────────────────────────────

class TestStartAssignment:
    def _create_direct(self, paper, **overrides):
        return BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, **overrides,
        )

    def test_start_transitions_scheduled_to_live(self, admin_client, published_paper):
        assignment = self._create_direct(published_paper)
        resp = admin_client.patch(f"/api/assessments/admin/assignments/{assignment.id}/start/")
        assert resp.status_code == 200
        assignment.refresh_from_db()
        assert assignment.status == ASSIGNMENT_STATUS_LIVE
        assert assignment.global_start_time is not None

    def test_start_succeeds_without_rechecking_paper_readiness(self, admin_client, paper_with_empty_set):
        # Readiness (content completeness, correct-answer counts) is checked
        # once, at assignment-creation time (get_assignment_readiness_blockers)
        # — Start must not re-run it. This directly created assignment
        # bypasses that create-time check (as _create_direct always has),
        # using a paper whose set has no questions, to prove Start doesn't
        # care about paper content at all.
        assignment = self._create_direct(paper_with_empty_set)
        resp = admin_client.patch(f"/api/assessments/admin/assignments/{assignment.id}/start/")
        assert resp.status_code == 200
        assignment.refresh_from_db()
        assert assignment.status == ASSIGNMENT_STATUS_LIVE

    def test_start_twice_is_noop_not_error(self, admin_client, published_paper):
        assignment = self._create_direct(published_paper)
        first = admin_client.patch(f"/api/assessments/admin/assignments/{assignment.id}/start/")
        second = admin_client.patch(f"/api/assessments/admin/assignments/{assignment.id}/start/")
        assert first.status_code == 200
        assert second.status_code == 200
        assignment.refresh_from_db()
        assert assignment.status == ASSIGNMENT_STATUS_LIVE

    def test_start_closed_assignment_rejected(self, admin_client, published_paper):
        assignment = self._create_direct(published_paper, status=ASSIGNMENT_STATUS_CLOSED)
        resp = admin_client.patch(f"/api/assessments/admin/assignments/{assignment.id}/start/")
        assert resp.status_code == 409

    def test_non_admin_forbidden(self, student_client, published_paper):
        assignment = self._create_direct(published_paper)
        resp = student_client.patch(f"/api/assessments/admin/assignments/{assignment.id}/start/")
        assert resp.status_code == 403

    def test_cross_institution_404(self, admin_b_client, published_paper):
        assignment = self._create_direct(published_paper)
        resp = admin_b_client.patch(f"/api/assessments/admin/assignments/{assignment.id}/start/")
        assert resp.status_code == 404
        assignment.refresh_from_db()
        assert assignment.status == ASSIGNMENT_STATUS_SCHEDULED

    def test_preexisting_start_time_preserved(self, admin_client, published_paper):
        preset = timezone.now() + timedelta(minutes=30)
        assignment = self._create_direct(published_paper, global_start_time=preset)
        admin_client.patch(f"/api/assessments/admin/assignments/{assignment.id}/start/")
        assignment.refresh_from_db()
        assert abs((assignment.global_start_time - preset).total_seconds()) < 1


# ── Close ────────────────────────────────────────────────────────────────────

class TestCloseAssignment:
    def _create_direct(self, paper, **overrides):
        return BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, **overrides,
        )

    def test_close_before_any_session_exists(self, admin_client, published_paper):
        assignment = self._create_direct(published_paper, status=ASSIGNMENT_STATUS_LIVE)
        resp = admin_client.patch(f"/api/assessments/admin/assignments/{assignment.id}/close/")
        assert resp.status_code == 200
        assignment.refresh_from_db()
        assert assignment.status == ASSIGNMENT_STATUS_CLOSED

    def test_close_is_idempotent(self, admin_client, published_paper):
        assignment = self._create_direct(published_paper, status=ASSIGNMENT_STATUS_CLOSED)
        resp = admin_client.patch(f"/api/assessments/admin/assignments/{assignment.id}/close/")
        assert resp.status_code == 200
        assignment.refresh_from_db()
        assert assignment.status == ASSIGNMENT_STATUS_CLOSED

    def test_cross_institution_404(self, admin_b_client, published_paper):
        assignment = self._create_direct(published_paper, status=ASSIGNMENT_STATUS_LIVE)
        resp = admin_b_client.patch(f"/api/assessments/admin/assignments/{assignment.id}/close/")
        assert resp.status_code == 404
        assignment.refresh_from_db()
        assert assignment.status == ASSIGNMENT_STATUS_LIVE

    def test_non_admin_forbidden(self, student_client, published_paper):
        assignment = self._create_direct(published_paper, status=ASSIGNMENT_STATUS_LIVE)
        resp = student_client.patch(f"/api/assessments/admin/assignments/{assignment.id}/close/")
        assert resp.status_code == 403


# ── Resync roster ────────────────────────────────────────────────────────────

class TestResyncRoster:
    def _create_direct(self, paper):
        return BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID,
        )

    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_resync_returns_new_allocation_count(self, mock_snap, admin_client, published_paper):
        mock_snap.return_value = 3
        assignment = self._create_direct(published_paper)
        resp = admin_client.post(f"/api/assessments/admin/assignments/{assignment.id}/resync-roster/")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_allocations"] == 3

    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_resync_failure_returns_502(self, mock_snap, admin_client, published_paper):
        mock_snap.side_effect = RuntimeError("unreachable")
        assignment = self._create_direct(published_paper)
        resp = admin_client.post(f"/api/assessments/admin/assignments/{assignment.id}/resync-roster/")
        assert resp.status_code == 502

    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_cross_institution_404(self, mock_snap, admin_b_client, published_paper):
        assignment = self._create_direct(published_paper)
        resp = admin_b_client.post(f"/api/assessments/admin/assignments/{assignment.id}/resync-roster/")
        assert resp.status_code == 404
        mock_snap.assert_not_called()

    def test_non_admin_forbidden(self, student_client, published_paper):
        assignment = self._create_direct(published_paper)
        resp = student_client.post(f"/api/assessments/admin/assignments/{assignment.id}/resync-roster/")
        assert resp.status_code == 403


# ── Extend stub ──────────────────────────────────────────────────────────────

class TestExtendSessionStub:
    def _create_direct(self, paper):
        return BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID,
        )

    def test_valid_assignment_but_no_session_yet_returns_clean_404(self, admin_client, published_paper):
        assignment = self._create_direct(published_paper)
        resp = admin_client.patch(
            f"/api/assessments/admin/assignments/{assignment.id}/sessions/{uuid.uuid4()}/extend/"
        )
        assert resp.status_code == 404

    def test_assignment_not_owned_by_admin_404s(self, admin_b_client, published_paper):
        assignment = self._create_direct(published_paper)
        resp = admin_b_client.patch(
            f"/api/assessments/admin/assignments/{assignment.id}/sessions/{uuid.uuid4()}/extend/"
        )
        assert resp.status_code == 404

    def test_non_admin_forbidden(self, student_client, published_paper):
        assignment = self._create_direct(published_paper)
        resp = student_client.patch(
            f"/api/assessments/admin/assignments/{assignment.id}/sessions/{uuid.uuid4()}/extend/"
        )
        assert resp.status_code == 403

    def test_extend_minutes_over_cap_rejected_cleanly(self, admin_client, published_paper):
        # Task 12.2's abuse-hardening audit: an unbounded extend_minutes
        # used to crash this endpoint with an unhandled OverflowError
        # ("date value out of range") once ends_at + timedelta(minutes=...)
        # exceeded datetime's representable range — this must be a clean
        # 400, not a 500.
        assignment = self._create_direct(published_paper)
        original_ends_at = timezone.now() + timedelta(hours=1)
        session = AssessmentSession.objects.create(
            assignment=assignment, student_id=STUDENT_USER_ID, set=published_paper.sets.first(),
            ends_at=original_ends_at,
        )
        resp = admin_client.patch(
            f"/api/assessments/admin/assignments/{assignment.id}/sessions/{session.id}/extend/",
            {"extend_minutes": 999999999999}, format="json",
        )
        assert resp.status_code == 400
        session.refresh_from_db()
        assert abs((session.ends_at - original_ends_at).total_seconds()) < 5

    def test_extend_minutes_within_cap_succeeds(self, admin_client, published_paper):
        assignment = self._create_direct(published_paper)
        original_ends_at = timezone.now() + timedelta(hours=1)
        session = AssessmentSession.objects.create(
            assignment=assignment, student_id=STUDENT_USER_ID, set=published_paper.sets.first(),
            ends_at=original_ends_at,
        )
        resp = admin_client.patch(
            f"/api/assessments/admin/assignments/{assignment.id}/sessions/{session.id}/extend/",
            {"extend_minutes": 30}, format="json",
        )
        assert resp.status_code == 200
        session.refresh_from_db()
        assert abs((session.ends_at - (original_ends_at + timedelta(minutes=30))).total_seconds()) < 5


# ── Status ───────────────────────────────────────────────────────────────────

class TestAssignmentStatus:
    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_status_before_any_session_exists(self, mock_snap, admin_client, published_paper):
        mock_snap.return_value = 7
        resp = admin_client.post("/api/assessments/admin/assignments/", _payload(published_paper), format="json")
        assignment_id = resp.json()["data"]["id"]

        status_resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment_id}/status/")
        assert status_resp.status_code == 200
        body = status_resp.json()["data"]
        assert body["status"] == ASSIGNMENT_STATUS_SCHEDULED
        # student_count_completed is now populated (Task 5.1) — 0 since no
        # AssessmentSession exists yet for this brand-new assignment.
        assert body["student_count_completed"] == 0

    def test_cross_institution_404(self, admin_b_client, published_paper):
        assignment = BatchAssignment.objects.create(
            paper=published_paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID,
        )
        resp = admin_b_client.get(f"/api/assessments/admin/assignments/{assignment.id}/status/")
        assert resp.status_code == 404

    def test_non_admin_forbidden(self, student_client, published_paper):
        assignment = BatchAssignment.objects.create(
            paper=published_paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID,
        )
        resp = student_client.get(f"/api/assessments/admin/assignments/{assignment.id}/status/")
        assert resp.status_code == 403


# ── List & detail (previously untested — Task 12.1's audit) ──────────────────

class TestAssignmentListAndDetail:
    def _create_direct(self, paper, institution_id=INSTITUTION_A):
        return BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=institution_id,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID,
        )

    def test_list_excludes_other_institutions_assignments(self, admin_b_client, published_paper):
        assignment = self._create_direct(published_paper)
        resp = admin_b_client.get("/api/assessments/admin/assignments/")
        assert resp.status_code == 200
        ids = [a["id"] for a in resp.json()["results"]]
        assert str(assignment.id) not in ids

    def test_list_non_admin_forbidden(self, student_client):
        resp = student_client.get("/api/assessments/admin/assignments/")
        assert resp.status_code == 403

    def test_detail_cross_institution_404(self, admin_b_client, published_paper):
        assignment = self._create_direct(published_paper)
        resp = admin_b_client.get(f"/api/assessments/admin/assignments/{assignment.id}/")
        assert resp.status_code == 404

    def test_detail_non_admin_forbidden(self, student_client, published_paper):
        assignment = self._create_direct(published_paper)
        resp = student_client.get(f"/api/assessments/admin/assignments/{assignment.id}/")
        assert resp.status_code == 403

    def test_detail_own_institution_succeeds(self, admin_client, published_paper):
        assignment = self._create_direct(published_paper)
        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == str(assignment.id)
