"""
Task 12.1's IDOR audit — the "Admin — Question Papers" endpoint group
(Task 2.2) had zero dedicated cross-institution/cross-student tests before
this file: every existing reference to these endpoints elsewhere in the
suite (e.g. test_assignments.py's immutability-lock tests) only exercises
them as fixture setup or tests a different property (the assigned-paper
lock, not institution isolation). The views themselves were already
correctly institution-scoped (every lookup filters by
`institution_id`/`paper__institution_id`/`set__paper__institution_id` —
read the code before writing these tests) — this file exists to lock that
in with an explicit test per endpoint, per this task's own mandate, not
because a vulnerability was found.
"""
import uuid
from unittest.mock import patch

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, Question, QuestionOption, MCQ_TYPE_SINGLE,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID


@pytest.fixture
def paper_chain(db):
    """An unlocked paper → set → question → option chain in INSTITUTION_A,
    owned by admin_client. admin_b_client (INSTITUTION_B) must not be able
    to read, write, or discover any of it."""
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="IDOR Audit Paper",
        created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    question = Question.objects.create(
        set=qset, question_text="2+2?", marks=1, mcq_type=MCQ_TYPE_SINGLE,
    )
    option = QuestionOption.objects.create(
        question=question, label="A", text="4", is_correct=True, order=1,
    )
    return {"paper": paper, "qset": qset, "question": question, "option": option}


class TestPaperListCreateIDOR:
    @patch("assessments.views.snapshot_roster_and_allocate")
    def test_list_excludes_other_institutions_papers(self, mock_snap, admin_b_client, paper_chain):
        resp = admin_b_client.get("/api/assessments/admin/papers/")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()["results"]]
        assert str(paper_chain["paper"].id) not in ids

    def test_create_is_scoped_to_own_institution(self, admin_b_client):
        resp = admin_b_client.post("/api/assessments/admin/papers/", {"title": "B's paper"}, format="json")
        assert resp.status_code == 201
        paper_id = resp.json()["data"]["id"]
        paper = QuestionPaper.objects.get(pk=paper_id)
        assert paper.institution_id != INSTITUTION_A

    def test_student_forbidden(self, student_client):
        resp = student_client.get("/api/assessments/admin/papers/")
        assert resp.status_code == 403


class TestPaperDetailIDOR:
    def test_cross_institution_get_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.get(f"/api/assessments/admin/papers/{paper_chain['paper'].id}/")
        assert resp.status_code == 404

    def test_cross_institution_patch_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.patch(
            f"/api/assessments/admin/papers/{paper_chain['paper'].id}/", {"title": "hijacked"}, format="json",
        )
        assert resp.status_code == 404
        paper_chain["paper"].refresh_from_db()
        assert paper_chain["paper"].title == "IDOR Audit Paper"

    def test_cross_institution_delete_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.delete(f"/api/assessments/admin/papers/{paper_chain['paper'].id}/")
        assert resp.status_code == 404
        assert QuestionPaper.objects.filter(pk=paper_chain["paper"].id).exists()

    def test_student_forbidden(self, student_client, paper_chain):
        resp = student_client.get(f"/api/assessments/admin/papers/{paper_chain['paper'].id}/")
        assert resp.status_code == 403


class TestPaperPublishIDOR:
    def test_cross_institution_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.patch(f"/api/assessments/admin/papers/{paper_chain['paper'].id}/publish/")
        assert resp.status_code == 404
        paper_chain["paper"].refresh_from_db()
        assert paper_chain["paper"].is_published is False

    def test_student_forbidden(self, student_client, paper_chain):
        resp = student_client.patch(f"/api/assessments/admin/papers/{paper_chain['paper'].id}/publish/")
        assert resp.status_code == 403


class TestPaperSetsCreateIDOR:
    def test_cross_institution_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.post(
            f"/api/assessments/admin/papers/{paper_chain['paper'].id}/sets/", {"label": "Hijacked Set"}, format="json",
        )
        assert resp.status_code == 404
        assert not QuestionSet.objects.filter(paper=paper_chain["paper"], label="Hijacked Set").exists()

    def test_student_forbidden(self, student_client, paper_chain):
        resp = student_client.post(f"/api/assessments/admin/papers/{paper_chain['paper'].id}/sets/", {"label": "X"}, format="json")
        assert resp.status_code == 403


