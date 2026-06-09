import uuid
import pytest
from tests.conftest import INSTITUTION_A, INSTITUTION_B


@pytest.mark.django_db
class TestBatchListCreate:
    def test_list_batches_as_admin(self, admin_client, batch):
        resp = admin_client.get("/api/users/batches/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["batch_name"] == "Batch 2024"

    def test_list_batches_requires_auth(self, anon_client):
        resp = anon_client.get("/api/users/batches/")
        assert resp.status_code == 401

    def test_list_batches_student_forbidden(self, student_client):
        resp = student_client.get("/api/users/batches/")
        assert resp.status_code == 403

    def test_create_batch(self, admin_client, db):
        resp = admin_client.post("/api/users/batches/", {"batch_name": "New Batch"}, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["batch_name"] == "New Batch"
        assert resp.json()["data"]["student_count"] == 0

    def test_create_batch_duplicate_name_case_insensitive(self, admin_client, batch):
        resp = admin_client.post("/api/users/batches/", {"batch_name": "batch 2024"}, format="json")
        assert resp.status_code == 400

    def test_create_batch_empty_name(self, admin_client, db):
        resp = admin_client.post("/api/users/batches/", {"batch_name": "  "}, format="json")
        assert resp.status_code == 400

    def test_admin_cannot_see_other_institution_batches(self, admin_client, batch_b):
        resp = admin_client.get("/api/users/batches/")
        assert resp.status_code == 200
        batch_names = [b["batch_name"] for b in resp.json()["data"]]
        assert "Batch B 2024" not in batch_names

    def test_super_admin_sees_all_batches(self, super_admin_client, batch, batch_b):
        resp = super_admin_client.get("/api/users/batches/")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2


@pytest.mark.django_db
class TestBatchDetail:
    def test_get_batch(self, admin_client, batch):
        resp = admin_client.get(f"/api/users/batches/{batch.pk}/")
        assert resp.status_code == 200
        assert resp.json()["data"]["batch_name"] == "Batch 2024"

    def test_get_batch_other_institution_returns_404(self, admin_client, batch_b):
        resp = admin_client.get(f"/api/users/batches/{batch_b.pk}/")
        assert resp.status_code == 404

    def test_patch_batch(self, admin_client, batch):
        resp = admin_client.patch(f"/api/users/batches/{batch.pk}/", {"batch_name": "Batch Updated"}, format="json")
        assert resp.status_code == 200
        assert resp.json()["data"]["batch_name"] == "Batch Updated"

    def test_delete_batch_without_students(self, admin_client, batch):
        resp = admin_client.delete(f"/api/users/batches/{batch.pk}/")
        assert resp.status_code == 200

    def test_delete_batch_with_students_fails(self, admin_client, batch, student):
        resp = admin_client.delete(f"/api/users/batches/{batch.pk}/")
        assert resp.status_code == 400
        assert "existing students" in resp.json()["message"]

    def test_batch_student_count_annotation(self, admin_client, batch, student):
        resp = admin_client.get(f"/api/users/batches/{batch.pk}/")
        assert resp.json()["data"]["student_count"] == 1
