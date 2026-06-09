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

    def test_confirm_upload(self, admin_client, company, section):
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
        Upload.objects.create(section=sec, upload_type="external_link", file_url="https://example.com")
        resp = student_client.get(
            f"/api/resources/student/companies/{published_company.pk}/sections/{sec.pk}/uploads/"
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

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