class TestSetDetailIDOR:
    def test_cross_institution_get_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.get(f"/api/assessments/admin/sets/{paper_chain['qset'].id}/")
        assert resp.status_code == 404

    def test_cross_institution_patch_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.patch(
            f"/api/assessments/admin/sets/{paper_chain['qset'].id}/", {"label": "hijacked"}, format="json",
        )
        assert resp.status_code == 404
        paper_chain["qset"].refresh_from_db()
        assert paper_chain["qset"].label == "Set A"

    def test_cross_institution_delete_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.delete(f"/api/assessments/admin/sets/{paper_chain['qset'].id}/")
        assert resp.status_code == 404
        assert QuestionSet.objects.filter(pk=paper_chain["qset"].id).exists()

    def test_student_forbidden(self, student_client, paper_chain):
        resp = student_client.get(f"/api/assessments/admin/sets/{paper_chain['qset'].id}/")
        assert resp.status_code == 403


class TestSetQuestionsCreateIDOR:
    def test_cross_institution_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.post(
            f"/api/assessments/admin/sets/{paper_chain['qset'].id}/questions/",
            {"question_text": "hijacked?", "marks": 1}, format="json",
        )
        assert resp.status_code == 404
        assert not Question.objects.filter(set=paper_chain["qset"], question_text="hijacked?").exists()

    def test_student_forbidden(self, student_client, paper_chain):
        resp = student_client.post(
            f"/api/assessments/admin/sets/{paper_chain['qset'].id}/questions/", {"question_text": "x", "marks": 1}, format="json",
        )
        assert resp.status_code == 403


class TestQuestionDetailIDOR:
    def test_cross_institution_get_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.get(f"/api/assessments/admin/questions/{paper_chain['question'].id}/")
        assert resp.status_code == 404

    def test_cross_institution_patch_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.patch(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/", {"question_text": "hijacked?"}, format="json",
        )
        assert resp.status_code == 404
        paper_chain["question"].refresh_from_db()
        assert paper_chain["question"].question_text == "2+2?"

    def test_cross_institution_delete_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.delete(f"/api/assessments/admin/questions/{paper_chain['question'].id}/")
        assert resp.status_code == 404
        assert Question.objects.filter(pk=paper_chain["question"].id).exists()

    def test_student_forbidden(self, student_client, paper_chain):
        resp = student_client.get(f"/api/assessments/admin/questions/{paper_chain['question'].id}/")
        assert resp.status_code == 403


