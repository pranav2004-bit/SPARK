import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from essays.models import EssayPaper, EssaySet, EssayAssignment, EssayStudentSetAllocation
from essays.allocation import snapshot_roster_and_allocate

from .conftest import INSTITUTION_A, ADMIN_USER_ID


@pytest.fixture
def paper(db):
    return EssayPaper.objects.create(
        institution_id=INSTITUTION_A, title="Alloc Test Paper", created_by=ADMIN_USER_ID,
    )


@pytest.fixture
def two_sets(paper):
    a = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    b = EssaySet.objects.create(paper=paper, label="Set B", order=2)
    return [a, b]


@pytest.fixture
def assignment(paper, two_sets):
    return EssayAssignment.objects.create(
        paper=paper,
        batch_id=uuid.uuid4(),
        institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        created_by=ADMIN_USER_ID,
    )


def _roster(n, prefix="S", department=None):
    return [
        {"user_id": str(uuid.uuid4()), "student_id": f"{prefix}-{i:04d}", "department": department}
        for i in range(n)
    ]


# ── Allocation engine (mirrors assessment-service's test_allocation.py) ────────

class TestSnapshotRosterAndAllocate:
    @patch("essays.allocation.fetch_batch_roster")
    def test_allocates_every_roster_student(self, mock_fetch, assignment, two_sets):
        mock_fetch.return_value = _roster(20)
        created = snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert created == 20
        assert EssayStudentSetAllocation.objects.filter(assignment=assignment).count() == 20

    @patch("essays.allocation.fetch_batch_roster")
    def test_second_run_is_idempotent_no_op(self, mock_fetch, assignment, two_sets):
        roster = _roster(15)
        mock_fetch.return_value = roster
        first = snapshot_roster_and_allocate(assignment, "Bearer fake")
        second = snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert first == 15
        assert second == 0
        assert EssayStudentSetAllocation.objects.filter(assignment=assignment).count() == 15

    @patch("essays.allocation.fetch_batch_roster")
    def test_resync_only_adds_new_students_existing_untouched(self, mock_fetch, assignment, two_sets):
        roster = _roster(10)
        mock_fetch.return_value = roster
        snapshot_roster_and_allocate(assignment, "Bearer fake")
        existing_set_ids = set(
            EssayStudentSetAllocation.objects.filter(assignment=assignment).values_list("student_id", "set_id")
        )

        roster_plus_new = roster + _roster(3, prefix="NEW")
        mock_fetch.return_value = roster_plus_new
        added = snapshot_roster_and_allocate(assignment, "Bearer fake")

        assert added == 3
        assert EssayStudentSetAllocation.objects.filter(assignment=assignment).count() == 13
        still_there = set(
            EssayStudentSetAllocation.objects.filter(assignment=assignment).values_list("student_id", "set_id")
        )
        assert existing_set_ids.issubset(still_there)

    @patch("essays.allocation.fetch_batch_roster")
    def test_zero_student_batch_no_crash(self, mock_fetch, assignment, two_sets):
        mock_fetch.return_value = []
        created = snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert created == 0
        assert EssayStudentSetAllocation.objects.filter(assignment=assignment).count() == 0

    @patch("essays.allocation.fetch_batch_roster")
    def test_roster_fetch_failure_leaves_no_partial_state(self, mock_fetch, assignment, two_sets):
        mock_fetch.side_effect = RuntimeError("user-service unreachable")
        with pytest.raises(RuntimeError):
            snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert EssayStudentSetAllocation.objects.filter(assignment=assignment).count() == 0

    def test_paper_with_no_sets_raises_cleanly(self, assignment):
        assignment.paper.sets.all().delete()
        with pytest.raises(RuntimeError):
            snapshot_roster_and_allocate(assignment, "Bearer fake")

    @patch("essays.allocation.fetch_batch_roster")
    def test_malformed_roster_entries_are_skipped_not_fatal(self, mock_fetch, assignment, two_sets):
        good = _roster(5)
        malformed = [{"student_id": "no-user-id-here"}, {"user_id": "not-a-uuid", "student_id": "bad"}]
        mock_fetch.return_value = good + malformed
        created = snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert created == 5


class TestSnapshotRosterAndAllocateDepartmentFilter:
    @patch("essays.allocation.fetch_batch_roster")
    def test_empty_departments_allocates_every_department(self, mock_fetch, assignment, two_sets):
        assert assignment.departments == []
        roster = _roster(5, prefix="CSE", department="CSE") + _roster(5, prefix="ECE", department="ECE")
        mock_fetch.return_value = roster
        created = snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert created == 10

    @patch("essays.allocation.fetch_batch_roster")
    def test_narrows_to_selected_departments_only(self, mock_fetch, assignment, two_sets):
        assignment.departments = ["CSE", "CSD"]
        assignment.save(update_fields=["departments"])
        roster = (
            _roster(4, prefix="CSE", department="CSE")
            + _roster(3, prefix="CSD", department="CSD")
            + _roster(6, prefix="ECE", department="ECE")
        )
        mock_fetch.return_value = roster
        created = snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert created == 7

    @patch("essays.allocation.fetch_batch_roster")
    def test_department_match_is_case_insensitive(self, mock_fetch, assignment, two_sets):
        assignment.departments = ["cse"]
        assignment.save(update_fields=["departments"])
        mock_fetch.return_value = _roster(4, department="CSE")
        created = snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert created == 4

    @patch("essays.allocation.fetch_batch_roster")
    def test_no_matching_department_on_first_snapshot_raises_and_creates_nothing(self, mock_fetch, assignment, two_sets):
        assignment.departments = ["MECH"]
        assignment.save(update_fields=["departments"])
        mock_fetch.return_value = _roster(10, department="CSE")
        with pytest.raises(RuntimeError):
            snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert EssayStudentSetAllocation.objects.filter(assignment=assignment).count() == 0
