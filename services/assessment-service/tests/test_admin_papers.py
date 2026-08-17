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
    QuestionPaper, QuestionSet, Question, QuestionOption,
    MCQ_TYPE_SINGLE, MCQ_TYPE_MULTIPLE,
    QUESTION_CONTENT_IMAGE, QUESTION_CONTENT_BOTH,
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
    # A 2nd option — assignment-readiness now requires >=2 options per
    # question (get_assignment_readiness_blockers), and TestLockedPaperBlocks
    # EveryMutation._lock() below creates a real assignment against this
    # exact chain, so it must already be assignment-ready.
    QuestionOption.objects.create(question=question, label="B", text="5", is_correct=False, order=2)
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


class TestPaperListCreatorEnrichment:
    """"Created by <name>" on each paper card (frontend/admin/assessments/
    papers/page.tsx) — created_by_name/created_by_email resolved via
    core.auth_service_client.resolve_user_names, one batch call for the
    whole page. conftest.py's autouse _mock_resolve_user_names fixture
    stubs this to {} for every other test in the suite; these tests
    override it locally to verify the enrichment wiring itself."""

    @patch("assessments.views.resolve_user_names")
    def test_resolved_name_and_email_attached_to_each_row(self, mock_resolve, admin_client, paper_chain):
        mock_resolve.return_value = {
            str(ADMIN_USER_ID): {"name": "Dr. Author", "email": "author@test.com"},
        }
        resp = admin_client.get("/api/assessments/admin/papers/")
        assert resp.status_code == 200
        row = next(p for p in resp.json()["results"] if p["id"] == str(paper_chain["paper"].id))
        assert row["created_by_name"] == "Dr. Author"
        assert row["created_by_email"] == "author@test.com"
        # Called with exactly this page's distinct creator ids — not every
        # user in the system.
        mock_resolve.assert_called_once()
        assert mock_resolve.call_args[0][0] == [str(ADMIN_USER_ID)]

    @patch("assessments.views.resolve_user_names")
    def test_unresolved_creator_gets_empty_strings_not_an_error(self, mock_resolve, admin_client, paper_chain):
        # resolve_user_names degrading to {} (its own documented best-effort
        # failure mode) must never break the papers list itself.
        mock_resolve.return_value = {}
        resp = admin_client.get("/api/assessments/admin/papers/")
        assert resp.status_code == 200
        row = next(p for p in resp.json()["results"] if p["id"] == str(paper_chain["paper"].id))
        assert row["created_by_name"] == ""
        assert row["created_by_email"] == ""

    @patch("assessments.views.resolve_user_names")
    def test_empty_papers_list_never_calls_resolve(self, mock_resolve, admin_b_client):
        # admin_b_client's institution has no papers here — no creator ids
        # to resolve, so the batch lookup shouldn't fire at all.
        resp = admin_b_client.get("/api/assessments/admin/papers/")
        assert resp.status_code == 200
        assert resp.json()["results"] == []
        mock_resolve.assert_not_called()


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


class TestMcqTypeTransitionValidation:
    """Live bug report: the frontend's "Answer Type" toggle used to be
    local-only (no PATCH), so a question could end up single-choice with
    2+ correct options already persisted via the option-level endpoints
    (which only guard *their own* single-choice invariant, not a
    subsequent mcq_type change on the question itself). Covers both the
    pre-existing option-level guard and the new question-level guard
    added to close the reverse direction."""

    def test_option_level_rejects_second_correct_option_on_single_choice(self, admin_client, paper_chain):
        # paper_chain's question is MCQ_TYPE_SINGLE with one correct option already.
        second = QuestionOption.objects.create(
            question=paper_chain["question"], label="B", text="5", is_correct=False, order=2,
        )
        resp = admin_client.patch(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/{second.id}/",
            {"is_correct": True}, format="json",
        )
        assert resp.status_code == 400
        second.refresh_from_db()
        assert second.is_correct is False

    def test_switch_to_multiple_then_marking_second_option_correct_succeeds(self, admin_client, paper_chain):
        resp = admin_client.patch(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/",
            {"mcq_type": MCQ_TYPE_MULTIPLE}, format="json",
        )
        assert resp.status_code == 200
        second = QuestionOption.objects.create(
            question=paper_chain["question"], label="B", text="5", is_correct=False, order=2,
        )
        resp = admin_client.patch(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/options/{second.id}/",
            {"is_correct": True}, format="json",
        )
        assert resp.status_code == 200
        second.refresh_from_db()
        assert second.is_correct is True

    def test_switch_to_single_with_two_correct_options_already_set_is_rejected(self, admin_client, paper_chain):
        admin_client.patch(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/",
            {"mcq_type": MCQ_TYPE_MULTIPLE}, format="json",
        )
        second = QuestionOption.objects.create(
            question=paper_chain["question"], label="B", text="5", is_correct=True, order=2,
        )
        resp = admin_client.patch(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/",
            {"mcq_type": MCQ_TYPE_SINGLE}, format="json",
        )
        assert resp.status_code == 400
        assert "more than one correct option" in resp.json()["message"]
        paper_chain["question"].refresh_from_db()
        assert paper_chain["question"].mcq_type == MCQ_TYPE_MULTIPLE

    def test_switch_to_single_with_at_most_one_correct_option_succeeds(self, admin_client, paper_chain):
        admin_client.patch(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/",
            {"mcq_type": MCQ_TYPE_MULTIPLE}, format="json",
        )
        resp = admin_client.patch(
            f"/api/assessments/admin/questions/{paper_chain['question'].id}/",
            {"mcq_type": MCQ_TYPE_SINGLE}, format="json",
        )
        assert resp.status_code == 200
        paper_chain["question"].refresh_from_db()
        assert paper_chain["question"].mcq_type == MCQ_TYPE_SINGLE


