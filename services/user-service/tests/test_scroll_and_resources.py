import uuid
import pytest
from tests.conftest import INSTITUTION_A


@pytest.mark.django_db
class TestScrollConfig:
    def test_get_scroll_config(self, admin_client, db):
        resp = admin_client.get("/api/users/scroll/config/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "is_enabled" in data
        assert "direction" in data

    def test_patch_scroll_config(self, admin_client, db):
        resp = admin_client.patch("/api/users/scroll/config/", {"is_enabled": True, "direction": "right"}, format="json")
        assert resp.status_code == 200
        assert resp.json()["data"]["is_enabled"] is True
        assert resp.json()["data"]["direction"] == "right"

    def test_scroll_config_requires_admin(self, student_client, db):
        resp = student_client.get("/api/users/scroll/config/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestScrollUpdates:
    def test_create_scroll_update(self, admin_client, db):
        resp = admin_client.post("/api/users/scroll/updates/", {
            "text": "New placement drive for CSE batch!",
            "link": "https://example.com",
            "show_new_badge": True,
        }, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["text"] == "New placement drive for CSE batch!"

    def test_list_scroll_updates(self, admin_client, db):
        admin_client.post("/api/users/scroll/updates/", {"text": "Update 1"}, format="json")
        admin_client.post("/api/users/scroll/updates/", {"text": "Update 2"}, format="json")
        resp = admin_client.get("/api/users/scroll/updates/")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_update_scroll_item(self, admin_client, db):
        create_resp = admin_client.post("/api/users/scroll/updates/", {"text": "Original"}, format="json")
        pk = create_resp.json()["data"]["id"]
        resp = admin_client.patch(f"/api/users/scroll/updates/{pk}/", {"text": "Updated"}, format="json")
        assert resp.status_code == 200
        assert resp.json()["data"]["text"] == "Updated"

    def test_delete_scroll_item(self, admin_client, db):
        create_resp = admin_client.post("/api/users/scroll/updates/", {"text": "To delete"}, format="json")
        pk = create_resp.json()["data"]["id"]
        resp = admin_client.delete(f"/api/users/scroll/updates/{pk}/")
        assert resp.status_code == 200

    def test_reorder_scroll_updates(self, admin_client, db):
        r1 = admin_client.post("/api/users/scroll/updates/", {"text": "First"}, format="json").json()["data"]["id"]
        r2 = admin_client.post("/api/users/scroll/updates/", {"text": "Second"}, format="json").json()["data"]["id"]
        resp = admin_client.post("/api/users/scroll/reorder/", {"ids": [r2, r1]}, format="json")
        assert resp.status_code == 200

    def test_empty_text_rejected(self, admin_client, db):
        resp = admin_client.post("/api/users/scroll/updates/", {"text": "  "}, format="json")
        assert resp.status_code == 400

    def test_public_scroll_view(self, anon_client, db):
        resp = anon_client.get("/api/users/scroll/")
        assert resp.status_code == 200
        assert "is_enabled" in resp.json()["data"]


@pytest.mark.django_db
class TestInquiries:
    def test_student_submit_inquiry(self, student_client, student):
        resp = student_client.post("/api/users/student/inquiries/", {
            "message": "This is a test inquiry message with enough characters."
        }, format="json")
        assert resp.status_code == 201

    def test_inquiry_too_short(self, student_client, student):
        resp = student_client.post("/api/users/student/inquiries/", {
            "message": "Too short"
        }, format="json")
        assert resp.status_code == 400

    def test_inquiry_empty_message(self, student_client, student):
        resp = student_client.post("/api/users/student/inquiries/", {"message": ""}, format="json")
        assert resp.status_code == 400

    def test_admin_list_inquiries(self, admin_client, student_client, student, db):
        student_client.post("/api/users/student/inquiries/", {
            "message": "Long enough inquiry message here for testing."
        }, format="json")
        resp = admin_client.get("/api/users/inquiries/")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_admin_mark_inquiry_read(self, admin_client, student_client, student, db):
        inq_resp = student_client.post("/api/users/student/inquiries/", {
            "message": "Long enough inquiry message here for the test."
        }, format="json")
        inq_id = inq_resp.json()["data"]["id"]
        resp = admin_client.patch(f"/api/users/inquiries/{inq_id}/mark-read/")
        assert resp.status_code == 200
        assert resp.json()["data"]["is_read"] is True

    def test_admin_cannot_read_other_institution_inquiry(self, admin_b_client, student_client, student, db):
        inq_resp = student_client.post("/api/users/student/inquiries/", {
            "message": "Long enough inquiry message here for the test."
        }, format="json")
        inq_id = inq_resp.json()["data"]["id"]
        resp = admin_b_client.patch(f"/api/users/inquiries/{inq_id}/mark-read/")
        assert resp.status_code == 404
