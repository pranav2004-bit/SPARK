"""
allocation.py — the roster-snapshot + set-distribution engine (Task 3.1).

Mirrors assessment-service's own allocation.py pattern exactly, adapted for
EssayAssignment/EssayStudentSetAllocation. Reused by two admin actions
(Task 3.2):
  * assignment creation — first snapshot, allocates every student in the batch
  * resync-roster — a later, additive-only re-snapshot for students added to
    the batch after the assignment was created (never removes an existing
    allocation)

Both are the same operation: "create an EssayStudentSetAllocation for every
roster student not already allocated under this assignment." Idempotent by
construction — an already-allocated student is skipped, and the DB-level
unique_together=(assignment, student_id) constraint is the final backstop
against a race between two concurrent calls.
"""

import logging
import uuid

from core.user_service_client import fetch_batch_roster
from .models import EssayStudentSetAllocation, distribute_set_for_student

logger = logging.getLogger(__name__)


def snapshot_roster_and_allocate(assignment, auth_header: str) -> int:
    """
    Fetch the batch roster from user-service and create
    EssayStudentSetAllocation rows for every student not already allocated
    under this assignment.

    Raises RuntimeError if the roster fetch fails, or if the assignment's
    paper has no sets to distribute across — callers (Task 3.2's admin
    endpoints) must treat either as a hard failure: no partial allocation
    state is ever written before this point, since the roster is fetched in
    full before any row is created.

    Returns the number of NEW allocations created (0 is valid — e.g. a
    0-student batch, or a resync where nobody new was added).
    """
    set_ids = list(
        assignment.paper.sets.order_by("order").values_list("id", flat=True)
    )
    if not set_ids:
        raise RuntimeError(
            "This paper has no essay sets — cannot distribute students to a set."
        )

    students = fetch_batch_roster(str(assignment.batch_id), auth_header)

    existing_ids = set(
        EssayStudentSetAllocation.objects.filter(assignment=assignment)
        .values_list("student_id", flat=True)
    )

    # Empty departments list (the default) means every department in the
    # batch — narrow the roster only when the admin scoped this assignment
    # to specific department(s), matching assessment-service's existing
    # convention exactly (department is free-text on Student, matched
    # case-insensitively).
    if assignment.departments:
        wanted = {d.strip().lower() for d in assignment.departments}
        matched = [s for s in students if (s.get("department") or "").strip().lower() in wanted]
        if not matched and students and not existing_ids:
            # Only the FIRST snapshot (nothing allocated yet) can leave this
            # assignment permanently dead — a resync legitimately finding
            # zero new matches (everyone eligible is already allocated)
            # isn't an error, just nothing new to do, so this only fires
            # pre-creation.
            raise RuntimeError(
                "No students in the selected batch match the selected department(s). "
                "Double-check the department names and try again."
            )
        students = matched

    new_allocations = []
    skipped = 0
    for student in students:
        raw_user_id = student.get("user_id")
        if not raw_user_id:
            # Defensive: a malformed roster entry must not abort the entire
            # batch's allocation — skip it and let the count/logs surface
            # the gap.
            skipped += 1
            continue
        try:
            student_uuid = uuid.UUID(str(raw_user_id))
        except (ValueError, AttributeError):
            skipped += 1
            continue
        if student_uuid in existing_ids:
            continue
        set_index = distribute_set_for_student(student_uuid, assignment.id, len(set_ids))
        new_allocations.append(EssayStudentSetAllocation(
            assignment=assignment,
            student_id=student_uuid,
            set_id=set_ids[set_index],
        ))

    if skipped:
        logger.warning(
            "Batch %s roster: skipped %d student(s) with missing/invalid user_id "
            "during allocation for assignment=%s.",
            assignment.batch_id, skipped, assignment.id,
        )

    if new_allocations:
        # ignore_conflicts is the final backstop against a race between two
        # concurrent calls for the same assignment; batch_size=500 matches
        # assessment-service's own Task 11.1 index/bulk-write convention.
        EssayStudentSetAllocation.objects.bulk_create(new_allocations, ignore_conflicts=True, batch_size=500)

    return len(new_allocations)
