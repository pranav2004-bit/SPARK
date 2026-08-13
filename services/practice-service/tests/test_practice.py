import uuid
import pytest
from unittest.mock import patch
from tests.conftest import INSTITUTION_A, INSTITUTION_B, ADMIN_USER_ID, STUDENT_USER_ID


# ── Admin: Root hub ────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminPracticeRoot:
    def test_root_empty(self, admin_client, db):
        resp = admin_client.get("/api/practice/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["modules"] == []
        assert data["sections"] == []

    def test_root_shows_top_level_modules(self, admin_client, module):
        resp = admin_client.get("/api/practice/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["modules"]) == 1
        assert data["modules"][0]["name"] == "Quantitative Aptitude"

    def test_root_requires_auth(self, anon_client):
        resp = anon_client.get("/api/practice/")
        assert resp.status_code == 401

    def test_root_student_forbidden(self, student_client):
        resp = student_client.get("/api/practice/")
        assert resp.status_code == 403

    def test_root_excludes_child_modules(self, admin_client, module):
        from practice.models import PracticeModule
        PracticeModule.objects.create(
            name="Child Module", parent=module,
            institution_id=INSTITUTION_A, is_published=True,
        )
        resp = admin_client.get("/api/practice/")
        data = resp.json()["data"]
        # Only the top-level module appears, not the child
        assert len(data["modules"]) == 1

    def test_root_institution_isolation(self, admin_b_client, module):
        resp = admin_b_client.get("/api/practice/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["modules"] == []


# ── Admin: Modules ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminModules:
    def test_create_module(self, admin_client, db):
        resp = admin_client.post("/api/practice/modules/", {"name": "Logical Reasoning"}, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["name"] == "Logical Reasoning"

    def test_create_module_requires_admin(self, student_client):
        resp = student_client.post("/api/practice/modules/", {"name": "X"}, format="json")
        assert resp.status_code == 403

    def test_get_module_detail(self, admin_client, module, section):
        resp = admin_client.get(f"/api/practice/modules/{module.pk}/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["module"]["name"] == "Quantitative Aptitude"
        assert len(data["sections"]) == 1

    def test_get_module_detail_idor(self, admin_b_client, module):
        resp = admin_b_client.get(f"/api/practice/modules/{module.pk}/")
        assert resp.status_code == 404

    def test_patch_module(self, admin_client, module):
        resp = admin_client.patch(
            f"/api/practice/modules/{module.pk}/",
            {"name": "Updated Module"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Updated Module"

    def test_delete_module(self, admin_client, module):
        resp = admin_client.delete(f"/api/practice/modules/{module.pk}/")
        assert resp.status_code == 200
        from practice.models import PracticeModule
        assert not PracticeModule.objects.filter(pk=module.pk).exists()

    def test_cannot_delete_module_with_sections(self, admin_client, module, section):
        resp = admin_client.delete(f"/api/practice/modules/{module.pk}/")
        assert resp.status_code == 400
        from practice.models import PracticeModule
        assert PracticeModule.objects.filter(pk=module.pk).exists()

    def test_cannot_delete_module_with_children(self, admin_client, module, db):
        from practice.models import PracticeModule
        PracticeModule.objects.create(
            name="Child", parent=module, institution_id=module.institution_id,
        )
        resp = admin_client.delete(f"/api/practice/modules/{module.pk}/")
        assert resp.status_code == 400
        assert PracticeModule.objects.filter(pk=module.pk).exists()

    def test_create_child_module(self, admin_client, module):
        resp = admin_client.post(
            f"/api/practice/modules/{module.pk}/children/",
            {"name": "Sub-topic"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["parent"] == str(module.pk)

    def test_create_child_module_idor(self, admin_b_client, module):
        resp = admin_b_client.post(
            f"/api/practice/modules/{module.pk}/children/",
            {"name": "X"},
            format="json",
        )
        assert resp.status_code == 404

    def test_create_section_in_module(self, admin_client, module):
        resp = admin_client.post(
            f"/api/practice/modules/{module.pk}/sections/",
            {"name": "New Section"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["module"] == str(module.pk)

    def test_publish_module(self, admin_client, db):
        from practice.models import PracticeModule
        m = PracticeModule.objects.create(
            name="Unpublished", institution_id=INSTITUTION_A, is_published=False
        )
        resp = admin_client.patch(f"/api/practice/modules/{m.pk}/", {"is_published": True}, format="json")
        assert resp.status_code == 200
        assert resp.json()["data"]["is_published"] is True


# ── Admin: Sections ────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminSections:
    def test_create_root_section(self, admin_client, db):
        resp = admin_client.post("/api/practice/sections/", {"name": "Standalone Section"}, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["module"] is None

    def test_get_section_detail(self, admin_client, module, section, question):
        resp = admin_client.get(f"/api/practice/sections/{section.pk}/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["section"]["name"] == "Number Systems"
        assert len(data["questions"]) == 1

    def test_get_section_idor(self, admin_b_client, section):
        resp = admin_b_client.get(f"/api/practice/sections/{section.pk}/")
        assert resp.status_code == 404

    def test_patch_section(self, admin_client, section):
        resp = admin_client.patch(
            f"/api/practice/sections/{section.pk}/",
            {"name": "Renamed Section"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Renamed Section"

    def test_delete_section(self, admin_client, section):
        resp = admin_client.delete(f"/api/practice/sections/{section.pk}/")
        assert resp.status_code == 200
        from practice.models import PracticeSection
        assert not PracticeSection.objects.filter(pk=section.pk).exists()

    def test_cannot_delete_section_with_questions(self, admin_client, section, question):
        resp = admin_client.delete(f"/api/practice/sections/{section.pk}/")
        assert resp.status_code == 400
        from practice.models import PracticeSection
        assert PracticeSection.objects.filter(pk=section.pk).exists()


# ── Admin: Questions ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminQuestions:
    def test_create_question(self, admin_client, section):
        resp = admin_client.post(
            f"/api/practice/sections/{section.pk}/questions/",
            {"question_type": "mcq", "title": "New Q"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["question_type"] == "mcq"

    def test_create_fib_question(self, admin_client, section):
        resp = admin_client.post(
            f"/api/practice/sections/{section.pk}/questions/",
            {"question_type": "fib", "title": "FIB Q"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["question_type"] == "fib"

    def test_create_question_idor(self, admin_b_client, section):
        resp = admin_b_client.post(
            f"/api/practice/sections/{section.pk}/questions/",
            {"question_type": "mcq", "title": "X"},
            format="json",
        )
        assert resp.status_code == 404

    def test_get_question_detail(self, admin_client, question, option_correct, option_wrong):
        resp = admin_client.get(f"/api/practice/questions/{question.pk}/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["question"]["title"] == "What is 2 + 2?"
        # Admin sees is_correct in options
        assert len(data["options"]) == 2
        correct = next(o for o in data["options"] if o["is_correct"])
        assert correct["label"] == "A"

    def test_get_question_idor(self, admin_b_client, question):
        resp = admin_b_client.get(f"/api/practice/questions/{question.pk}/")
        assert resp.status_code == 404

    def test_patch_question(self, admin_client, question):
        resp = admin_client.patch(
            f"/api/practice/questions/{question.pk}/",
            {"title": "Updated Title", "is_published": False},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Updated Title"
        assert resp.json()["data"]["is_published"] is False

    def test_delete_question(self, admin_client, question):
        resp = admin_client.delete(f"/api/practice/questions/{question.pk}/")
        assert resp.status_code == 200
        from practice.models import PracticeQuestion
        assert not PracticeQuestion.objects.filter(pk=question.pk).exists()

    def test_question_number_auto_assigned(self, admin_client, section):
        resp1 = admin_client.post(
            f"/api/practice/sections/{section.pk}/questions/",
            {"question_type": "mcq", "title": "Q1"},
            format="json",
        )
        resp2 = admin_client.post(
            f"/api/practice/sections/{section.pk}/questions/",
            {"question_type": "mcq", "title": "Q2"},
            format="json",
        )
        assert resp1.json()["data"]["question_number"] > 0
        assert resp2.json()["data"]["question_number"] > resp1.json()["data"]["question_number"]

    def test_question_number_scoped_per_section_not_global(self, admin_client, section, module):
        from practice.models import PracticeSection
        # Fill section A with a couple of questions first.
        admin_client.post(
            f"/api/practice/sections/{section.pk}/questions/",
            {"question_type": "mcq", "title": "A-Q1"}, format="json",
        )
        admin_client.post(
            f"/api/practice/sections/{section.pk}/questions/",
            {"question_type": "mcq", "title": "A-Q2"}, format="json",
        )
        # A brand-new section's first question must start at 1 — not
        # continue from whatever the table-wide max happened to be.
        other_section = PracticeSection.objects.create(
            name="Other Section", module=module, institution_id=section.institution_id,
        )
        resp = admin_client.post(
            f"/api/practice/sections/{other_section.pk}/questions/",
            {"question_type": "mcq", "title": "B-Q1"}, format="json",
        )
        assert resp.json()["data"]["question_number"] == 1


# ── Admin: MCQ Options ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminOptions:
    def test_list_options(self, admin_client, question, option_correct, option_wrong):
        resp = admin_client.get(f"/api/practice/questions/{question.pk}/options/")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_create_option(self, admin_client, question):
        # Draft, not published — the `question` fixture has no explanation,
        # so publishing it would be blocked by the new publish-gate. These
        # option-CRUD tests care about option mechanics, not publish state.
        question.is_published = False
        question.save(update_fields=["is_published"])
        resp = admin_client.post(
            f"/api/practice/questions/{question.pk}/options/",
            {"text": "Option text", "is_correct": False},
            format="json",
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["label"] == "A"  # Auto-assigned first label

    def test_create_option_label_auto_increments(self, admin_client, question, option_correct):
        question.is_published = False
        question.save(update_fields=["is_published"])
        resp = admin_client.post(
            f"/api/practice/questions/{question.pk}/options/",
            {"text": "Second", "is_correct": False},
            format="json",
        )
        assert resp.json()["data"]["label"] == "B"

    def test_single_correct_enforced(self, admin_client, question, option_correct, option_wrong):
        question.is_published = False
        question.save(update_fields=["is_published"])
        # Mark option_wrong as correct — should clear option_correct
        resp = admin_client.patch(
            f"/api/practice/questions/{question.pk}/options/{option_wrong.pk}/",
            {"is_correct": True},
            format="json",
        )
        assert resp.status_code == 200
        from practice.models import PracticeQuestionOption
        assert PracticeQuestionOption.objects.filter(question=question, is_correct=True).count() == 1
        assert PracticeQuestionOption.objects.get(pk=option_wrong.pk).is_correct is True
        assert PracticeQuestionOption.objects.get(pk=option_correct.pk).is_correct is False

    def test_delete_option(self, admin_client, question, option_correct):
        question.is_published = False
        question.save(update_fields=["is_published"])
        resp = admin_client.delete(
            f"/api/practice/questions/{question.pk}/options/{option_correct.pk}/"
        )
        assert resp.status_code == 200
        from practice.models import PracticeQuestionOption
        assert not PracticeQuestionOption.objects.filter(pk=option_correct.pk).exists()

    def test_list_options_idor(self, admin_b_client, question):
        resp = admin_b_client.get(f"/api/practice/questions/{question.pk}/options/")
        assert resp.status_code == 404


# ── Admin: Image presign ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminImagePresign:
    def test_body_presign_not_configured(self, admin_client, question):
        resp = admin_client.post(
            f"/api/practice/questions/{question.pk}/question-image/presign/",
            {"filename": "diagram.png", "content_type": "image/png"},
            format="json",
        )
        assert resp.status_code == 503

    def test_explanation_presign_not_configured(self, admin_client, question):
        resp = admin_client.post(
            f"/api/practice/questions/{question.pk}/explanation-image/presign/",
            {"filename": "explain.jpg", "content_type": "image/jpeg"},
            format="json",
        )
        assert resp.status_code == 503

    def test_body_presign_invalid_mime(self, admin_client, question):
        resp = admin_client.post(
            f"/api/practice/questions/{question.pk}/question-image/presign/",
            {"filename": "file.exe", "content_type": "application/octet-stream"},
            format="json",
        )
        assert resp.status_code == 400

    def test_presign_idor(self, admin_b_client, question):
        resp = admin_b_client.post(
            f"/api/practice/questions/{question.pk}/question-image/presign/",
            {"filename": "x.png", "content_type": "image/png"},
            format="json",
        )
        assert resp.status_code == 404

    def test_presign_svg_rejected(self, admin_client, question):
        # .svg can carry inline <script>/event-handler payloads — a
        # stored-XSS vector if opened via its CDN URL. Deliberately excluded.
        resp = admin_client.post(
            f"/api/practice/questions/{question.pk}/question-image/presign/",
            {"filename": "diagram.svg", "content_type": "image/svg+xml"},
            format="json",
        )
        assert resp.status_code == 400

    def test_explanation_presign_svg_rejected(self, admin_client, question):
        resp = admin_client.post(
            f"/api/practice/questions/{question.pk}/explanation-image/presign/",
            {"filename": "diagram.svg", "content_type": "image/svg+xml"},
            format="json",
        )
        assert resp.status_code == 400

    def test_presign_extension_mismatch_rejected(self, admin_client, question):
        # Extension not in the allowlist at all, regardless of content_type.
        resp = admin_client.post(
            f"/api/practice/questions/{question.pk}/question-image/presign/",
            {"filename": "payload.html", "content_type": "image/png"},
            format="json",
        )
        assert resp.status_code == 400


# ── Admin: Question image verification (PATCH commit point) ────────────────────

@pytest.mark.django_db
class TestQuestionImageVerification:
    def test_patch_image_key_storage_not_configured(self, admin_client, question):
        # R2 credentials are unset in test settings — verify_uploaded_image
        # raises RuntimeError, same contract as the presign endpoint.
        resp = admin_client.patch(
            f"/api/practice/questions/{question.pk}/",
            {"question_image_key": "uploads/image/some-uuid.png"},
            format="json",
        )
        assert resp.status_code == 503

    @patch("practice.views.scan_image_for_malware")
    @patch("practice.views.verify_uploaded_image")
    def test_patch_image_key_verified_and_saved(self, mock_verify, mock_scan, admin_client, question):
        question.is_published = False
        question.save(update_fields=["is_published"])
        mock_verify.return_value = (2048, None)
        mock_scan.return_value = None
        resp = admin_client.patch(
            f"/api/practice/questions/{question.pk}/",
            {"question_image_key": "uploads/image/some-uuid.png"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["question_image_key"] == "uploads/image/some-uuid.png"
        assert resp.json()["data"]["question_image_size_bytes"] == 2048

    @patch("practice.views.delete_file")
    @patch("practice.views.verify_uploaded_image")
    def test_patch_image_key_rejected_and_cleaned_up(self, mock_verify, mock_delete, admin_client, question):
        mock_verify.return_value = (None, "Image contents do not match a supported image format.")
        resp = admin_client.patch(
            f"/api/practice/questions/{question.pk}/",
            {"question_image_key": "uploads/image/fake.png"},
            format="json",
        )
        assert resp.status_code == 400
        mock_delete.assert_called_once_with("uploads/image/fake.png")
        question.refresh_from_db()
        assert question.question_image_key == ""

    @patch("practice.views.scan_image_for_malware")
    @patch("practice.views.delete_file")
    @patch("practice.views.verify_uploaded_image")
    def test_patch_replacing_image_deletes_old_object(self, mock_verify, mock_delete, mock_scan, admin_client, question):
        question.question_image_key = "uploads/image/old.png"
        question.is_published = False
        question.save(update_fields=["question_image_key", "is_published"])
        mock_verify.return_value = (2048, None)
        mock_scan.return_value = None
        resp = admin_client.patch(
            f"/api/practice/questions/{question.pk}/",
            {"question_image_key": "uploads/image/new.png"},
            format="json",
        )
        assert resp.status_code == 200
        mock_delete.assert_called_once_with("uploads/image/old.png")

    @patch("practice.views.delete_file")
    @patch("practice.views.verify_uploaded_image")
    def test_patch_image_malware_scan_not_configured(self, mock_verify, mock_delete, admin_client, question):
        # verify_uploaded_image passes but CLAMAV_HOST is unset in test
        # settings — scan_image_for_malware raises RuntimeError, fail closed.
        mock_verify.return_value = (2048, None)
        resp = admin_client.patch(
            f"/api/practice/questions/{question.pk}/",
            {"question_image_key": "uploads/image/some-uuid.png"},
            format="json",
        )
        assert resp.status_code == 503

    @patch("practice.views.scan_image_for_malware")
    @patch("practice.views.delete_file")
    @patch("practice.views.verify_uploaded_image")
    def test_patch_image_infected_rejected_and_deleted(self, mock_verify, mock_delete, mock_scan, admin_client, question):
        mock_verify.return_value = (2048, None)
        mock_scan.return_value = "This image failed a security scan and cannot be used."
        resp = admin_client.patch(
            f"/api/practice/questions/{question.pk}/",
            {"question_image_key": "uploads/image/infected.png"},
            format="json",
        )
        assert resp.status_code == 400
        mock_delete.assert_called_once_with("uploads/image/infected.png")
        question.refresh_from_db()
        assert question.question_image_key == ""
        assert question.question_image_size_bytes is None

    @patch("practice.views.scan_image_for_malware")
    @patch("practice.views.delete_file")
    @patch("practice.views.verify_uploaded_image")
    def test_patch_image_over_section_quota_rejected(self, mock_verify, mock_delete, mock_scan, admin_client, section, question):
        from practice.models import PracticeQuestion
        from core.upload_constraints import MAX_BYTES_PER_SECTION
        # Another question in the same section already holds almost the
        # entire quota.
        PracticeQuestion.objects.create(
            section=section, title="Big image holder", question_type="mcq",
            question_image_key="uploads/image/big.png",
            question_image_size_bytes=MAX_BYTES_PER_SECTION - 1024,
        )
        mock_verify.return_value = (2048, None)  # pushes the section over the cap
        mock_scan.return_value = None
        resp = admin_client.patch(
            f"/api/practice/questions/{question.pk}/",
            {"question_image_key": "uploads/image/new.png"},
            format="json",
        )
        assert resp.status_code == 400
        mock_delete.assert_called_once_with("uploads/image/new.png")
        question.refresh_from_db()
        assert question.question_image_key == ""

    @patch("practice.views.delete_file")
    @patch("practice.views.verify_uploaded_image")
    def test_patch_image_verify_transient_failure_not_deleted(self, mock_verify, mock_delete, admin_client, question):
        # Storage itself is unreachable (network blip, R2 hiccup) — the
        # object was never actually examined, so it must be left alone.
        # Regression test: this used to fall through to the "reject and
        # delete" path, destroying a perfectly good upload and turning a
        # retryable 503 into a permanent, misleading "not found" 400 on the
        # next attempt.
        from core.storage import TransientStorageError
        mock_verify.side_effect = TransientStorageError("Could not verify the uploaded image. Please try again.")
        resp = admin_client.patch(
            f"/api/practice/questions/{question.pk}/",
            {"question_image_key": "uploads/image/some-uuid.png"},
            format="json",
        )
        assert resp.status_code == 503
        mock_delete.assert_not_called()
        question.refresh_from_db()
        assert question.question_image_key == ""

    @patch("practice.views.scan_image_for_malware")
    @patch("practice.views.delete_file")
    @patch("practice.views.verify_uploaded_image")
    def test_patch_image_scan_transient_failure_not_deleted(self, mock_verify, mock_delete, mock_scan, admin_client, question):
        # ClamAV unreachable (e.g. OOM-killed, still starting up) — same
        # regression as above but for the malware-scan step: a scanner
        # outage must not be treated as "this file is bad."
        from core.storage import TransientStorageError
        mock_verify.return_value = (2048, None)
        mock_scan.side_effect = TransientStorageError("Could not scan the uploaded image right now. Please try again.")
        resp = admin_client.patch(
            f"/api/practice/questions/{question.pk}/",
            {"question_image_key": "uploads/image/some-uuid.png"},
            format="json",
        )
        assert resp.status_code == 503
        mock_delete.assert_not_called()
        question.refresh_from_db()
        assert question.question_image_key == ""

    @patch("practice.views.scan_image_for_malware")
    @patch("practice.views.verify_uploaded_image")
    def test_patch_image_under_section_quota_allowed(self, mock_verify, mock_scan, admin_client, section, question):
        question.is_published = False
        question.save(update_fields=["is_published"])
        from practice.models import PracticeQuestion
        PracticeQuestion.objects.create(
            section=section, title="Small image holder", question_type="mcq",
            question_image_key="uploads/image/small.png",
            question_image_size_bytes=1024,
        )
        mock_verify.return_value = (2048, None)
        mock_scan.return_value = None
        resp = admin_client.patch(
            f"/api/practice/questions/{question.pk}/",
            {"question_image_key": "uploads/image/new.png"},
            format="json",
        )
        assert resp.status_code == 200


# ── Admin: Publish gate ─────────────────────────────────────────────────────────
# Admin-defined rules a question must satisfy before it can be published:
#  1. Question body has text and/or image.
#  2. MCQ: at least one option, none blank, at least one marked correct.
#     FIB: a non-empty answer.
#  3. An explanation (text and/or image) is present.

@pytest.mark.django_db
class TestQuestionPublishGate:
    def test_publish_blocked_no_question_content(self, admin_client, section, db):
        from practice.models import PracticeQuestion
        q = PracticeQuestion.objects.create(
            section=section, title="Empty", question_type="mcq",
            explanation_text="Because.",
        )
        resp = admin_client.patch(
            f"/api/practice/questions/{q.pk}/", {"is_published": True}, format="json"
        )
        assert resp.status_code == 400
        assert "Question must have text or an image." in resp.json()["errors"]["publish"]

    def test_publish_blocked_mcq_no_options(self, admin_client, section, db):
        from practice.models import PracticeQuestion
        q = PracticeQuestion.objects.create(
            section=section, title="No opts", question_type="mcq",
            question_text="2+2=?", explanation_text="Because.",
        )
        resp = admin_client.patch(
            f"/api/practice/questions/{q.pk}/", {"is_published": True}, format="json"
        )
        assert resp.status_code == 400
        assert "At least 2 options are required." in resp.json()["errors"]["publish"]

    def test_publish_blocked_mcq_no_correct_option(self, admin_client, section, db):
        from practice.models import PracticeQuestion, PracticeQuestionOption
        q = PracticeQuestion.objects.create(
            section=section, title="No correct", question_type="mcq",
            question_text="2+2=?", explanation_text="Because.",
        )
        PracticeQuestionOption.objects.create(question=q, label="A", text="4", is_correct=False)
        resp = admin_client.patch(
            f"/api/practice/questions/{q.pk}/", {"is_published": True}, format="json"
        )
        assert resp.status_code == 400
        assert "At least one option must be marked as the correct answer." in resp.json()["errors"]["publish"]

    def test_publish_blocked_mcq_blank_option_text(self, admin_client, section, db):
        from practice.models import PracticeQuestion, PracticeQuestionOption
        q = PracticeQuestion.objects.create(
            section=section, title="Blank opt", question_type="mcq",
            question_text="2+2=?", explanation_text="Because.",
        )
        PracticeQuestionOption.objects.create(question=q, label="A", text="4", is_correct=True)
        PracticeQuestionOption.objects.create(question=q, label="B", text="  ", is_correct=False)
        resp = admin_client.patch(
            f"/api/practice/questions/{q.pk}/", {"is_published": True}, format="json"
        )
        assert resp.status_code == 400
        assert "All options must have text filled in." in resp.json()["errors"]["publish"]

    def test_publish_blocked_fib_no_answer(self, admin_client, fib_question):
        fib_question.fib_answer = ""
        fib_question.explanation_text = "Because."
        fib_question.save(update_fields=["fib_answer", "explanation_text"])
        resp = admin_client.patch(
            f"/api/practice/questions/{fib_question.pk}/", {"is_published": True}, format="json"
        )
        assert resp.status_code == 400
        assert "A fill-in-the-blank answer is required." in resp.json()["errors"]["publish"]

    def test_publish_blocked_no_explanation(self, admin_client, section, db):
        from practice.models import PracticeQuestion, PracticeQuestionOption
        q = PracticeQuestion.objects.create(
            section=section, title="No explanation", question_type="mcq", question_text="2+2=?",
        )
        PracticeQuestionOption.objects.create(question=q, label="A", text="4", is_correct=True)
        PracticeQuestionOption.objects.create(question=q, label="B", text="3", is_correct=False)
        resp = admin_client.patch(
            f"/api/practice/questions/{q.pk}/", {"is_published": True}, format="json"
        )
        assert resp.status_code == 400
        assert "An explanation (text or image) is required." in resp.json()["errors"]["publish"]

    def test_publish_reports_all_blockers_at_once(self, admin_client, section, db):
        from practice.models import PracticeQuestion
        q = PracticeQuestion.objects.create(section=section, title="Empty", question_type="mcq")
        resp = admin_client.patch(
            f"/api/practice/questions/{q.pk}/", {"is_published": True}, format="json"
        )
        assert resp.status_code == 400
        blockers = resp.json()["errors"]["publish"]
        # content, "at least one option", "at least one correct", explanation —
        # all four surface together so the admin can fix everything in one pass.
        assert len(blockers) == 4

    def test_publish_succeeds_when_mcq_requirements_met(self, admin_client, section, db):
        from practice.models import PracticeQuestion, PracticeQuestionOption
        q = PracticeQuestion.objects.create(
            section=section, title="Complete", question_type="mcq",
            question_text="2+2=?", explanation_text="Basic addition.",
        )
        PracticeQuestionOption.objects.create(question=q, label="A", text="4", is_correct=True)
        PracticeQuestionOption.objects.create(question=q, label="B", text="3", is_correct=False)
        resp = admin_client.patch(
            f"/api/practice/questions/{q.pk}/", {"is_published": True}, format="json"
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_published"] is True

    def test_publish_succeeds_when_fib_requirements_met(self, admin_client, fib_question):
        assert fib_question.fib_answer and fib_question.explanation_text is not None
        fib_question.explanation_text = "The capital is Paris."
        fib_question.is_published = False
        fib_question.save(update_fields=["explanation_text", "is_published"])
        resp = admin_client.patch(
            f"/api/practice/questions/{fib_question.pk}/", {"is_published": True}, format="json"
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_published"] is True

    def test_cannot_unmark_last_correct_option_on_published_question(self, admin_client, section, db):
        from practice.models import PracticeQuestion, PracticeQuestionOption
        q = PracticeQuestion.objects.create(
            section=section, title="Live", question_type="mcq", question_text="2+2=?",
            explanation_text="Basic addition.", is_published=True,
        )
        opt = PracticeQuestionOption.objects.create(question=q, label="A", text="4", is_correct=True)
        PracticeQuestionOption.objects.create(question=q, label="B", text="3", is_correct=False)
        resp = admin_client.patch(
            f"/api/practice/questions/{q.pk}/options/{opt.pk}/", {"is_correct": False}, format="json"
        )
        assert resp.status_code == 400
        assert "publish" in resp.json()["errors"]
        opt.refresh_from_db()
        assert opt.is_correct is True  # rolled back, not silently left half-changed

    def test_cannot_delete_option_below_minimum_from_published_question(self, admin_client, section, db):
        from practice.models import PracticeQuestion, PracticeQuestionOption
        q = PracticeQuestion.objects.create(
            section=section, title="Live", question_type="mcq", question_text="2+2=?",
            explanation_text="Basic addition.", is_published=True,
        )
        opt = PracticeQuestionOption.objects.create(question=q, label="A", text="4", is_correct=True)
        PracticeQuestionOption.objects.create(question=q, label="B", text="3", is_correct=False)
        # Exactly at the 2-option minimum — deleting either one would drop below it.
        resp = admin_client.delete(f"/api/practice/questions/{q.pk}/options/{opt.pk}/")
        assert resp.status_code == 400
        assert PracticeQuestionOption.objects.filter(pk=opt.pk).exists()  # rolled back

    def test_cannot_add_blank_option_to_published_question(self, admin_client, section, db):
        from practice.models import PracticeQuestion, PracticeQuestionOption
        q = PracticeQuestion.objects.create(
            section=section, title="Live", question_type="mcq", question_text="2+2=?",
            explanation_text="Basic addition.", is_published=True,
        )
        PracticeQuestionOption.objects.create(question=q, label="A", text="4", is_correct=True)
        PracticeQuestionOption.objects.create(question=q, label="B", text="3", is_correct=False)
        resp = admin_client.post(
            f"/api/practice/questions/{q.pk}/options/", {"text": "", "is_correct": False}, format="json"
        )
        assert resp.status_code == 400
        assert q.options.count() == 2  # the blank option was not persisted

    def test_cannot_clear_explanation_on_published_question(self, admin_client, section, db):
        from practice.models import PracticeQuestion, PracticeQuestionOption
        q = PracticeQuestion.objects.create(
            section=section, title="Live", question_type="mcq", question_text="2+2=?",
            explanation_text="Basic addition.", is_published=True,
        )
        PracticeQuestionOption.objects.create(question=q, label="A", text="4", is_correct=True)
        PracticeQuestionOption.objects.create(question=q, label="B", text="3", is_correct=False)
        resp = admin_client.patch(
            f"/api/practice/questions/{q.pk}/", {"explanation_text": ""}, format="json"
        )
        assert resp.status_code == 400
        q.refresh_from_db()
        assert q.explanation_text == "Basic addition."  # unchanged

    def test_editing_unrelated_field_on_published_valid_question_still_works(self, admin_client, section, db):
        from practice.models import PracticeQuestion, PracticeQuestionOption
        q = PracticeQuestion.objects.create(
            section=section, title="Live", question_type="mcq", question_text="2+2=?",
            explanation_text="Basic addition.", is_published=True,
        )
        PracticeQuestionOption.objects.create(question=q, label="A", text="4", is_correct=True)
        PracticeQuestionOption.objects.create(question=q, label="B", text="3", is_correct=False)
        resp = admin_client.patch(
            f"/api/practice/questions/{q.pk}/", {"title": "Renamed"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Renamed"


# ── Student: Root hub ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStudentPracticeRoot:
    def test_root_shows_published_only(self, student_client, module, db):
        from practice.models import PracticeModule
        PracticeModule.objects.create(
            name="Hidden Module", institution_id=INSTITUTION_A, is_published=False
        )
        resp = student_client.get("/api/practice/student/")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["data"]["modules"]]
        assert "Quantitative Aptitude" in names
        assert "Hidden Module" not in names

    def test_root_requires_student_role(self, admin_client):
        resp = admin_client.get("/api/practice/student/")
        assert resp.status_code == 403

    def test_root_institution_isolation(self, student_client, db):
        from practice.models import PracticeModule
        PracticeModule.objects.create(
            name="Other Institution Module", institution_id=INSTITUTION_B, is_published=True
        )
        resp = student_client.get("/api/practice/student/")
        names = [m["name"] for m in resp.json()["data"]["modules"]]
        assert "Other Institution Module" not in names


# ── Student: Module view ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStudentModuleView:
    def test_get_published_module(self, student_client, module, section):
        resp = student_client.get(f"/api/practice/student/modules/{module.pk}/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["module"]["name"] == "Quantitative Aptitude"
        assert len(data["sections"]) == 1

    def test_unpublished_module_404(self, student_client, db):
        from practice.models import PracticeModule
        m = PracticeModule.objects.create(
            name="Hidden", institution_id=INSTITUTION_A, is_published=False
        )
        resp = student_client.get(f"/api/practice/student/modules/{m.pk}/")
        assert resp.status_code == 404

    def test_module_idor(self, student_client, db):
        from practice.models import PracticeModule
        other = PracticeModule.objects.create(
            name="Other", institution_id=INSTITUTION_B, is_published=True
        )
        resp = student_client.get(f"/api/practice/student/modules/{other.pk}/")
        assert resp.status_code == 404


# ── Student: Section view ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStudentSectionView:
    def test_get_section_with_questions(self, student_client, section, question):
        resp = student_client.get(f"/api/practice/student/sections/{section.pk}/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["section"]["name"] == "Number Systems"
        assert len(data["questions"]) == 1

    def test_fib_answer_not_exposed(self, student_client, section, fib_question):
        resp = student_client.get(f"/api/practice/student/sections/{section.pk}/")
        assert resp.status_code == 200
        for q in resp.json()["data"]["questions"]:
            assert "fib_answer" not in q

    def test_section_shows_progress_status(self, student_client, section, question):
        resp = student_client.get(f"/api/practice/student/sections/{section.pk}/")
        assert resp.json()["data"]["questions"][0]["progress_status"] == "not_visited"

    def test_unpublished_section_404(self, student_client, db, module):
        from practice.models import PracticeSection
        sec = PracticeSection.objects.create(
            name="Hidden Section", module=module,
            institution_id=INSTITUTION_A, is_published=False
        )
        resp = student_client.get(f"/api/practice/student/sections/{sec.pk}/")
        assert resp.status_code == 404

    def test_section_idor(self, student_client, db):
        from practice.models import PracticeSection
        other_sec = PracticeSection.objects.create(
            name="Other", institution_id=INSTITUTION_B, is_published=True
        )
        resp = student_client.get(f"/api/practice/student/sections/{other_sec.pk}/")
        assert resp.status_code == 404

    def test_section_cache_hit(self, student_client, section, question):
        resp1 = student_client.get(f"/api/practice/student/sections/{section.pk}/")
        resp2 = student_client.get(f"/api/practice/student/sections/{section.pk}/")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]["questions"]) == 1

    def test_section_cache_invalidated_on_question_patch(self, admin_client, student_client, section, question):
        student_client.get(f"/api/practice/student/sections/{section.pk}/")
        # Admin unpublishes the question
        admin_client.patch(f"/api/practice/questions/{question.pk}/", {"is_published": False}, format="json")
        resp = student_client.get(f"/api/practice/student/sections/{section.pk}/")
        # Cache was invalidated; question is now unpublished so not returned
        assert resp.json()["data"]["questions"] == []


# ── Student: Question view ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStudentQuestionView:
    def test_get_question(self, student_client, question, option_correct, option_wrong):
        resp = student_client.get(f"/api/practice/student/questions/{question.pk}/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["question"]["title"] == "What is 2 + 2?"
        assert len(data["options"]) == 2
        # is_correct must not be in student option
        for opt in data["options"]:
            assert "is_correct" not in opt

    def test_fib_answer_not_in_question_view(self, student_client, fib_question):
        resp = student_client.get(f"/api/practice/student/questions/{fib_question.pk}/")
        assert resp.status_code == 200
        assert "fib_answer" not in resp.json()["data"]["question"]

    def test_question_has_prev_next(self, student_client, section):
        from practice.models import PracticeQuestion
        q1 = PracticeQuestion.objects.create(section=section, title="Q1", question_type="mcq", is_published=True, order=1)
        q2 = PracticeQuestion.objects.create(section=section, title="Q2", question_type="mcq", is_published=True, order=2)
        q3 = PracticeQuestion.objects.create(section=section, title="Q3", question_type="mcq", is_published=True, order=3)
        resp = student_client.get(f"/api/practice/student/questions/{q2.pk}/")
        data = resp.json()["data"]
        assert str(data["prev_question_id"]) == str(q1.pk)
        assert str(data["next_question_id"]) == str(q3.pk)

    def test_unpublished_question_404(self, student_client, db, section):
        from practice.models import PracticeQuestion
        q = PracticeQuestion.objects.create(
            section=section, title="Hidden", question_type="mcq", is_published=False
        )
        resp = student_client.get(f"/api/practice/student/questions/{q.pk}/")
        assert resp.status_code == 404

    def test_question_idor(self, student_client, db):
        from practice.models import PracticeSection, PracticeQuestion
        other_sec = PracticeSection.objects.create(
            name="Other", institution_id=INSTITUTION_B, is_published=True
        )
        other_q = PracticeQuestion.objects.create(
            section=other_sec, title="X", question_type="mcq", is_published=True
        )
        resp = student_client.get(f"/api/practice/student/questions/{other_q.pk}/")
        assert resp.status_code == 404


# ── Student: Progress ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStudentProgress:
    def test_mark_visited(self, student_client, question):
        resp = student_client.post(
            f"/api/practice/student/questions/{question.pk}/progress/",
            {"status": "visited"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "visited"

    def test_mark_completed(self, student_client, question):
        resp = student_client.post(
            f"/api/practice/student/questions/{question.pk}/progress/",
            {"status": "completed"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "completed"

    def test_progress_monotone_no_regression(self, student_client, question):
        # Advance to attempted
        student_client.post(
            f"/api/practice/student/questions/{question.pk}/progress/",
            {"status": "attempted"}, format="json"
        )
        # Try to go back to visited — should stay at attempted
        resp = student_client.post(
            f"/api/practice/student/questions/{question.pk}/progress/",
            {"status": "visited"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "attempted"

    def test_invalid_status_400(self, student_client, question):
        resp = student_client.post(
            f"/api/practice/student/questions/{question.pk}/progress/",
            {"status": "unknown_status"},
            format="json",
        )
        assert resp.status_code == 400

    def test_progress_idempotent(self, student_client, question):
        for _ in range(3):
            resp = student_client.post(
                f"/api/practice/student/questions/{question.pk}/progress/",
                {"status": "visited"}, format="json"
            )
            assert resp.status_code == 200
        from practice.models import PracticeQuestionProgress
        assert PracticeQuestionProgress.objects.filter(
            student_id=STUDENT_USER_ID, question=question
        ).count() == 1


# ── Student: Submit MCQ ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStudentSubmit:
    def test_submit_correct_answer(self, student_client, question, option_correct, option_wrong):
        resp = student_client.post(
            f"/api/practice/student/questions/{question.pk}/submit/",
            {"selected_option_ids": [str(option_correct.pk)]},
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_correct"] is True
        assert data["attempt_number"] == 1
        assert str(option_correct.pk) in data["correct_option_ids"]

    def test_submit_wrong_answer(self, student_client, question, option_correct, option_wrong):
        resp = student_client.post(
            f"/api/practice/student/questions/{question.pk}/submit/",
            {"selected_option_ids": [str(option_wrong.pk)]},
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_correct"] is False

    def test_submit_increments_attempt_number(self, student_client, question, option_correct, option_wrong):
        student_client.post(
            f"/api/practice/student/questions/{question.pk}/submit/",
            {"selected_option_ids": [str(option_wrong.pk)]}, format="json"
        )
        resp = student_client.post(
            f"/api/practice/student/questions/{question.pk}/submit/",
            {"selected_option_ids": [str(option_correct.pk)]}, format="json"
        )
        assert resp.json()["data"]["attempt_number"] == 2

    def test_correct_advances_progress_to_completed(self, student_client, question, option_correct, option_wrong):
        student_client.post(
            f"/api/practice/student/questions/{question.pk}/submit/",
            {"selected_option_ids": [str(option_correct.pk)]}, format="json"
        )
        from practice.models import PracticeQuestionProgress
        progress = PracticeQuestionProgress.objects.get(
            student_id=STUDENT_USER_ID, question=question
        )
        assert progress.status == "completed"

    def test_wrong_advances_progress_to_attempted(self, student_client, question, option_correct, option_wrong):
        student_client.post(
            f"/api/practice/student/questions/{question.pk}/submit/",
            {"selected_option_ids": [str(option_wrong.pk)]}, format="json"
        )
        from practice.models import PracticeQuestionProgress
        progress = PracticeQuestionProgress.objects.get(
            student_id=STUDENT_USER_ID, question=question
        )
        assert progress.status == "attempted"

    def test_submit_fib_returns_400(self, student_client, fib_question):
        resp = student_client.post(
            f"/api/practice/student/questions/{fib_question.pk}/submit/",
            {"selected_option_ids": []},
            format="json",
        )
        assert resp.status_code == 400

    def test_submit_empty_options_400(self, student_client, question):
        resp = student_client.post(
            f"/api/practice/student/questions/{question.pk}/submit/",
            {"selected_option_ids": []},
            format="json",
        )
        assert resp.status_code == 400

    def test_submit_invalid_option_id_400(self, student_client, question):
        resp = student_client.post(
            f"/api/practice/student/questions/{question.pk}/submit/",
            {"selected_option_ids": [str(uuid.uuid4())]},
            format="json",
        )
        assert resp.status_code == 400


# ── Student: Reveal answer ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStudentRevealAnswer:
    def test_fib_reveals_answer_and_completes(self, student_client, fib_question):
        resp = student_client.post(
            f"/api/practice/student/questions/{fib_question.pk}/reveal-answer/",
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["fib_answer"] == "Paris"
        from practice.models import PracticeQuestionProgress
        progress = PracticeQuestionProgress.objects.get(
            student_id=STUDENT_USER_ID, question=fib_question
        )
        assert progress.status == "completed"

    def test_mcq_reveal_returns_correct_option_ids(self, student_client, question, option_correct, option_wrong):
        resp = student_client.post(
            f"/api/practice/student/questions/{question.pk}/reveal-answer/",
            format="json",
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "correct_option_ids" in data
        assert str(option_correct.pk) in data["correct_option_ids"]

    def test_mcq_reveal_does_not_change_progress(self, student_client, question, option_correct):
        from practice.models import PracticeQuestionProgress
        student_client.post(
            f"/api/practice/student/questions/{question.pk}/reveal-answer/",
            format="json",
        )
        # For MCQ, reveal must NOT create a progress record (no side effect)
        assert not PracticeQuestionProgress.objects.filter(
            student_id=STUDENT_USER_ID, question=question
        ).exists()

    def test_attempt_info_shown_after_submit(self, student_client, question, option_correct, option_wrong):
        student_client.post(
            f"/api/practice/student/questions/{question.pk}/submit/",
            {"selected_option_ids": [str(option_wrong.pk)]}, format="json"
        )
        resp = student_client.get(f"/api/practice/student/questions/{question.pk}/")
        data = resp.json()["data"]
        assert data["attempt_info"] is not None
        assert data["attempt_info"]["attempt_count"] == 1
        assert data["attempt_info"]["last_is_correct"] is False