class TestSetImagePresignIDOR:
    """AdminSetImagePresignView — presign for a question image before the
    question exists yet, scoped to the QuestionSet (Live bug report,
    2026-08-14). Same IDOR shape as the question/option presign endpoints
    already covered above."""

    def test_cross_institution_404(self, admin_b_client, paper_chain):
        resp = admin_b_client.post(
            f"/api/assessments/admin/sets/{paper_chain['qset'].id}/image-presign/",
            {"filename": "x.jpg", "content_type": "image/jpeg"}, format="json",
        )
        assert resp.status_code == 404

    def test_student_forbidden(self, student_client, paper_chain):
        resp = student_client.post(
            f"/api/assessments/admin/sets/{paper_chain['qset'].id}/image-presign/",
            {"filename": "x.jpg", "content_type": "image/jpeg"}, format="json",
        )
        assert resp.status_code == 403


class TestQuestionCreateWithImage:
    """Live bug report, 2026-08-14: selecting "Text + Image" (or "Image")
    on a brand-new question was a dead end — the create endpoint requires
    an image already attached for content_type='both', but the frontend
    only allowed image upload *after* the question was saved. Fixed by
    letting the image be presigned/uploaded against the QuestionSet before
    the question exists (TestSetImagePresignIDOR above), then attached on
    the question's first save. These tests cover that first-save path,
    including that the same verify/scan/quota gate PATCH already applies
    to later image changes is also applied here, not skipped."""

    def test_both_without_image_still_rejected(self, admin_client, paper_chain):
        # Exact scenario from the bug report: 'both' selected, no image
        # attached yet — must still be rejected, not silently accepted.
        resp = admin_client.post(
            f"/api/assessments/admin/sets/{paper_chain['qset'].id}/questions/",
            {"question_content_type": QUESTION_CONTENT_BOTH, "question_text": "Solve: 84÷7", "marks": 1},
            format="json",
        )
        assert resp.status_code == 400
        assert "requires both text and an image" in resp.json()["message"]

    @patch("assessments.views.scan_image_for_malware", return_value=None)
    @patch("assessments.views.verify_uploaded_image", return_value=(2048, None))
    def test_both_with_presigned_image_succeeds_on_first_save(self, mock_verify, mock_scan, admin_client, paper_chain):
        resp = admin_client.post(
            f"/api/assessments/admin/sets/{paper_chain['qset'].id}/questions/",
            {
                "question_content_type": QUESTION_CONTENT_BOTH,
                "question_text": "Solve: 84÷7",
                "question_image_key": "uploads/image/fake-key.jpg",
                "marks": 1,
            },
            format="json",
        )
        assert resp.status_code == 201
        question = Question.objects.get(pk=resp.json()["data"]["id"])
        assert question.question_content_type == QUESTION_CONTENT_BOTH
        assert question.question_image_key == "uploads/image/fake-key.jpg"
        assert question.question_image_size_bytes == 2048
        mock_verify.assert_called_once_with("uploads/image/fake-key.jpg")

    @patch("assessments.views.scan_image_for_malware", return_value=None)
    @patch("assessments.views.verify_uploaded_image", return_value=(2048, None))
    def test_image_only_with_no_text_succeeds(self, mock_verify, mock_scan, admin_client, paper_chain):
        resp = admin_client.post(
            f"/api/assessments/admin/sets/{paper_chain['qset'].id}/questions/",
            {
                "question_content_type": QUESTION_CONTENT_IMAGE,
                "question_image_key": "uploads/image/fake-key.jpg",
                "marks": 1,
            },
            format="json",
        )
        assert resp.status_code == 201

    @patch("assessments.views.delete_file")
    @patch("assessments.views.scan_image_for_malware", return_value="Malware detected in uploaded file.")
    @patch("assessments.views.verify_uploaded_image", return_value=(2048, None))
    def test_infected_image_rejected_and_cleaned_up(self, mock_verify, mock_scan, mock_delete, admin_client, paper_chain):
        before_count = Question.objects.count()
        resp = admin_client.post(
            f"/api/assessments/admin/sets/{paper_chain['qset'].id}/questions/",
            {
                "question_content_type": QUESTION_CONTENT_BOTH,
                "question_text": "Solve: 84÷7",
                "question_image_key": "uploads/image/infected.jpg",
                "marks": 1,
            },
            format="json",
        )
        assert resp.status_code == 400
        assert Question.objects.count() == before_count
        mock_delete.assert_called_once_with("uploads/image/infected.jpg")

    @patch("assessments.views.delete_file")
    @patch("assessments.views.scan_image_for_malware", return_value=None)
    @patch("assessments.views.verify_uploaded_image", return_value=(250 * 1024 * 1024, None))
    def test_over_quota_image_rejected_and_cleaned_up(self, mock_verify, mock_scan, mock_delete, admin_client, paper_chain):
        before_count = Question.objects.count()
        resp = admin_client.post(
            f"/api/assessments/admin/sets/{paper_chain['qset'].id}/questions/",
            {
                "question_content_type": QUESTION_CONTENT_BOTH,
                "question_text": "Solve: 84÷7",
                "question_image_key": "uploads/image/huge.jpg",
                "marks": 1,
            },
            format="json",
        )
        assert resp.status_code == 400
        assert "storage limit" in resp.json()["message"]
        assert Question.objects.count() == before_count
        mock_delete.assert_called_once_with("uploads/image/huge.jpg")
