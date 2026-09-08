import uuid
from io import StringIO

import pytest
from django.core.management import call_command

from tests.conftest import INSTITUTION_A, INSTITUTION_B, STUDENT_USER_ID


@pytest.mark.django_db
class TestStudentListCreate:
    def test_list_students_forbidden_for_admin(self, admin_client, student):
        """Students module removed from Admin entirely (2026-08-19) — Batches
        alone is Admin's student-facing module now; the standalone Students
        list is Super Admin/IT-only."""
        resp = admin_client.get("/api/users/students/")
        assert resp.status_code == 403

    def test_list_requires_auth(self, anon_client):
        resp = anon_client.get("/api/users/students/")
        assert resp.status_code == 401

    def test_student_cannot_list_all_students(self, student_client):
        resp = student_client.get("/api/users/students/")
        assert resp.status_code == 403

    def test_create_student_forbidden_for_admin(self, admin_client, batch):
        """Admin is read/query-only (2026-08-19) — student creation is IT-exclusive."""
        resp = admin_client.post("/api/users/students/", {
            "student_id": "STU999",
            "department": "ECE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 403

    def test_create_student_forbidden_for_super_admin(self, super_admin_client, batch):
        resp = super_admin_client.post("/api/users/students/", {
            "student_id": "STU999",
            "department": "ECE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 403

    def test_list_students_forbidden_for_super_admin(self, super_admin_client, student):
        """Students module removed from Super Admin too (2026-08-19) — same
        reasoning and timing as Admin; IT is the sole owner of this endpoint."""
        resp = super_admin_client.get("/api/users/students/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestStudentDetail:
    def test_get_student_forbidden_for_admin(self, admin_client, student):
        """Students module removed from Admin entirely (2026-08-19)."""
        resp = admin_client.get(f"/api/users/students/{student.pk}/")
        assert resp.status_code == 403

    def test_get_student_forbidden_for_super_admin(self, super_admin_client, student):
        """Students module removed from Super Admin too (2026-08-19)."""
        resp = super_admin_client.get(f"/api/users/students/{student.pk}/")
        assert resp.status_code == 403

    def test_patch_student_forbidden_for_admin(self, admin_client, student, batch):
        """Admin is read/query-only (2026-08-19) — student edits are IT-exclusive."""
        resp = admin_client.patch(f"/api/users/students/{student.pk}/", {
            "fullname": "John Doe",
            "college_email_id": "john@college.edu",
        }, format="json")
        assert resp.status_code == 403

    def test_hard_delete_student_forbidden_for_admin(self, admin_client, student):
        resp = admin_client.delete(f"/api/users/students/{student.pk}/")
        assert resp.status_code == 403
        from users.models import Student
        assert Student.objects.filter(pk=student.pk).exists()


@pytest.mark.django_db
class TestStudentToggleStatus:
    def test_toggle_status_forbidden_for_admin(self, admin_client, student):
        """Admin is read/query-only (2026-08-19) — toggling status is IT-exclusive."""
        assert student.is_active is True
        resp = admin_client.patch(f"/api/users/students/{student.pk}/toggle-status/")
        assert resp.status_code == 403
        student.refresh_from_db()
        assert student.is_active is True


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
    def test_bulk_import_forbidden_for_admin(self, admin_client, batch):
        """Admin is read/query-only (2026-08-19) — bulk import is IT-exclusive."""
        resp = admin_client.post("/api/users/students/import/", {
            "student_ids": ["B001", "B002", "B003"],
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 403


# ── Batches/Students CRUD is exclusive to IT (revised 2026-08-19). Admin and ──
# Super Admin briefly had equal write access ("shared access", 2026-08-19);
# that was reversed the same day — Admin/Super Admin keep read-only access
# (tested above), IT owns all create/update/delete/toggle/bulk-import, so all
# of the write-path validation coverage lives here now.

@pytest.mark.django_db
class TestStudentListCreateIT:
    def test_list_students_as_it(self, it_client, student):
        resp = it_client.get("/api/users/students/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["student_id"] == "STU001"

    def test_create_student_as_it(self, it_client, batch):
        resp = it_client.post("/api/users/students/", {
            "student_id": "STU998",
            "department": "ECE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["student_id"] == "STU998"

    def test_create_student_uppercase_normalization(self, it_client, batch):
        resp = it_client.post("/api/users/students/", {
            "student_id": "stu123",
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 201
        assert resp.json()["data"]["student_id"] == "STU123"

    def test_create_student_duplicate_id(self, it_client, batch, student):
        resp = it_client.post("/api/users/students/", {
            "student_id": "STU001",
            "department": "ECE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 400

    def test_create_student_wrong_institution_batch(self, it_client, batch_b):
        resp = it_client.post("/api/users/students/", {
            "student_id": "STU500",
            "department": "CSE",
            "batch_id": str(batch_b.pk),
        }, format="json")
        assert resp.status_code == 400

    def test_it_cannot_see_other_institution_students(self, it_b_client, student):
        resp = it_b_client.get("/api/users/students/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_search_filter(self, it_client, student):
        resp = it_client.get("/api/users/students/?search=STU001")
        assert resp.json()["count"] == 1
        resp2 = it_client.get("/api/users/students/?search=NOMATCH")
        assert resp2.json()["count"] == 0

    def test_department_filter(self, it_client, student):
        resp = it_client.get("/api/users/students/?department=CSE")
        assert resp.json()["count"] == 1
        resp2 = it_client.get("/api/users/students/?department=MECH")
        assert resp2.json()["count"] == 0


@pytest.mark.django_db
class TestStudentDetailIT:
    def test_get_student_as_it(self, it_client, student):
        resp = it_client.get(f"/api/users/students/{student.pk}/")
        assert resp.status_code == 200
        assert resp.json()["data"]["student_id"] == "STU001"

    def test_get_student_other_institution_404_for_it(self, it_b_client, student):
        resp = it_b_client.get(f"/api/users/students/{student.pk}/")
        assert resp.status_code == 404

    def test_patch_student_as_it(self, it_client, student, batch):
        resp = it_client.patch(f"/api/users/students/{student.pk}/", {
            "fullname": "IT Edited Name",
            "college_email_id": "itedit@college.edu",
        }, format="json")
        assert resp.status_code == 200
        assert resp.json()["data"]["fullname"] == "IT Edited Name"

    def test_hard_delete_student_as_it(self, it_client, student):
        pk = student.pk
        resp = it_client.delete(f"/api/users/students/{pk}/")
        assert resp.status_code == 200
        from users.models import Student
        assert not Student.objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestStudentToggleStatusIT:
    def test_toggle_status_as_it(self, it_client, student):
        assert student.is_active is True
        resp = it_client.patch(f"/api/users/students/{student.pk}/toggle-status/")
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False

    def test_toggle_wrong_institution_404_for_it(self, it_b_client, student):
        resp = it_b_client.patch(f"/api/users/students/{student.pk}/toggle-status/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestBulkStudentImportIT:
    def test_bulk_import_as_it(self, it_client, batch):
        resp = it_client.post("/api/users/students/import/", {
            "student_ids": ["IT001", "IT002"],
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["created"] == 2
        assert data["rejected"] == 0

    def test_bulk_import_max_limit(self, it_client, batch):
        ids = [f"S{i:04d}" for i in range(1001)]
        resp = it_client.post("/api/users/students/import/", {
            "student_ids": ids,
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 400

    def test_bulk_import_duplicates_skipped(self, it_client, batch, student):
        resp = it_client.post("/api/users/students/import/", {
            "student_ids": ["STU001", "NEW001"],
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["created"] == 1
        assert data["rejected"] == 1

    def test_bulk_import_within_file_duplicates(self, it_client, batch):
        resp = it_client.post("/api/users/students/import/", {
            "student_ids": ["DUP001", "DUP001"],
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        data = resp.json()["data"]
        assert data["created"] == 1
        assert data["rejected"] == 1

    def test_bulk_import_missing_department(self, it_client, batch):
        resp = it_client.post("/api/users/students/import/", {
            "student_ids": ["X001"],
            "batch_id": str(batch.pk),
        }, format="json")
        assert resp.status_code == 400

    def test_bulk_import_wrong_institution_batch(self, it_client, batch_b):
        resp = it_client.post("/api/users/students/import/", {
            "student_ids": ["X001"],
            "department": "CSE",
            "batch_id": str(batch_b.pk),
        }, format="json")
        assert resp.status_code == 400

    def test_bulk_import_empty_ids_rejected(self, it_client, batch):
        resp = it_client.post("/api/users/students/import/", {
            "student_ids": ["", "VALID001"],
            "department": "CSE",
            "batch_id": str(batch.pk),
        }, format="json")
        data = resp.json()["data"]
        assert data["created"] == 1
        assert data["rejected"] == 1

    def test_bulk_import_invalid_list_type(self, it_client, batch):
        resp = it_client.post("/api/users/students/import/", {
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
