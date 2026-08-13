import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from assessments.models import (
    BatchAssignment, StudentSetAllocation, QuestionPaper, QuestionSet,
    distribute_set_for_student,
)
from assessments.allocation import snapshot_roster_and_allocate

from .conftest import INSTITUTION_A, ADMIN_USER_ID


@pytest.fixture
def paper(db):
    return QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Alloc Test Paper", created_by=ADMIN_USER_ID,
    )


@pytest.fixture
def two_sets(paper):
    a = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    b = QuestionSet.objects.create(paper=paper, label="Set B", order=2)
    return [a, b]


@pytest.fixture
def assignment(paper, two_sets):
    return BatchAssignment.objects.create(
        paper=paper,
        batch_id=uuid.uuid4(),
        institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60,
        created_by=ADMIN_USER_ID,
    )


def _roster(n, prefix="S"):
    return [
        {"user_id": str(uuid.uuid4()), "student_id": f"{prefix}-{i:04d}"}
        for i in range(n)
    ]


# ── Distribution algorithm ──────────────────────────────────────────────────

class TestDistributeSetForStudent:
    def test_deterministic_across_calls(self):
        sid, aid = uuid.uuid4(), uuid.uuid4()
        assert distribute_set_for_student(sid, aid, 2) == distribute_set_for_student(sid, aid, 2)

    def test_different_students_can_land_on_different_sets(self):
        aid = uuid.uuid4()
        results = {distribute_set_for_student(uuid.uuid4(), aid, 3) for _ in range(50)}
        assert len(results) > 1  # near-impossible for 50 random UUIDs to all collide on one set

    def test_always_within_bounds(self):
        aid = uuid.uuid4()
        for _ in range(200):
            idx = distribute_set_for_student(uuid.uuid4(), aid, 4)
            assert 0 <= idx < 4

    def test_roughly_even_spread_at_scale(self):
        aid = uuid.uuid4()
        counts = [0, 0]
        for _ in range(2000):
            counts[distribute_set_for_student(uuid.uuid4(), aid, 2)] += 1
        # Neither bucket should be wildly skewed for a cryptographic hash at n=2000.
        assert 0.35 < counts[0] / 2000 < 0.65


# ── Allocation engine ────────────────────────────────────────────────────────

class TestSnapshotRosterAndAllocate:
    @patch("assessments.allocation.fetch_batch_roster")
    def test_allocates_every_roster_student(self, mock_fetch, assignment, two_sets):
        mock_fetch.return_value = _roster(20)
        created = snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert created == 20
        assert StudentSetAllocation.objects.filter(assignment=assignment).count() == 20

    @patch("assessments.allocation.fetch_batch_roster")
    def test_second_run_is_idempotent_no_op(self, mock_fetch, assignment, two_sets):
        roster = _roster(15)
        mock_fetch.return_value = roster
        first = snapshot_roster_and_allocate(assignment, "Bearer fake")
        second = snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert first == 15
        assert second == 0
        assert StudentSetAllocation.objects.filter(assignment=assignment).count() == 15

    @patch("assessments.allocation.fetch_batch_roster")
    def test_resync_only_adds_new_students_existing_untouched(self, mock_fetch, assignment, two_sets):
        roster = _roster(10)
        mock_fetch.return_value = roster
        snapshot_roster_and_allocate(assignment, "Bearer fake")
        existing_set_ids = set(
            StudentSetAllocation.objects.filter(assignment=assignment).values_list("student_id", "set_id")
        )

        roster_plus_new = roster + _roster(3, prefix="NEW")
        mock_fetch.return_value = roster_plus_new
        added = snapshot_roster_and_allocate(assignment, "Bearer fake")

        assert added == 3
        assert StudentSetAllocation.objects.filter(assignment=assignment).count() == 13
        # Original 10 allocations kept their original set — resync never
        # reshuffles an already-allocated student.
        still_there = set(
            StudentSetAllocation.objects.filter(assignment=assignment).values_list("student_id", "set_id")
        )
        assert existing_set_ids.issubset(still_there)

    @patch("assessments.allocation.fetch_batch_roster")
    def test_zero_student_batch_no_crash(self, mock_fetch, assignment, two_sets):
        mock_fetch.return_value = []
        created = snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert created == 0
        assert StudentSetAllocation.objects.filter(assignment=assignment).count() == 0

    @patch("assessments.allocation.fetch_batch_roster")
    def test_roster_fetch_failure_leaves_no_partial_state(self, mock_fetch, assignment, two_sets):
        mock_fetch.side_effect = RuntimeError("user-service unreachable")
        with pytest.raises(RuntimeError):
            snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert StudentSetAllocation.objects.filter(assignment=assignment).count() == 0

    def test_paper_with_no_sets_raises_cleanly(self, assignment):
        # assignment fixture depends on two_sets normally; here we delete them
        # to simulate a paper with zero sets reaching this function.
        assignment.paper.sets.all().delete()
        with pytest.raises(RuntimeError):
            snapshot_roster_and_allocate(assignment, "Bearer fake")

    @patch("assessments.allocation.fetch_batch_roster")
    def test_malformed_roster_entries_are_skipped_not_fatal(self, mock_fetch, assignment, two_sets):
        good = _roster(5)
        malformed = [{"student_id": "no-user-id-here"}, {"user_id": "not-a-uuid", "student_id": "bad"}]
        mock_fetch.return_value = good + malformed
        created = snapshot_roster_and_allocate(assignment, "Bearer fake")
        assert created == 5  # only the well-formed entries were allocated
