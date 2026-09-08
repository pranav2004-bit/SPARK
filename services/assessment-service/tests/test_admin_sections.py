"""
Dedicated coverage for the Question Sections feature (grouping layer
between a QuestionSet and its Questions, added 2026-08-26): the new admin
endpoints (list/create sections under a set, section detail get/patch/
delete, create a question within a section), the new cross-set "equal
section counts" assignment-readiness check, and the model-level behaviour
that keeps older/internal callers working without an explicit section
(Question.save()'s auto-default-section-per-set fallback).
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, QuestionSection, Question, QuestionOption,
    MCQ_TYPE_SINGLE,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID


def _payload(paper):
    return {
        "paper": str(paper.id),
        "batch_id": str(uuid.uuid4()),
        "global_expire_time": (timezone.now() + timedelta(hours=3)).isoformat(),
        "exam_duration_minutes": 60,
    }


@pytest.fixture
def section_chain(db):
    """An unlocked paper → set → section → question → option chain in
    INSTITUTION_A, owned by admin_client — same shape as test_admin_papers's
    paper_chain, extended one level for the section layer."""
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Sections Test Paper", created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    section = QuestionSection.objects.create(set=qset, title="Quantitative Aptitude", order=1)
    question = Question.objects.create(
        set=qset, section=section, question_text="2+2?", marks=1, mcq_type=MCQ_TYPE_SINGLE,
    )
    QuestionOption.objects.create(question=question, label="A", text="4", is_correct=True, order=1)
    QuestionOption.objects.create(question=question, label="B", text="5", is_correct=False, order=2)
    return {"paper": paper, "qset": qset, "section": section, "question": question}


def _lock(admin_client, paper):
    with patch("assessments.views.snapshot_roster_and_allocate", return_value=0):
        admin_client.post("/api/assessments/admin/assignments/", _payload(paper), format="json")
    paper.refresh_from_db()
    assert paper.is_locked() is True


# ── AdminSetSectionsView — list/create ──────────────────────────────────────

class TestSetSectionsListCreate:
    def test_list_returns_set_paper_and_sections(self, admin_client, section_chain):
        resp = admin_client.get(f"/api/assessments/admin/sets/{section_chain['qset'].id}/sections/")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["set"]["id"] == str(section_chain["qset"].id)
        assert body["paper"]["id"] == str(section_chain["paper"].id)
        titles = [s["title"] for s in body["sections"]]
        assert "Quantitative Aptitude" in titles

    def test_create_section_succeeds(self, admin_client, section_chain):
        resp = admin_client.post(
            f"/api/assessments/admin/sets/{section_chain['qset'].id}/sections/",
            {"title": "Logical Reasoning"}, format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["title"] == "Logical Reasoning"
        assert QuestionSection.objects.filter(set=section_chain["qset"], title="Logical Reasoning").exists()

    def test_create_section_auto_increments_order(self, admin_client, section_chain):
        # section_chain already has one section at order=1
        resp = admin_client.post(
            f"/api/assessments/admin/sets/{section_chain['qset'].id}/sections/",
            {"title": "Verbal Ability"}, format="json",
        )
        assert resp.json()["data"]["order"] == 2

    def test_duplicate_title_in_same_set_rejected(self, admin_client, section_chain):
        resp = admin_client.post(
            f"/api/assessments/admin/sets/{section_chain['qset'].id}/sections/",
            {"title": "Quantitative Aptitude"}, format="json",
        )
        assert resp.status_code == 400

    def test_same_title_in_a_different_set_is_fine(self, admin_client, section_chain):
        other_set = QuestionSet.objects.create(paper=section_chain["paper"], label="Set B", order=2)
        resp = admin_client.post(
            f"/api/assessments/admin/sets/{other_set.id}/sections/",
            {"title": "Quantitative Aptitude"}, format="json",
        )
        assert resp.status_code == 201

    def test_locked_paper_blocks_section_create(self, admin_client, section_chain):
        _lock(admin_client, section_chain["paper"])
        resp = admin_client.post(
            f"/api/assessments/admin/sets/{section_chain['qset'].id}/sections/",
            {"title": "New Section"}, format="json",
        )
        assert resp.status_code == 403

    def test_cross_institution_set_404s(self, admin_b_client, section_chain):
        resp = admin_b_client.get(f"/api/assessments/admin/sets/{section_chain['qset'].id}/sections/")
        assert resp.status_code == 404

    def test_student_forbidden(self, student_client, section_chain):
        resp = student_client.get(f"/api/assessments/admin/sets/{section_chain['qset'].id}/sections/")
        assert resp.status_code == 403


# ── AdminSectionDetailView — get/patch/delete ───────────────────────────────

class TestSectionDetail:
    def test_get_returns_section_set_paper_and_questions(self, admin_client, section_chain):
        resp = admin_client.get(f"/api/assessments/admin/sections/{section_chain['section'].id}/")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["section"]["id"] == str(section_chain["section"].id)
        assert body["set"]["id"] == str(section_chain["qset"].id)
        assert body["paper"]["id"] == str(section_chain["paper"].id)
        assert len(body["questions"]) == 1
        assert body["questions"][0]["id"] == str(section_chain["question"].id)

    def test_patch_renames_section(self, admin_client, section_chain):
        resp = admin_client.patch(
            f"/api/assessments/admin/sections/{section_chain['section'].id}/",
            {"title": "Renamed Section"}, format="json",
        )
        assert resp.status_code == 200
        section_chain["section"].refresh_from_db()
        assert section_chain["section"].title == "Renamed Section"

    def test_delete_cascades_to_its_questions(self, admin_client, section_chain):
        question_id = section_chain["question"].id
        resp = admin_client.delete(f"/api/assessments/admin/sections/{section_chain['section'].id}/")
        assert resp.status_code == 200
        assert not QuestionSection.objects.filter(id=section_chain["section"].id).exists()
        assert not Question.objects.filter(id=question_id).exists()

    def test_locked_paper_blocks_patch(self, admin_client, section_chain):
        _lock(admin_client, section_chain["paper"])
        resp = admin_client.patch(
            f"/api/assessments/admin/sections/{section_chain['section'].id}/",
            {"title": "x"}, format="json",
        )
        assert resp.status_code == 403

    def test_locked_paper_blocks_delete(self, admin_client, section_chain):
        _lock(admin_client, section_chain["paper"])
        resp = admin_client.delete(f"/api/assessments/admin/sections/{section_chain['section'].id}/")
        assert resp.status_code == 403

    def test_cross_institution_404s(self, admin_b_client, section_chain):
        resp = admin_b_client.get(f"/api/assessments/admin/sections/{section_chain['section'].id}/")
        assert resp.status_code == 404

    def test_student_forbidden(self, student_client, section_chain):
        resp = student_client.get(f"/api/assessments/admin/sections/{section_chain['section'].id}/")
        assert resp.status_code == 403


# ── AdminSectionQuestionsView — create question within a section ───────────

class TestSectionQuestionsCreate:
    def test_create_question_gets_correct_set_and_section(self, admin_client, section_chain):
        resp = admin_client.post(
            f"/api/assessments/admin/sections/{section_chain['section'].id}/questions/",
            {"question_text": "New question", "marks": 2, "mcq_type": "single"}, format="json",
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["section"] == str(section_chain["section"].id)
        assert data["set"] == str(section_chain["qset"].id)

    def test_question_number_continues_set_wide_sequence(self, admin_client, section_chain):
        # section_chain's question is already #1 on the set — a 2nd question
        # in a *different* section of the same set must be #2, not restart at
        # #1 (Question.save() numbers per-set, not per-section — unchanged
        # by this feature, asserted here so a future refactor can't silently
        # break it without a test noticing).
        other_section = QuestionSection.objects.create(set=section_chain["qset"], title="Other", order=2)
        resp = admin_client.post(
            f"/api/assessments/admin/sections/{other_section.id}/questions/",
            {"question_text": "Second", "marks": 1, "mcq_type": "single"}, format="json",
        )
        assert resp.json()["data"]["question_number"] == 2

    def test_locked_paper_blocks_create(self, admin_client, section_chain):
        _lock(admin_client, section_chain["paper"])
        resp = admin_client.post(
            f"/api/assessments/admin/sections/{section_chain['section'].id}/questions/",
            {"question_text": "x", "marks": 1}, format="json",
        )
        assert resp.status_code == 403

    def test_content_type_blocker_enforced(self, admin_client, section_chain):
        resp = admin_client.post(
            f"/api/assessments/admin/sections/{section_chain['section'].id}/questions/",
            {"question_content_type": "both", "question_text": "only text, no image", "marks": 1},
            format="json",
        )
        assert resp.status_code == 400

    def test_cross_institution_404s(self, admin_b_client, section_chain):
        resp = admin_b_client.post(
            f"/api/assessments/admin/sections/{section_chain['section'].id}/questions/",
            {"question_text": "x", "marks": 1}, format="json",
        )
        assert resp.status_code == 404

    def test_student_forbidden(self, student_client, section_chain):
        resp = student_client.post(
            f"/api/assessments/admin/sections/{section_chain['section'].id}/questions/",
            {"question_text": "x", "marks": 1}, format="json",
        )
        assert resp.status_code == 403


# ── Model-level default section fallback ────────────────────────────────────

class TestQuestionAutoDefaultSection:
    """Question.save()'s fallback for callers that don't pass a section
    explicitly (e.g. the older AdminSetQuestionsView endpoint, or direct
    ORM use like most of the rest of this test suite) — must reuse one
    shared "Section 1" per set, not create a fresh one per question."""

    def test_question_created_without_section_gets_default(self, db):
        paper = QuestionPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
        qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
        q = Question.objects.create(set=qset, question_text="Q1", marks=1)
        assert q.section is not None
        assert q.section.title == "Section 1"
        assert q.section.set_id == qset.id

    def test_second_question_without_section_reuses_the_same_default(self, db):
        paper = QuestionPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
        qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
        q1 = Question.objects.create(set=qset, question_text="Q1", marks=1)
        q2 = Question.objects.create(set=qset, question_text="Q2", marks=1)
        assert q1.section_id == q2.section_id
        assert QuestionSection.objects.filter(set=qset).count() == 1

    def test_old_set_level_endpoint_still_works_via_the_fallback(self, admin_client, section_chain):
        resp = admin_client.post(
            f"/api/assessments/admin/sets/{section_chain['qset'].id}/questions/",
            {"question_text": "via legacy endpoint", "marks": 1}, format="json",
        )
        assert resp.status_code == 201
        q = Question.objects.get(id=resp.json()["data"]["id"])
        assert q.section is not None


# ── Cross-set section-count validation ──────────────────────────────────────

class TestCrossSetSectionCountValidation:
    def _two_set_paper(self, sections_per_set):
        """sections_per_set: list of ints, one per set — how many sections
        (each with one ready-to-assign question) that set gets."""
        paper = QuestionPaper.objects.create(
            institution_id=INSTITUTION_A, title="Section Count Test Paper", created_by=ADMIN_USER_ID,
        )
        for i, n_sections in enumerate(sections_per_set):
            qset = QuestionSet.objects.create(paper=paper, label=f"Set {chr(65+i)}", order=i + 1)
            for j in range(n_sections):
                section = QuestionSection.objects.create(set=qset, title=f"Section {j+1}", order=j + 1)
                q = Question.objects.create(set=qset, section=section, question_text=f"Q{j}", marks=1, mcq_type=MCQ_TYPE_SINGLE)
                QuestionOption.objects.create(question=q, label="A", text="right", is_correct=True, order=1)
                QuestionOption.objects.create(question=q, label="B", text="wrong", is_correct=False, order=2)
        return paper

    def test_unequal_section_counts_across_sets_rejected(self, admin_client):
        paper = self._two_set_paper([1, 2])
        resp = admin_client.post("/api/assessments/admin/assignments/", _payload(paper), format="json")
        assert resp.status_code == 400
        assert "unequal section counts" in resp.json()["message"]

    def test_equal_section_counts_across_sets_not_flagged(self, admin_client):
        paper = self._two_set_paper([2, 2])
        with patch("assessments.views.snapshot_roster_and_allocate", return_value=0):
            resp = admin_client.post("/api/assessments/admin/assignments/", _payload(paper), format="json")
        assert resp.status_code == 201

    def test_single_set_paper_never_flagged_regardless_of_section_count(self, admin_client):
        # The rule is explicitly scoped to >1 set — a single-set paper has
        # nothing to compare its section count against.
        paper = self._two_set_paper([3])
        with patch("assessments.views.snapshot_roster_and_allocate", return_value=0):
            resp = admin_client.post("/api/assessments/admin/assignments/", _payload(paper), format="json")
        assert resp.status_code == 201


# ── Paper detail's per-set section_count (Final Review checklist, added
# 2026-08-27) — the admin Assign page's pre-flight checklist reads this
# field straight off GET admin/papers/<pk>/, so it must be correct per set,
# not just present. ──────────────────────────────────────────────────────

class TestPaperDetailSectionCount:
    def _two_set_paper(self, sections_per_set):
        paper = QuestionPaper.objects.create(
            institution_id=INSTITUTION_A, title="Section Count Detail Paper", created_by=ADMIN_USER_ID,
        )
        for i, n_sections in enumerate(sections_per_set):
            qset = QuestionSet.objects.create(paper=paper, label=f"Set {chr(65+i)}", order=i + 1)
            for j in range(n_sections):
                QuestionSection.objects.create(set=qset, title=f"Section {j+1}", order=j + 1)
        return paper

    def test_section_count_reported_correctly_per_set(self, admin_client):
        paper = self._two_set_paper([1, 3])
        resp = admin_client.get(f"/api/assessments/admin/papers/{paper.id}/")
        assert resp.status_code == 200
        sets = {s["label"]: s["section_count"] for s in resp.json()["data"]["sets"]}
        assert sets == {"Set A": 1, "Set B": 3}

    def test_section_count_does_not_inflate_question_count_or_vice_versa(self, admin_client, section_chain):
        # Regression guard: annotating question_count and section_count in
        # the same queryset joins both reverse relations — without
        # distinct=True on both Count()s, the join's row fan-out silently
        # inflates one or both counts. section_chain's set has exactly one
        # section and one question, so any fan-out would show up as >1 here.
        resp = admin_client.get(f"/api/assessments/admin/papers/{section_chain['paper'].id}/")
        assert resp.status_code == 200
        row = resp.json()["data"]["sets"][0]
        assert row["question_count"] == 1
        assert row["section_count"] == 1
