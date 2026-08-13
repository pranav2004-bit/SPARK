import uuid
import pytest
from unittest.mock import patch
from tests.conftest import INSTITUTION_A, INSTITUTION_B


@pytest.mark.django_db
class TestCompanyListCreate:
    def test_list_companies(self, admin_client, company):
        resp = admin_client.get("/api/resources/companies/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_list_requires_auth(self, anon_client):
        resp = anon_client.get("/api/resources/companies/")
        assert resp.status_code == 401

    def test_student_cannot_list_admin_companies(self, student_client):
        resp = student_client.get("/api/resources/companies/")
        assert resp.status_code == 403

    def test_create_company(self, admin_client, db):
        resp = admin_client.post("/api/resources/companies/", {"company_name": "Wipro"}, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["company_name"] == "Wipro"

    def test_create_company_duplicate_name(self, admin_client, company):
        resp = admin_client.post("/api/resources/companies/", {"company_name": "TCS"}, format="json")
        assert resp.status_code == 400

    def test_create_company_case_insensitive_duplicate(self, admin_client, company):
        resp = admin_client.post("/api/resources/companies/", {"company_name": "tcs"}, format="json")
        assert resp.status_code == 400

    def test_admin_b_cannot_see_institution_a_companies(self, admin_b_client, company):
        resp = admin_b_client.get("/api/resources/companies/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_list_uses_cache(self, admin_client, company):
        resp1 = admin_client.get("/api/resources/companies/")
        resp2 = admin_client.get("/api/resources/companies/")
        assert resp1.status_code == 200
        assert resp2.status_code == 200

    def test_create_invalidates_cache(self, admin_client, db):
        admin_client.get("/api/resources/companies/")
        admin_client.post("/api/resources/companies/", {"company_name": "NewCo"}, format="json")
        resp = admin_client.get("/api/resources/companies/")
        assert resp.json()["count"] == 1


@pytest.mark.django_db
class TestCompanyDetail:
    def test_get_company(self, admin_client, company):
        resp = admin_client.get(f"/api/resources/companies/{company.pk}/")
        assert resp.status_code == 200
        assert resp.json()["data"]["company_name"] == "TCS"

    def test_get_company_other_institution_404(self, admin_b_client, company):
        resp = admin_b_client.get(f"/api/resources/companies/{company.pk}/")
        assert resp.status_code == 404

    def test_patch_company(self, admin_client, company):
        resp = admin_client.patch(f"/api/resources/companies/{company.pk}/", {
            "company_name": "TCS Updated"
        }, format="json")
        assert resp.status_code == 200
        assert resp.json()["data"]["company_name"] == "TCS Updated"

    def test_delete_company_no_sections(self, admin_client, company):
        resp = admin_client.delete(f"/api/resources/companies/{company.pk}/")
        assert resp.status_code == 200

    def test_delete_company_with_sections_fails(self, admin_client, company, section):
        resp = admin_client.delete(f"/api/resources/companies/{company.pk}/")
        assert resp.status_code == 400

    def test_toggle_publish(self, admin_client, company):
        assert company.is_published is False
        resp = admin_client.patch(f"/api/resources/companies/{company.pk}/toggle-publish/")
        assert resp.status_code == 200
        assert resp.json()["data"]["is_published"] is True
        resp2 = admin_client.patch(f"/api/resources/companies/{company.pk}/toggle-publish/")
        assert resp2.json()["data"]["is_published"] is False


@pytest.mark.django_db
class TestSections:
    def test_create_section(self, admin_client, company):
        resp = admin_client.post(f"/api/resources/companies/{company.pk}/sections/", {
            "section_name": "Technical"
        }, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["section_name"] == "Technical"

    def test_create_section_duplicate_name(self, admin_client, company, section):
        resp = admin_client.post(f"/api/resources/companies/{company.pk}/sections/", {
            "section_name": "Aptitude"
        }, format="json")
        assert resp.status_code == 400

    def test_list_sections(self, admin_client, company, section):
        resp = admin_client.get(f"/api/resources/companies/{company.pk}/sections/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_delete_empty_section(self, admin_client, company, section):
        resp = admin_client.delete(f"/api/resources/companies/{company.pk}/sections/{section.pk}/")
        assert resp.status_code == 200

    def test_delete_section_with_uploads_fails(self, admin_client, company, section, upload):
        resp = admin_client.delete(f"/api/resources/companies/{company.pk}/sections/{section.pk}/")
        assert resp.status_code == 400

    def test_section_idor(self, admin_b_client, company, section):
        resp = admin_b_client.get(f"/api/resources/companies/{company.pk}/sections/{section.pk}/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestUploads:
    def test_list_uploads(self, admin_client, company, section, upload):
        resp = admin_client.get(f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_add_link_upload(self, admin_client, company, section):
        resp = admin_client.post(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/add-link/",
            {"upload_type": "video_link", "file_url": "https://youtube.com/watch?v=abc123"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["upload_type"] == "video_link"

    def test_add_invalid_link_type(self, admin_client, company, section):
        resp = admin_client.post(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/add-link/",
            {"upload_type": "pdf", "file_url": "https://example.com/file.pdf"},
            format="json",
        )
        assert resp.status_code == 400

    def test_presign_storage_not_configured(self, admin_client, company, section):
        resp = admin_client.post(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/presign/",
            {"filename": "test.pdf", "content_type": "application/pdf", "upload_type": "pdf"},
            format="json",
        )
        assert resp.status_code == 503

    def test_presign_wrong_extension(self, admin_client, company, section):
        resp = admin_client.post(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/presign/",
            {"filename": "test.exe", "content_type": "application/pdf", "upload_type": "pdf"},
            format="json",
        )
        assert resp.status_code == 400

    def test_presign_dropped_extensions_rejected(self, admin_client, company, section):
        """.svg (XSS vector), .wav (size mismatch) and .avi/.mov/.mkv (unplayable
        in-browser) were deliberately dropped from the allowlist."""
        cases = [
            ("logo.svg", "image/svg+xml", "image"),
            ("recording.wav", "audio/wav", "audio"),
            ("clip.avi", "video/avi", "video"),
            ("clip.mov", "video/quicktime", "video"),
            ("clip.mkv", "video/x-matroska", "video"),
        ]
        for filename, content_type, upload_type in cases:
            resp = admin_client.post(
                f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/presign/",
                {"filename": filename, "content_type": content_type, "upload_type": upload_type},
                format="json",
            )
            assert resp.status_code == 400, filename

    def test_presign_mime_type_mismatch(self, admin_client, company, section):
        resp = admin_client.post(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/presign/",
            {"filename": "report.pdf", "content_type": "text/html", "upload_type": "pdf"},
            format="json",
        )
        assert resp.status_code == 400

    def test_confirm_storage_not_configured(self, admin_client, company, section):
        # R2 credentials are unset in test settings — verify_uploaded_object
        # raises RuntimeError, same contract as the presign endpoint.
        resp = admin_client.post(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/confirm/",
            {
                "file_key": "uploads/pdf/some-uuid.pdf",
                "original_filename": "report.pdf",
                "file_size_bytes": 2048,
                "upload_type": "pdf",
            },
            format="json",
        )
        assert resp.status_code == 503

    @patch("resources.tasks.scan_uploaded_file.delay")
    @patch("core.storage.verify_uploaded_object")
    def test_confirm_upload(self, mock_verify, mock_scan_delay, admin_client, company, section):
        mock_verify.return_value = (2048, None)
        resp = admin_client.post(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/confirm/",
            {
                "file_key": "uploads/pdf/some-uuid.pdf",
                "original_filename": "report.pdf",
                "file_size_bytes": 2048,
                "upload_type": "pdf",
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["upload_type"] == "pdf"
        # real HEAD size is trusted, not the client-reported value
        assert resp.json()["data"]["file_size_bytes"] == 2048
        assert resp.json()["data"]["scan_status"] == "pending"
        mock_scan_delay.assert_called_once()

    @patch("core.storage.delete_file")
    @patch("core.storage.verify_uploaded_object")
    def test_confirm_rejects_oversized_or_mismatched_file(self, mock_verify, mock_delete, admin_client, company, section):
        # Server-side ground truth (HEAD + magic bytes) rejects the object —
        # e.g. real size exceeds the cap, or bytes don't match the claimed type.
        mock_verify.return_value = (None, "File exceeds the 25 MB limit for 'pdf'.")
        resp = admin_client.post(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/confirm/",
            {
                "file_key": "uploads/pdf/some-uuid.pdf",
                "original_filename": "report.pdf",
                "file_size_bytes": 2048,
                "upload_type": "pdf",
            },
            format="json",
        )
        assert resp.status_code == 400
        mock_delete.assert_called_once_with("uploads/pdf/some-uuid.pdf")
        from resources.models import Upload
        assert not Upload.objects.filter(file_url="uploads/pdf/some-uuid.pdf").exists()

    @patch("core.storage.delete_file")
    @patch("core.storage.verify_uploaded_object")
    def test_confirm_rejects_when_object_never_uploaded(self, mock_verify, mock_delete, admin_client, company, section):
        mock_verify.return_value = (None, "File was not found in storage. Upload it before confirming.")
        resp = admin_client.post(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/confirm/",
            {
                "file_key": "uploads/pdf/never-uploaded.pdf",
                "original_filename": "report.pdf",
                "file_size_bytes": 2048,
                "upload_type": "pdf",
            },
            format="json",
        )
        assert resp.status_code == 400

    @patch("core.storage.delete_file")
    @patch("core.storage.verify_uploaded_object")
    def test_confirm_rejects_over_section_quota(self, mock_verify, mock_delete, admin_client, company, section, db):
        from resources.models import Upload
        from core.upload_constraints import MAX_BYTES_PER_SECTION
        Upload.objects.create(
            section=section, upload_type="pdf", file_url="uploads/pdf/big1.pdf",
            file_size_bytes=MAX_BYTES_PER_SECTION - 1024, scan_status="clean",
        )
        mock_verify.return_value = (2048, None)  # pushes total over the cap
        resp = admin_client.post(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/confirm/",
            {
                "file_key": "uploads/pdf/some-uuid.pdf",
                "original_filename": "report.pdf",
                "file_size_bytes": 2048,
                "upload_type": "pdf",
            },
            format="json",
        )
        assert resp.status_code == 400
        mock_delete.assert_called_once_with("uploads/pdf/some-uuid.pdf")

    def test_add_link_is_immediately_clean(self, admin_client, company, section):
        resp = admin_client.post(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/add-link/",
            {"upload_type": "video_link", "file_url": "https://youtube.com/watch?v=xyz"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["scan_status"] == "clean"

    def test_rename_upload(self, admin_client, company, section, upload):
        resp = admin_client.patch(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/{upload.pk}/",
            {"original_filename": "renamed.pdf"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["original_filename"] == "renamed.pdf"

    def test_rename_empty_name(self, admin_client, company, section, upload):
        resp = admin_client.patch(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/{upload.pk}/",
            {"original_filename": "  "},
            format="json",
        )
        assert resp.status_code == 400

    @patch("resources.tasks.async_delete_file.delay")
    def test_delete_upload_queues_task(self, mock_delay, admin_client, company, section, upload):
        resp = admin_client.delete(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/{upload.pk}/"
        )
        assert resp.status_code == 200
        mock_delay.assert_called_once_with(upload.file_url)

    def test_upload_idor(self, admin_b_client, company, section, upload):
        resp = admin_b_client.get(
            f"/api/resources/companies/{company.pk}/sections/{section.pk}/uploads/"
        )
        assert resp.status_code == 404


@pytest.mark.django_db
class TestStudentCompanyViews:
    def test_student_list_published_only(self, student_client, company, published_company):
        resp = student_client.get("/api/resources/student/companies/")
        assert resp.status_code == 200
        company_names = [c["company_name"] for c in resp.json()["results"]]
        assert "Infosys" in company_names
        assert "TCS" not in company_names

    def test_student_detail_published(self, student_client, published_company):
        resp = student_client.get(f"/api/resources/student/companies/{published_company.pk}/")
        assert resp.status_code == 200

    def test_student_detail_unpublished_404(self, student_client, company):
        resp = student_client.get(f"/api/resources/student/companies/{company.pk}/")
        assert resp.status_code == 404

    def test_student_sections_published_company(self, student_client, published_company, db):
        from resources.models import Section
        Section.objects.create(company=published_company, section_name="HR Round")
        resp = student_client.get(f"/api/resources/student/companies/{published_company.pk}/sections/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_student_uploads_published_company(self, student_client, published_company, db):
        from resources.models import Section, Upload
        sec = Section.objects.create(company=published_company, section_name="Tech")
        Upload.objects.create(section=sec, upload_type="external_link", file_url="https://example.com", scan_status="clean")
        resp = student_client.get(
            f"/api/resources/student/companies/{published_company.pk}/sections/{sec.pk}/uploads/"
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_student_does_not_see_unscanned_upload(self, student_client, published_company, db):
        from resources.models import Section, Upload
        sec = Section.objects.create(company=published_company, section_name="Tech")
        Upload.objects.create(
            section=sec, upload_type="pdf", file_url="uploads/pdf/pending.pdf",
            original_filename="pending.pdf", file_size_bytes=1024, scan_status="pending",
        )
        resp = student_client.get(
            f"/api/resources/student/companies/{published_company.pk}/sections/{sec.pk}/uploads/"
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_student_institution_idor(self, admin_b_client, db):
        from resources.models import Company
        Company.objects.create(company_name="InstitutionB Co", institution_id=INSTITUTION_B, is_published=True)
        resp = admin_b_client.get("/api/resources/companies/")
        assert resp.json()["count"] == 1
        resp_a_view = APIClient()
        from tests.conftest import _make_token, STUDENT_USER_ID
        resp_a_view.credentials(HTTP_AUTHORIZATION=f"Bearer {_make_token(STUDENT_USER_ID, 'student', INSTITUTION_A)}")
        student_resp = resp_a_view.get("/api/resources/student/companies/")
        assert student_resp.json()["count"] == 0


from rest_framework.test import APIClient
