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

    def test_create_batch_forbidden_for_admin(self, admin_client, db):
        """Admin is read/query-only (2026-08-19) — batch creation is IT-exclusive."""
        resp = admin_client.post("/api/users/batches/", {"batch_name": "New Batch"}, format="json")
        assert resp.status_code == 403

    def test_create_batch_forbidden_for_super_admin(self, super_admin_client, db):
        resp = super_admin_client.post("/api/users/batches/", {"batch_name": "New Batch"}, format="json")
        assert resp.status_code == 403

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

    def test_patch_batch_forbidden_for_admin(self, admin_client, batch):
        """Admin is read/query-only (2026-08-19) — batch updates are IT-exclusive."""
        resp = admin_client.patch(f"/api/users/batches/{batch.pk}/", {"batch_name": "Batch Updated"}, format="json")
        assert resp.status_code == 403

    def test_delete_batch_forbidden_for_admin(self, admin_client, batch):
        resp = admin_client.delete(f"/api/users/batches/{batch.pk}/")
        assert resp.status_code == 403

    def test_batch_student_count_annotation(self, admin_client, batch, student):
        resp = admin_client.get(f"/api/users/batches/{batch.pk}/")
        assert resp.json()["data"]["student_count"] == 1


# ── Batches/Students CRUD is exclusive to IT (revised 2026-08-19). Admin and ──
# Super Admin briefly had equal write access ("shared access", 2026-08-19);
# that was reversed the same day — Admin/Super Admin keep read-only access
# (tested above), IT owns all create/update/delete.

@pytest.mark.django_db
class TestBatchListCreateIT:
    def test_list_batches_as_it(self, it_client, batch):
        resp = it_client.get("/api/users/batches/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["batch_name"] == "Batch 2024"

    def test_create_batch_as_it(self, it_client, db):
        resp = it_client.post("/api/users/batches/", {"batch_name": "IT Created Batch"}, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["batch_name"] == "IT Created Batch"

    def test_create_batch_duplicate_name_case_insensitive(self, it_client, batch):
        resp = it_client.post("/api/users/batches/", {"batch_name": "batch 2024"}, format="json")
        assert resp.status_code == 400

    def test_create_batch_empty_name(self, it_client, db):
        resp = it_client.post("/api/users/batches/", {"batch_name": "  "}, format="json")
        assert resp.status_code == 400

    def test_it_cannot_see_other_institution_batches(self, it_client, batch_b):
        resp = it_client.get("/api/users/batches/")
        assert resp.status_code == 200
        batch_names = [b["batch_name"] for b in resp.json()["data"]]
        assert "Batch B 2024" not in batch_names


@pytest.mark.django_db
class TestBatchDetailIT:
    def test_get_batch_as_it(self, it_client, batch):
        resp = it_client.get(f"/api/users/batches/{batch.pk}/")
        assert resp.status_code == 200
        assert resp.json()["data"]["batch_name"] == "Batch 2024"

    def test_get_batch_other_institution_returns_404_for_it(self, it_client, batch_b):
        resp = it_client.get(f"/api/users/batches/{batch_b.pk}/")
        assert resp.status_code == 404

    def test_patch_batch_as_it(self, it_client, batch):
        resp = it_client.patch(f"/api/users/batches/{batch.pk}/", {"batch_name": "IT Updated"}, format="json")
        assert resp.status_code == 200
        assert resp.json()["data"]["batch_name"] == "IT Updated"

    def test_delete_batch_as_it(self, it_client, batch):
        resp = it_client.delete(f"/api/users/batches/{batch.pk}/")
        assert resp.status_code == 200

    def test_delete_batch_with_students_fails_for_it(self, it_client, batch, student):
        resp = it_client.delete(f"/api/users/batches/{batch.pk}/")
        assert resp.status_code == 400
        assert "existing students" in resp.json()["message"]


# ── GET /batches/<id>/students/ — read-only, shared by Admin/Super Admin/IT ──
# alike (unaffected by the CRUD-exclusivity change: this endpoint never wrote).

@pytest.mark.django_db
class TestBatchStudentsView:
    def test_admin_lists_students_in_batch(self, admin_client, batch, student):
        resp = admin_client.get(f"/api/users/batches/{batch.pk}/students/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["results"][0]["student_id"] == "STU001"

    def test_it_lists_students_in_batch(self, it_client, batch, student):
        resp = it_client.get(f"/api/users/batches/{batch.pk}/students/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_admin_cannot_list_students_in_other_institution_batch(self, admin_client, batch_b):
        resp = admin_client.get(f"/api/users/batches/{batch_b.pk}/students/")
        assert resp.status_code == 404

    def test_student_forbidden(self, student_client, batch):
        resp = student_client.get(f"/api/users/batches/{batch.pk}/students/")
        assert resp.status_code == 403


# ── departments= (plural, comma-separated) filter, added 2026-08-27 for the
# admin Assign page's live "students attending this assessment" preview
# count. Matching must be case-insensitive and mirror assessment-service's
# snapshot_roster_and_allocate (assessments/allocation.py) exactly, since
# this count is a promise about what that function will actually allocate.

@pytest.mark.django_db
class TestBatchStudentsMultiDepartmentFilter:
    def _make_students(self, batch, departments):
        from users.models import Student
        for i, dept in enumerate(departments):
            Student.objects.create(
                user_id=uuid.uuid4(), student_id=f"STU{i:03d}", department=dept,
                batch=batch, institution_id=INSTITUTION_A,
            )

    def test_matches_only_listed_departments(self, admin_client, batch):
        self._make_students(batch, ["CSE", "CSD", "ECE", "CSE"])
        resp = admin_client.get(f"/api/users/batches/{batch.pk}/students/?departments=CSE,CSD&page_size=1")
        assert resp.status_code == 200
        assert resp.json()["count"] == 3  # 2 CSE + 1 CSD, ECE excluded

    def test_case_insensitive(self, admin_client, batch):
        self._make_students(batch, ["CSE", "ece"])
        resp = admin_client.get(f"/api/users/batches/{batch.pk}/students/?departments=cse,ECE")
        assert resp.json()["count"] == 2

    def test_empty_departments_param_returns_everyone(self, admin_client, batch):
        self._make_students(batch, ["CSE", "ECE", "MECH"])
        resp = admin_client.get(f"/api/users/batches/{batch.pk}/students/?departments=")
        assert resp.json()["count"] == 3

    def test_no_match_returns_zero_not_an_error(self, admin_client, batch):
        self._make_students(batch, ["CSE"])
        resp = admin_client.get(f"/api/users/batches/{batch.pk}/students/?departments=MECH")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