class TestQuestionOptionsIDOR:
    def test_cross_institution_get_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.get(f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/")
        assert resp.status_code == 404

    def test_cross_institution_post_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.post(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/",
            {"text": "hijacked", "label": "Z"}, format="json",
        )
        assert resp.status_code == 404
        assert not QuestionOption.objects.filter(question=paper_chain["question"], text="hijacked").exists()

    def test_student_forbidden(self, student_client, paper_chain):
        resp = student_client.get(f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/")
        assert resp.status_code == 403


class TestQuestionOptionDetailIDOR:
    def test_cross_institution_patch_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.patch(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/{paper_chain['option'].id}/",
            {"text": "hijacked"}, format="json",
        )
        assert resp.status_code == 404
        paper_chain["option"].refresh_from_db()
        assert paper_chain["option"].text == "4"

    def test_cross_institution_delete_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.delete(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/{paper_chain['option'].id}/",
        )
        assert resp.status_code == 404
        assert QuestionOption.objects.filter(pk=paper_chain["option"].id).exists()

    def test_student_forbidden(self, student_client, paper_chain):
        resp = student_client.patch(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/{paper_chain['option'].id}/",
            {"text": "x"}, format="json",
        )
        assert resp.status_code == 403

    def test_option_id_not_scoped_to_wrong_question_within_same_institution(self, admin_client, paper_chain):
        # A second question in the SAME institution — the URL's <pk>
        # (question id) and <option_pk> must both match, not just the
        # institution. Guards against an admin editing question A's option
        # via a URL built from question B's id + a stolen option_pk.
        other_question = Question.objects.create(
            set=paper_chain["qset"], question_text="Other Q", marks=1, mcq_type=MCQ_TYPE_SINGLE,
        )
        resp = admin_client.patch(
            f"/api/assessments/admin/questions/{other_question.id}/options/{paper_chain['option'].id}/",
            {"text": "hijacked"}, format="json",
        )
        assert resp.status_code == 404


class TestImagePresignIDOR:
    def test_question_presign_cross_institution_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.post(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/image-presign/",
            {"filename": "x.jpg", "content_type": "image/jpeg"}, format="json",
        )
        assert resp.status_code == 404

    def test_question_presign_student_forbidden(self, student_client, paper_chain):
        resp = student_client.post(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/image-presign/",
            {"filename": "x.jpg", "content_type": "image/jpeg"}, format="json",
        )
        assert resp.status_code == 403

    def test_option_presign_cross_institution_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.post(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/{paper_chain['option'].id}/image-presign/",
            {"filename": "x.jpg", "content_type": "image/jpeg"}, format="json",
        )
        assert resp.status_code == 404

    def test_option_presign_student_forbidden(self, student_client, paper_chain):
        resp = student_client.post(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/{paper_chain['option'].id}/image-presign/",
            {"filename": "x.jpg", "content_type": "image/jpeg"}, format="json",
        )
        assert resp.status_code == 403


class TestLockedPaperBlocksEveryMutation:
    """AT15 — every mutation on a locked (assigned) paper's content must be
    rejected, not just the ones test_assignments.py's immutability-lock
    tests happened to cover (question PATCH only)."""

    def _lock(self, admin_client, paper_chain):
        import uuid as _uuid
        from datetime import timedelta
        payload = {
            "paper": str(paper_chain["paper"].id),
            "batch_id": str(_uuid.uuid4()),
            "global_expire_time": (timezone.now() + timedelta(hours=3)).isoformat(),
            "exam_duration_minutes": 60,
        }
        with patch("assessments.views.snapshot_roster_and_allocate", return_value=0):
            admin_client.post("/api/assessments/admin/assignments/", payload, format="json")
        paper_chain["paper"].refresh_from_db()
        assert paper_chain["paper"].is_locked() is True

    def test_locked_paper_blocks_set_create(self, admin_client, paper_chain):
        self._lock(admin_client, paper_chain)
        resp = admin_client.post(f"/api/assessments/admin/papers/{paper_chain['paper'].id}/sets/", {"label": "New"}, format="json")
        assert resp.status_code == 403

    def test_locked_paper_blocks_set_patch(self, admin_client, paper_chain):
        self._lock(admin_client, paper_chain)
        resp = admin_client.patch(f"/api/assessments/admin/sets/{paper_chain['qset'].id}/", {"label": "x"}, format="json")
        assert resp.status_code == 403

    def test_locked_paper_blocks_set_delete(self, admin_client, paper_chain):
        self._lock(admin_client, paper_chain)
        resp = admin_client.delete(f"/api/assessments/admin/sets/{paper_chain['qset'].id}/")
        assert resp.status_code == 403

    def test_locked_paper_blocks_question_create(self, admin_client, paper_chain):
        self._lock(admin_client, paper_chain)
        resp = admin_client.post(
            f"/api/assessments/admin/sets/{paper_chain['qset'].id}/questions/", {"question_text": "x", "marks": 1}, format="json",
        )
        assert resp.status_code == 403

    def test_locked_paper_blocks_question_delete(self, admin_client, paper_chain):
        self._lock(admin_client, paper_chain)
        resp = admin_client.delete(f"/api/assessments/admin/questions/{paper_chain['question'].id}/")
        assert resp.status_code == 403

    def test_locked_paper_blocks_option_create(self, admin_client, paper_chain):
        self._lock(admin_client, paper_chain)
        resp = admin_client.post(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/", {"text": "x", "label": "Z"}, format="json",
        )
        assert resp.status_code == 403

    def test_locked_paper_blocks_option_patch(self, admin_client, paper_chain):
        self._lock(admin_client, paper_chain)
        resp = admin_client.patch(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/{paper_chain['option'].id}/",
            {"text": "x"}, format="json",
        )
        assert resp.status_code == 403

    def test_locked_paper_blocks_option_delete(self, admin_client, paper_chain):
        self._lock(admin_client, paper_chain)
        resp = admin_client.delete(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/{paper_chain['option'].id}/",
        )
        assert resp.status_code == 403

    def test_locked_paper_blocks_paper_patch(self, admin_client, paper_chain):
        self._lock(admin_client, paper_chain)
        resp = admin_client.patch(f"/api/assessments/admin/papers/{paper_chain['paper'].id}/", {"title": "x"}, format="json")
        assert resp.status_code == 403

    def test_locked_paper_blocks_paper_delete(self, admin_client, paper_chain):
        self._lock(admin_client, paper_chain)
        resp = admin_client.delete(f"/api/assessments/admin/papers/{paper_chain['paper'].id}/")
        assert resp.status_code == 403
