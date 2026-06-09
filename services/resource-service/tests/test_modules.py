"""
Tests for general Module / ModuleSection / ModuleUpload endpoints.
Mirrors the coverage previously held in user-service test_scroll_and_resources.py.
"""

import pytest
from tests.conftest import INSTITUTION_A, INSTITUTION_B


@pytest.mark.django_db
class TestModuleAdmin:
    def test_list_modules_creates_system_module(self, admin_client, db):
        resp = admin_client.get("/api/resources/modules/")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert isinstance(results, list)
        # system module should be auto-created
        assert any(m["is_system"] for m in results)

    def test_create_module(self, admin_client, db):
        resp = admin_client.post("/api/resources/modules/", {
            "name": "Interview Prep",
            "is_published": True,
        }, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["name"] == "Interview Prep"

    def test_create_module_empty_name_rejected(self, admin_client, db):
        resp = admin_client.post("/api/resources/modules/", {"name": "  "}, format="json")
        assert resp.status_code == 400

    def test_get_module_detail(self, admin_client, db):
        create_resp = admin_client.post("/api/resources/modules/", {
            "name": "Test Module",
            "is_published": False,
        }, format="json")
        pk = create_resp.json()["data"]["id"]
        resp = admin_client.get(f"/api/resources/modules/{pk}/")
        assert resp.status_code == 200
        payload = resp.json()["data"]
        assert "module" in payload
        assert "sections" in payload
        assert "children" in payload

    def test_delete_non_system_module(self, admin_client, db):
        create_resp = admin_client.post("/api/resources/modules/", {"name": "Deletable"}, format="json")
        pk = create_resp.json()["data"]["id"]
        resp = admin_client.delete(f"/api/resources/modules/{pk}/")
        assert resp.status_code == 200

    def test_cannot_delete_system_module(self, admin_client, db):
        from resources.models import Module
        system_mod = Module.objects.create(
            name="Company Resources",
            is_system=True,
            is_published=True,
            institution_id=INSTITUTION_A,
        )
        resp = admin_client.delete(f"/api/resources/modules/{system_mod.pk}/")
        assert resp.status_code == 403

    def test_create_sub_module(self, admin_client, db):
        parent_resp = admin_client.post("/api/resources/modules/", {"name": "Parent"}, format="json")
        parent_pk = parent_resp.json()["data"]["id"]
        resp = admin_client.post(f"/api/resources/modules/{parent_pk}/children/", {
            "name": "Child Module",
        }, format="json")
        assert resp.status_code == 201

    def test_module_idor_other_institution(self, admin_b_client, db):
        from resources.models import Module
        mod = Module.objects.create(name="Inst A Module", institution_id=INSTITUTION_A)
        resp = admin_b_client.get(f"/api/resources/modules/{mod.pk}/")
        assert resp.status_code == 404

    def test_create_section_in_module(self, admin_client, db):
        module_resp = admin_client.post("/api/resources/modules/", {"name": "Module"}, format="json")
        module_pk = module_resp.json()["data"]["id"]
        resp = admin_client.post(f"/api/resources/modules/{module_pk}/sections/", {
            "name": "Section 1",
        }, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["name"] == "Section 1"

    def test_delete_section_with_no_uploads(self, admin_client, db):
        module_resp = admin_client.post("/api/resources/modules/", {"name": "Module"}, format="json")
        module_pk = module_resp.json()["data"]["id"]
        section_resp = admin_client.post(f"/api/resources/modules/{module_pk}/sections/", {
            "name": "Empty Section"
        }, format="json")
        section_pk = section_resp.json()["data"]["id"]
        resp = admin_client.delete(f"/api/resources/sections/{section_pk}/")
        assert resp.status_code == 200

    def test_patch_module_name(self, admin_client, db):
        create_resp = admin_client.post("/api/resources/modules/", {"name": "Old Name"}, format="json")
        pk = create_resp.json()["data"]["id"]
        resp = admin_client.patch(f"/api/resources/modules/{pk}/", {"name": "New Name"}, format="json")
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "New Name"

    def test_patch_module_publish(self, admin_client, db):
        create_resp = admin_client.post("/api/resources/modules/", {"name": "Mod"}, format="json")
        pk = create_resp.json()["data"]["id"]
        resp = admin_client.patch(f"/api/resources/modules/{pk}/", {"is_published": True}, format="json")
        assert resp.status_code == 200
        assert resp.json()["data"]["is_published"] is True


@pytest.mark.django_db
class TestModuleStudent:
    def test_student_sees_published_modules_own_institution(self, student_client, db):
        from resources.models import Module
        Module.objects.create(name="Published", is_published=True, institution_id=INSTITUTION_A)
        Module.objects.create(name="Unpublished", is_published=False, institution_id=INSTITUTION_A)
        resp = student_client.get("/api/resources/student/modules/")
        assert resp.status_code == 200
        names = [m["name"] for m in resp.json()["data"]]
        assert "Published" in names
        assert "Unpublished" not in names

    def test_student_cannot_access_unpublished_module(self, student_client, db):
        from resources.models import Module
        mod = Module.objects.create(name="Hidden", is_published=False, institution_id=INSTITUTION_A)
        resp = student_client.get(f"/api/resources/student/modules/{mod.pk}/")
        assert resp.status_code == 404

    def test_student_module_detail_returns_sections(self, student_client, db):
        from resources.models import Module, ModuleSection
        mod = Module.objects.create(name="Visible", is_published=True, institution_id=INSTITUTION_A)
        ModuleSection.objects.create(module=mod, name="Sec A", is_published=True, order=0)
        resp = student_client.get(f"/api/resources/student/modules/{mod.pk}/")
        assert resp.status_code == 200
        assert len(resp.json()["data"]["sections"]) == 1

    def test_student_section_detail(self, student_client, db):
        from resources.models import Module, ModuleSection
        mod = Module.objects.create(name="Visible", is_published=True, institution_id=INSTITUTION_A)
        sec = ModuleSection.objects.create(module=mod, name="Sec A", is_published=True, order=0)
        resp = student_client.get(f"/api/resources/student/modules/{mod.pk}/sections/{sec.pk}/")
        assert resp.status_code == 200
        payload = resp.json()["data"]
        assert "module" in payload
        assert "section" in payload
        assert "uploads" in payload

    def test_student_cannot_access_admin_module_endpoint(self, student_client, db):
        resp = student_client.get("/api/resources/modules/")
        assert resp.status_code == 403
