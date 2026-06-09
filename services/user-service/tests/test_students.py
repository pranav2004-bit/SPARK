import uuid
from io import StringIO

import pytest
from django.core.management import call_command

from tests.conftest import INSTITUTION_A, INSTITUTION_B, STUDENT_USER_ID


@pytest.mark.django_db
class TestStudentListCreate:
    def test_list_students_as_admin(self, admin_client, student):
        resp = admin_client.get("/api/users/students/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["student_id"] == "STU001"

    def test_list_requires_auth(self, anon_client):
        resp = anon_client.get("/api/users/students/")
        assert resp.status_code == 401

    def test_student_cannot_list_all_students(self, student_client):
        resp = student_client.get("/api/users/students/")
        assert resp.status_code == 403

    def test_create_student(self, admin_client, batch):
        resp = admin_client.post("/api/users/students/", {
            "student_id": "STU999",
            "department": "ECE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["student_id"] == "STU999"

    def test_create_student_uppercase_normalization(self, admin_client, batch):
        resp = admin_client.post("/api/users/students/", {
            "student_id": "stu123",
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["student_id"] == "STU123"

    def test_create_student_duplicate_id(self, admin_client, batch, student):
        resp = admin_client.post("/api/users/students/", {
            "student_id": "STU001",
            "department": "ECE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 400

    def test_create_student_wrong_institution_batch(self, admin_client, batch_b):
        resp = admin_client.post("/api/users/students/", {
            "student_id": "STU500",
            "department": "CSE",
            "batch_id": str(batch_b.pk),
        }, format="json")
        assert resp.status_code == 400

    def test_admin_cannot_see_other_institution_students(self, admin_b_client, student):
        resp = admin_b_client.get("/api/users/students/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_super_admin_sees_all_students(self, super_admin_client, student):
        resp = super_admin_client.get("/api/users/students/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_search_filter(self, admin_client, student):
        resp = admin_client.get("/api/users/students/?search=STU001")
        assert resp.json()["count"] == 1
        resp2 = admin_client.get("/api/users/students/?search=NOMATCH")
        assert resp2.json()["count"] == 0

    def test_department_filter(self, admin_client, student):
        resp = admin_client.get("/api/users/students/?department=CSE")
        assert resp.json()["count"] == 1
        resp2 = admin_client.get("/api/users/students/?department=MECH")
        assert resp2.json()["count"] == 0


@pytest.mark.django_db
class TestStudentDetail:
    def test_get_student(self, admin_client, student):
        resp = admin_client.get(f"/api/users/students/{student.pk}/")
        assert resp.status_code == 200
        assert resp.json()["data"]["student_id"] == "STU001"

    def test_get_student_other_institution_404(self, admin_b_client, student):
        resp = admin_b_client.get(f"/api/users/students/{student.pk}/")
        assert resp.status_code == 404

    def test_patch_student(self, admin_client, student, batch):
        resp = admin_client.patch(f"/api/users/students/{student.pk}/", {
            "fullname": "John Doe",
            "college_email_id": "john@college.edu",
        }, format="json")
        assert resp.status_code == 200
        assert resp.json()["data"]["fullname"] == "John Doe"

    def test_hard_delete_student(self, admin_client, student):
        pk = student.pk
        resp = admin_client.delete(f"/api/users/students/{pk}/")
        assert resp.status_code == 200
        # Student is permanently removed from the database
        from users.models import Student
        assert not Student.objects.filter(pk=pk).exists()

    def test_hard_delete_other_institution_student_404(self, admin_b_client, student):
        resp = admin_b_client.delete(f"/api/users/students/{student.pk}/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestStudentToggleStatus:
    def test_toggle_status(self, admin_client, student):
        assert student.is_active is True
        resp = admin_client.patch(f"/api/users/students/{student.pk}/toggle-status/")
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False

    def test_toggle_wrong_institution_404(self, admin_b_client, student):
        resp = admin_b_client.patch(f"/api/users/students/{student.pk}/toggle-status/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestStudentMe:
    def test_student_get_own_profile(self, student_client, student):
        resp = student_client.get("/api/users/me/")
        assert resp.status_code == 200
        assert resp.json()["data"]["student_id"] == "STU001"

    def test_student_not_found_returns_404(self, student_client, db):
        resp = student_client.get("/api/users/me/")
        assert resp.status_code == 404

    def test_student_patch_profile(self, student_client, student):
        resp = student_client.patch("/api/users/me/", {
            "fullname": "Alice Smith",
            "college_email_id": "alice@college.edu",
        }, format="json")
        assert resp.status_code == 200
        assert resp.json()["data"]["fullname"] == "Alice Smith"

    def test_profile_completion_flag(self, student_client, student):
        assert student.is_profile_completed is False
        student_client.put("/api/users/me/", {
            "fullname": "Alice Smith",
            "college_email_id": "alice@college.edu",
        }, format="json")
        student.refresh_from_db()
        assert student.is_profile_completed is True

    def test_admin_cannot_access_me(self, admin_client, student):
        resp = admin_client.get("/api/users/me/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestBulkStudentImport:
    def test_bulk_import_basic(self, admin_client, batch):
        resp = admin_client.post("/api/users/students/import/", {
            "student_ids": ["B001", "B002", "B003"],
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["created"] == 3
        assert data["rejected"] == 0

    def test_bulk_import_max_limit(self, admin_client, batch):
        ids = [f"S{i:04d}" for i in range(1001)]
        resp = admin_client.post("/api/users/students/import/", {
            "student_ids": ids,
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 400

    def test_bulk_import_duplicates_skipped(self, admin_client, batch, student):
        resp = admin_client.post("/api/users/students/import/", {
            "student_ids": ["STU001", "NEW001"],
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["created"] == 1
        assert data["rejected"] == 1

    def test_bulk_import_within_file_duplicates(self, admin_client, batch):
        resp = admin_client.post("/api/users/students/import/", {
            "student_ids": ["DUP001", "DUP001"],
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        data = resp.json()["data"]
        assert data["created"] == 1
        assert data["rejected"] == 1

    def test_bulk_import_missing_department(self, admin_client, batch):
        resp = admin_client.post("/api/users/students/import/", {
            "student_ids": ["X001"],
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 400

    def test_bulk_import_wrong_institution_batch(self, admin_client, batch_b):
        resp = admin_client.post("/api/users/students/import/", {
            "student_ids": ["X001"],
            "department": "CSE",
            "batch_id": str(batch_b.pk),
        }, format="json")
        assert resp.status_code == 400

    def test_bulk_import_empty_ids_rejected(self, admin_client, batch):
        resp = admin_client.post("/api/users/students/import/", {
            "student_ids": ["", "VALID001"],
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        data = resp.json()["data"]
        assert data["created"] == 1
        assert data["rejected"] == 1

    def test_bulk_import_invalid_list_type(self, admin_client, batch):
        resp = admin_client.post("/api/users/students/import/", {
            "student_ids": "NOT_A_LIST",
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 400


# ── Management command: cleanup_ghost_students ────────────────────────────────

@pytest.mark.django_db
class TestCleanupGhostStudentsCommand:

    def _make_ghost(self, batch, student_id="GHOST01"):
        """Create a student that is inactive (simulates a legacy soft-delete ghost)."""
        from users.models import Student
        return Student.objects.create(
            user_id=uuid.uuid4(),
            student_id=student_id,
            department="CSE",
            batch=batch,
            institution_id=INSTITUTION_A,
            is_active=False,
        )

    def test_dry_run_lists_ghost_and_does_not_delete(self, batch):
        ghost = self._make_ghost(batch)
        out = StringIO()
        call_command("cleanup_ghost_students", stdout=out)
        output = out.getvalue()

        assert "GHOST01" in output
        assert "DRY RUN" in output

        # Record must still exist — dry run never deletes.
        from users.models import Student
        assert Student.objects.filter(pk=ghost.pk).exists()

    def test_execute_permanently_deletes_ghost(self, batch):
        ghost = self._make_ghost(batch)
        pk = ghost.pk
        out = StringIO()
        call_command("cleanup_ghost_students", execute=True, stdout=out)
        output = out.getvalue()

        assert "GHOST01" in output
        assert "[OK]" in output

        from users.models import Student
        assert not Student.objects.filter(pk=pk).exists()

    def test_execute_deletes_multiple_ghosts(self, batch):
        from users.models import Student
        ids = ["GHOST_A", "GHOST_B", "GHOST_C"]
        pks = [self._make_ghost(batch, sid).pk for sid in ids]
        out = StringIO()
        call_command("cleanup_ghost_students", execute=True, stdout=out)

        for pk in pks:
            assert not Student.objects.filter(pk=pk).exists()
        assert "3 deleted" in out.getvalue()

    def test_no_ghosts_reports_nothing_to_do(self, db):
        out = StringIO()
        call_command("cleanup_ghost_students", stdout=out)
        assert "Nothing to do" in out.getvalue()

    def test_active_students_are_never_touched(self, batch, student):
        """Active (toggle-on) students must never be affected."""
        assert student.is_active is True
        out = StringIO()
        call_command("cleanup_ghost_students", execute=True, stdout=out)
        assert "Nothing to do" in out.getvalue()

        from users.models import Student
        assert Student.objects.filter(pk=student.pk).exists()

    def test_execute_only_deletes_inactive_not_active(self, batch, student):
        """With a mix of active + ghost students, only the ghost is removed."""
        ghost = self._make_ghost(batch, "GHOST_MIX")
        out = StringIO()
        call_command("cleanup_ghost_students", execute=True, stdout=out)

        from users.models import Student
        assert not Student.objects.filter(pk=ghost.pk).exists()
        assert Student.objects.filter(pk=student.pk).exists()
