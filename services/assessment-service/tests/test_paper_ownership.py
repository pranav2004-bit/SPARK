"""
Faculty-privacy restriction (live user request): a question paper's
contents (sets/questions/options/instructions/images) and the ability to
assign it to a batch are visible-but-inaccessible to any admin other than
the one who created it — the papers *list* stays fully visible to every
admin at the institution (unchanged), only opening/editing/assigning is
gated. A super admin always bypasses the restriction (escape hatch for a
creator's account later being deactivated/deleted). Results, Analytics, and
Dashboard are explicitly NOT part of this restriction — still open to any
admin, per the same decision.
"""
import uuid
from unittest.mock import patch

import pytest
from django.utils import timezone
from datetime import timedelta

from assessments.models import (
    QuestionPaper, QuestionSet, Question, QuestionOption,
    MCQ_TYPE_SINGLE, BatchAssignment,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID

PAPER_OWNERSHIP_DENIED_MSG = "This assessment was created by another admin and can't be accessed by you."


@pytest.fixture
def owned_paper_chain(db):
    """An unlocked, assignment-ready paper → set → question → 2 options,
    created by ADMIN_USER_ID (admin_client). colleague_admin_client is a
    different admin at the same institution and must be denied everywhere
    except the papers list; super_admin_client must always get through."""
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Faculty-Private Paper",
        created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    question = Question.objects.create(
        set=qset, question_text="2+2?", marks=1, mcq_type=MCQ_TYPE_SINGLE,
    )
    opt_a = QuestionOption.objects.create(question=question, label="A", text="4", is_correct=True, order=1)
    QuestionOption.objects.create(question=question, label="B", text="5", is_correct=False, order=2)
    return {"paper": paper, "qset": qset, "question": question, "option": opt_a}


# ── The list itself is NOT restricted ───────────────────────────────────────

class TestPapersListStaysVisibleToEveryone:
    def test_colleague_admin_sees_the_paper_in_the_list(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.get("/api/assessments/admin/papers/")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()["results"]]
        assert str(owned_paper_chain["paper"].id) in ids


# ── Paper detail ─────────────────────────────────────────────────────────────

class TestPaperDetailOwnership:
    def test_creator_can_view(self, admin_client, owned_paper_chain):
        resp = admin_client.get(f"/api/assessments/admin/papers/{owned_paper_chain['paper'].id}/")
        assert resp.status_code == 200

    def test_colleague_blocked_from_viewing(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.get(f"/api/assessments/admin/papers/{owned_paper_chain['paper'].id}/")
        assert resp.status_code == 403
        assert resp.json()["message"] == PAPER_OWNERSHIP_DENIED_MSG

    def test_colleague_blocked_from_editing(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.patch(
            f"/api/assessments/admin/papers/{owned_paper_chain['paper'].id}/",
            {"title": "hijacked"}, format="json",
        )
        assert resp.status_code == 403
        owned_paper_chain["paper"].refresh_from_db()
        assert owned_paper_chain["paper"].title == "Faculty-Private Paper"

    def test_colleague_blocked_from_deleting(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.delete(f"/api/assessments/admin/papers/{owned_paper_chain['paper'].id}/")
        assert resp.status_code == 403
        assert QuestionPaper.objects.filter(pk=owned_paper_chain["paper"].id).exists()

    def test_super_admin_can_view_despite_not_being_creator(self, super_admin_client, owned_paper_chain):
        resp = super_admin_client.get(f"/api/assessments/admin/papers/{owned_paper_chain['paper'].id}/")
        assert resp.status_code == 200

    def test_super_admin_can_edit_despite_not_being_creator(self, super_admin_client, owned_paper_chain):
        resp = super_admin_client.patch(
            f"/api/assessments/admin/papers/{owned_paper_chain['paper'].id}/",
            {"title": "super admin fixed a typo"}, format="json",
        )
        assert resp.status_code == 200


class TestPaperInstructionsOwnership:
    def test_colleague_blocked(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.patch(
            f"/api/assessments/admin/papers/{owned_paper_chain['paper'].id}/instructions/",
            {"instructions": "hijacked"}, format="json",
        )
        assert resp.status_code == 403

    def test_creator_allowed(self, admin_client, owned_paper_chain):
        resp = admin_client.patch(
            f"/api/assessments/admin/papers/{owned_paper_chain['paper'].id}/instructions/",
            {"instructions": "Read carefully."}, format="json",
        )
        assert resp.status_code == 200


# ── Sets ───────────────────────────────────────────────────────────────────

class TestSetOwnership:
    def test_colleague_blocked_from_creating_a_set(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.post(
            f"/api/assessments/admin/papers/{owned_paper_chain['paper'].id}/sets/",
            {"label": "Set B"}, format="json",
        )
        assert resp.status_code == 403

    def test_colleague_blocked_from_viewing_a_set(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.get(f"/api/assessments/admin/sets/{owned_paper_chain['qset'].id}/")
        assert resp.status_code == 403

    def test_colleague_blocked_from_editing_a_set(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.patch(
            f"/api/assessments/admin/sets/{owned_paper_chain['qset'].id}/", {"label": "Hijacked"}, format="json",
        )
        assert resp.status_code == 403

    def test_colleague_blocked_from_deleting_a_set(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.delete(f"/api/assessments/admin/sets/{owned_paper_chain['qset'].id}/")
        assert resp.status_code == 403

    def test_creator_can_view_a_set(self, admin_client, owned_paper_chain):
        resp = admin_client.get(f"/api/assessments/admin/sets/{owned_paper_chain['qset'].id}/")
        assert resp.status_code == 200

    def test_colleague_blocked_from_set_image_presign(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.post(
            f"/api/assessments/admin/sets/{owned_paper_chain['qset'].id}/image-presign/",
            {"filename": "q.jpg", "content_type": "image/jpeg"}, format="json",
        )
        assert resp.status_code == 403


# ── Questions ────────────────────────────────────────────────────────────────

class TestQuestionOwnership:
    def test_colleague_blocked_from_creating_a_question(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.post(
            f"/api/assessments/admin/sets/{owned_paper_chain['qset'].id}/questions/",
            {"question_text": "3+3?", "marks": 1}, format="json",
        )
        assert resp.status_code == 403

    def test_colleague_blocked_from_viewing_a_question(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.get(f"/api/assessments/admin/questions/{owned_paper_chain['question'].id}/")
        assert resp.status_code == 403

    def test_colleague_blocked_from_editing_a_question(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.patch(
            f"/api/assessments/admin/questions/{owned_paper_chain['question'].id}/",
            {"question_text": "hijacked"}, format="json",
        )
        assert resp.status_code == 403

    def test_colleague_blocked_from_deleting_a_question(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.delete(f"/api/assessments/admin/questions/{owned_paper_chain['question'].id}/")
        assert resp.status_code == 403

    def test_colleague_blocked_from_question_image_presign(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.post(
            f"/api/assessments/admin/questions/{owned_paper_chain['question'].id}/image-presign/",
            {"filename": "q.jpg", "content_type": "image/jpeg"}, format="json",
        )
        assert resp.status_code == 403

    def test_creator_can_view_a_question(self, admin_client, owned_paper_chain):
        resp = admin_client.get(f"/api/assessments/admin/questions/{owned_paper_chain['question'].id}/")
        assert resp.status_code == 200


# ── Options ──────────────────────────────────────────────────────────────────

class TestOptionOwnership:
    def test_colleague_blocked_from_listing_options(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.get(f"/api/assessments/admin/questions/{owned_paper_chain['question'].id}/options/")
        assert resp.status_code == 403

    def test_colleague_blocked_from_creating_an_option(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.post(
            f"/api/assessments/admin/questions/{owned_paper_chain['question'].id}/options/",
            {"text": "6"}, format="json",
        )
        assert resp.status_code == 403

    def test_colleague_blocked_from_editing_an_option(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.patch(
            f"/api/assessments/admin/questions/{owned_paper_chain['question'].id}/options/{owned_paper_chain['option'].id}/",
            {"text": "hijacked"}, format="json",
        )
        assert resp.status_code == 403

    def test_colleague_blocked_from_deleting_an_option(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.delete(
            f"/api/assessments/admin/questions/{owned_paper_chain['question'].id}/options/{owned_paper_chain['option'].id}/",
        )
        assert resp.status_code == 403

    def test_colleague_blocked_from_option_image_presign(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.post(
            f"/api/assessments/admin/questions/{owned_paper_chain['question'].id}/options/{owned_paper_chain['option'].id}/image-presign/",
            {"filename": "o.jpg", "content_type": "image/jpeg"}, format="json",
        )
        assert resp.status_code == 403


# ── Assign ───────────────────────────────────────────────────────────────────

class TestAssignOwnership:
    def _payload(self, paper):
        return {
            "paper": str(paper.id),
            "batch_id": str(uuid.uuid4()),
            "global_expire_time": (timezone.now() + timedelta(hours=3)).isoformat(),
            "exam_duration_minutes": 60,
        }

    def test_colleague_blocked_from_assigning(self, colleague_admin_client, owned_paper_chain):
        resp = colleague_admin_client.post(
            "/api/assessments/admin/assignments/", self._payload(owned_paper_chain["paper"]), format="json",
        )
        assert resp.status_code == 403
        assert resp.json()["message"] == PAPER_OWNERSHIP_DENIED_MSG
        assert not BatchAssignment.objects.filter(paper=owned_paper_chain["paper"]).exists()

    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_creator_can_assign(self, mock_snap, admin_client, owned_paper_chain):
        mock_snap.return_value = 0
        resp = admin_client.post(
            "/api/assessments/admin/assignments/", self._payload(owned_paper_chain["paper"]), format="json",
        )
        assert resp.status_code == 201

    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_super_admin_can_assign_despite_not_being_creator(self, mock_snap, super_admin_client, owned_paper_chain):
        mock_snap.return_value = 0
        resp = super_admin_client.post(
            "/api/assessments/admin/assignments/", self._payload(owned_paper_chain["paper"]), format="json",
        )
        assert resp.status_code == 201

    def test_colleague_can_still_list_all_institution_assignments(self, colleague_admin_client, owned_paper_chain):
        # The assignments LIST (unlike creating one) is results-adjacent,
        # not paper-authoring — deliberately NOT gated by paper ownership.
        resp = colleague_admin_client.get("/api/assessments/admin/assignments/")
        assert resp.status_code == 200


# ── Regression: Results/Analytics/Dashboard stay fully open ─────────────────

class TestResultsAnalyticsDashboardRemainUnrestricted:
    """Explicitly NOT part of this restriction, per the same decision that
    introduced it — this class exists to catch a future regression, not
    because these were ever touched by the ownership check."""

    def _assignment(self, paper):
        return BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID,
        )

    @patch("assessments.views.fetch_batch_roster")
    def test_colleague_can_view_results_for_a_paper_they_did_not_create(self, mock_roster, colleague_admin_client, owned_paper_chain):
        mock_roster.return_value = []
        assignment = self._assignment(owned_paper_chain["paper"])
        resp = colleague_admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/")
        assert resp.status_code == 200

    def test_colleague_can_view_dashboard_for_a_paper_they_did_not_create(self, colleague_admin_client, owned_paper_chain):
        assignment = self._assignment(owned_paper_chain["paper"])
        resp = colleague_admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/dashboard/")
        assert resp.status_code == 200
