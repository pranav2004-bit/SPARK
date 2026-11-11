import uuid

import pytest

from essays.models import EssayPaper, EssaySet, EssayQuestion


def _create_paper(client, title="Essay Paper 1"):
    resp = client.post("/api/essay/admin/papers/", {"title": title, "description": "desc"}, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data["data"]


def _create_set(client, paper_id, label="Set A"):
    resp = client.post(f"/api/essay/admin/papers/{paper_id}/sets/", {"label": label}, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data["data"]


def _create_question(client, set_id, **overrides):
    payload = {
        "question_text": "Describe a time you solved a difficult problem.",
        "llm_rubric_prompt": "Score for clarity, structure, and grammar out of 10.",
        "word_limit": 500,
        "time_limit_minutes": 30,
    }
    payload.update(overrides)
    resp = client.post(f"/api/essay/admin/sets/{set_id}/question/", payload, format="json")
    return resp


@pytest.mark.django_db
class TestAdminPaperCRUD:
    def test_create_list_paper(self, admin_client):
        _create_paper(admin_client, "Paper 1")
        resp = admin_client.get("/api/essay/admin/papers/")
        assert resp.status_code == 200
        # Paginated list responses return the pagination envelope directly
        # (StandardResultsPagination.get_paginated_response), not wrapped in
        # success_response's "data" key — unlike every other view here.
        assert resp.data["count"] == 1

    def test_get_paper_detail_includes_sets(self, admin_client):
        paper = _create_paper(admin_client)
        _create_set(admin_client, paper["id"], "Set A")
        resp = admin_client.get(f"/api/essay/admin/papers/{paper['id']}/")
        assert resp.status_code == 200
        assert len(resp.data["data"]["sets"]) == 1
        assert resp.data["data"]["sets"][0]["has_question"] is False

    def test_patch_paper(self, admin_client):
        paper = _create_paper(admin_client)
        resp = admin_client.patch(f"/api/essay/admin/papers/{paper['id']}/", {"title": "Renamed"}, format="json")
        assert resp.status_code == 200
        assert resp.data["data"]["title"] == "Renamed"

    def test_delete_paper(self, admin_client):
        paper = _create_paper(admin_client)
        resp = admin_client.delete(f"/api/essay/admin/papers/{paper['id']}/")
        assert resp.status_code == 200
        assert not EssayPaper.objects.filter(pk=paper["id"]).exists()


@pytest.mark.django_db
class TestAdminSetAndQuestionCRUD:
    def test_full_creation_chain(self, admin_client):
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        resp = _create_question(admin_client, eset["id"])
        assert resp.status_code == 201, resp.data
        assert resp.data["data"]["max_score"] == 10

        detail = admin_client.get(f"/api/essay/admin/sets/{eset['id']}/")
        assert detail.status_code == 200
        assert detail.data["data"]["question"]["question_text"] == "Describe a time you solved a difficult problem."

    def test_second_question_on_same_set_rejected(self, admin_client):
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        first = _create_question(admin_client, eset["id"])
        assert first.status_code == 201
        second = _create_question(admin_client, eset["id"])
        assert second.status_code == 400
        assert "already has a question" in second.data["message"]

    def test_patch_question(self, admin_client):
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        q = _create_question(admin_client, eset["id"]).data["data"]
        resp = admin_client.patch(f"/api/essay/admin/questions/{q['id']}/", {"word_limit": 800}, format="json")
        assert resp.status_code == 200
        assert resp.data["data"]["word_limit"] == 800

    def test_delete_question_allows_recreate(self, admin_client):
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        q = _create_question(admin_client, eset["id"]).data["data"]
        del_resp = admin_client.delete(f"/api/essay/admin/questions/{q['id']}/")
        assert del_resp.status_code == 200
        recreate = _create_question(admin_client, eset["id"], question_text="New prompt")
        assert recreate.status_code == 201

    def test_unique_set_label_conflict_returns_400(self, admin_client):
        paper = _create_paper(admin_client)
        _create_set(admin_client, paper["id"], "Set A")
        resp = admin_client.post(f"/api/essay/admin/papers/{paper['id']}/sets/", {"label": "Set A"}, format="json")
        assert resp.status_code == 400


@pytest.mark.django_db
class TestAdminQuestionEdgeCases:
    def test_empty_question_text_rejected(self, admin_client):
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        resp = _create_question(admin_client, eset["id"], question_text="   ")
        assert resp.status_code == 400

    def test_empty_rubric_prompt_rejected(self, admin_client):
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        resp = _create_question(admin_client, eset["id"], llm_rubric_prompt="")
        assert resp.status_code == 400

    def test_unicode_emoji_in_prompt_accepted(self, admin_client):
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        resp = _create_question(
            admin_client, eset["id"],
            question_text="Écrivez sur un défi 🎯 que vous avez surmonté — 你好世界",
        )
        assert resp.status_code == 201, resp.data
        assert "🎯" in resp.data["data"]["question_text"]

    def test_over_length_rubric_prompt_accepted_no_arbitrary_cap(self, admin_client):
        # TextField has no max_length — a long, detailed rubric is a
        # legitimate admin use case, not something to arbitrarily cap.
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        long_rubric = "Evaluate for clarity, structure, grammar, and originality. " * 200
        resp = _create_question(admin_client, eset["id"], llm_rubric_prompt=long_rubric)
        assert resp.status_code == 201


@pytest.mark.django_db
class TestSecurityIsolation:
    def test_cross_institution_paper_access_is_404_not_403(self, admin_client, admin_b_client):
        paper = _create_paper(admin_client)
        resp = admin_b_client.get(f"/api/essay/admin/papers/{paper['id']}/")
        assert resp.status_code == 404

    def test_cross_institution_cannot_patch(self, admin_client, admin_b_client):
        paper = _create_paper(admin_client)
        resp = admin_b_client.patch(f"/api/essay/admin/papers/{paper['id']}/", {"title": "Hijacked"}, format="json")
        assert resp.status_code == 404
        paper_obj = EssayPaper.objects.get(pk=paper["id"])
        assert paper_obj.title != "Hijacked"

    def test_cross_institution_set_access_is_404(self, admin_client, admin_b_client):
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        resp = admin_b_client.get(f"/api/essay/admin/sets/{eset['id']}/")
        assert resp.status_code == 404

    def test_unauthenticated_rejected(self, anon_client):
        resp = anon_client.get("/api/essay/admin/papers/")
        assert resp.status_code == 401

    def test_student_role_rejected(self, student_client):
        resp = student_client.get("/api/essay/admin/papers/")
        assert resp.status_code == 403

    def test_super_admin_allowed(self, super_admin_client):
        resp = super_admin_client.get("/api/essay/admin/papers/")
        assert resp.status_code == 200

    # Task 15.1's own IDOR & Cross-Institution Audit — the rest of this
    # class, added in that round. A coverage-mapping pass found this
    # module's own detail/sets/question/set-detail/question-detail
    # endpoints had gaps (DELETE never covered cross-institution, wrong-
    # role only ever tested on the plain list endpoint, and two entire
    # endpoints — papers/<pk>/sets/ POST and sets/<pk>/question/ POST —
    # had zero access-control tests at all). Every view below was read
    # directly first (AdminPaperSetsView, AdminSetQuestionView,
    # AdminQuestionDetailView all already filter by
    # institution_id=/paper__institution_id=/set__paper__institution_id=)
    # — this closes a test-coverage gap, not a live vulnerability.

    def test_cross_institution_cannot_delete_paper(self, admin_client, admin_b_client):
        paper = _create_paper(admin_client)
        resp = admin_b_client.delete(f"/api/essay/admin/papers/{paper['id']}/")
        assert resp.status_code == 404
        assert EssayPaper.objects.filter(pk=paper["id"]).exists()

    def test_paper_detail_rejects_student_and_anon(self, admin_client, student_client, anon_client):
        paper = _create_paper(admin_client)
        for method, kwargs in [("get", {}), ("patch", {"data": {"title": "x"}, "format": "json"}), ("delete", {})]:
            assert getattr(student_client, method)(f"/api/essay/admin/papers/{paper['id']}/", **kwargs).status_code == 403
            assert getattr(anon_client, method)(f"/api/essay/admin/papers/{paper['id']}/", **kwargs).status_code in (401, 403)
        assert EssayPaper.objects.filter(pk=paper["id"]).exists()

    def test_paper_create_rejects_student_and_anon(self, student_client, anon_client):
        resp = student_client.post("/api/essay/admin/papers/", {"title": "x"}, format="json")
        assert resp.status_code == 403
        resp = anon_client.post("/api/essay/admin/papers/", {"title": "x"}, format="json")
        assert resp.status_code in (401, 403)

    def test_sets_create_rejects_cross_institution_and_wrong_role(self, admin_client, admin_b_client, student_client, anon_client):
        paper = _create_paper(admin_client)
        url = f"/api/essay/admin/papers/{paper['id']}/sets/"
        assert admin_b_client.post(url, {"label": "Hijacked Set"}, format="json").status_code == 404
        assert student_client.post(url, {"label": "x"}, format="json").status_code == 403
        assert anon_client.post(url, {"label": "x"}, format="json").status_code in (401, 403)
        assert EssaySet.objects.filter(paper_id=paper["id"]).count() == 0

    def test_cross_institution_cannot_patch_or_delete_set(self, admin_client, admin_b_client):
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        url = f"/api/essay/admin/sets/{eset['id']}/"
        resp = admin_b_client.patch(url, {"label": "Hijacked"}, format="json")
        assert resp.status_code == 404
        resp = admin_b_client.delete(url)
        assert resp.status_code == 404
        assert EssaySet.objects.filter(pk=eset["id"]).exists()

    def test_set_detail_rejects_student_and_anon(self, admin_client, student_client, anon_client):
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        url = f"/api/essay/admin/sets/{eset['id']}/"
        assert student_client.get(url).status_code == 403
        assert anon_client.get(url).status_code in (401, 403)

    def test_question_create_rejects_cross_institution_and_wrong_role(self, admin_client, admin_b_client, student_client, anon_client):
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        url = f"/api/essay/admin/sets/{eset['id']}/question/"
        payload = {
            "question_text": "Q", "llm_rubric_prompt": "R", "word_limit": 500, "time_limit_minutes": 30,
        }
        assert admin_b_client.post(url, payload, format="json").status_code == 404
        assert student_client.post(url, payload, format="json").status_code == 403
        assert anon_client.post(url, payload, format="json").status_code in (401, 403)
        assert not EssayQuestion.objects.filter(set_id=eset["id"]).exists()

    def test_question_detail_rejects_cross_institution_and_wrong_role(self, admin_client, admin_b_client, student_client, anon_client):
        # AdminQuestionDetailView only implements patch/delete — no get
        # (confirmed live by this test's own first draft, which assumed a
        # get and got a genuine 405, not a 404 — fixed here, not a
        # security gap).
        paper = _create_paper(admin_client)
        eset = _create_set(admin_client, paper["id"])
        q = _create_question(admin_client, eset["id"]).data["data"]
        url = f"/api/essay/admin/questions/{q['id']}/"

        assert admin_b_client.patch(url, {"word_limit": 999}, format="json").status_code == 404
        assert admin_b_client.delete(url).status_code == 404
        assert EssayQuestion.objects.filter(pk=q["id"]).exists()

        assert student_client.patch(url, {"word_limit": 999}, format="json").status_code == 403
        assert anon_client.patch(url, {"word_limit": 999}, format="json").status_code in (401, 403)
