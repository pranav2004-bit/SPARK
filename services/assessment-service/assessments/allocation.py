"""
allocation.py — the roster-snapshot + set-distribution engine (Task 3.1).

Reused by two admin actions (Task 3.2):
  * assignment creation — first snapshot, allocates every student in the batch
  * resync-roster — a later, additive-only re-snapshot for students added to
    the batch after the assignment was created (never removes an existing
    allocation, per Task 3.1's documented roster-change policy)

Both are the same operation: "create a StudentSetAllocation for every
roster student not already allocated under this assignment." Idempotent by
construction — an already-allocated student is skipped, and the DB-level
unique_together=(assignment, student_id) constraint is the final backstop
against a race between two concurrent calls.
"""

import logging
import uuid

from core.user_service_client import fetch_batch_roster
from .models import StudentSetAllocation, distribute_set_for_student

logger = logging.getLogger(__name__)


def snapshot_roster_and_allocate(assignment, auth_header: str) -> int:
    """
    Fetch the batch roster from user-service and create StudentSetAllocation
    rows for every student not already allocated under this assignment.

    Raises RuntimeError if the roster fetch fails, or if the assignment's
    paper has no sets to distribute across — callers (Task 3.2's admin
    endpoints) must treat either as a hard failure: no partial allocation
    state is ever written before this point, since the roster is fetched in
    full before any row is created.

    Returns the number of NEW allocations created (0 is valid — e.g. a
    0-student batch, or a resync where nobody new was added).
    """
    # (id, label) pairs, not just ids — label is needed to populate each new
    # allocation's set_label_snapshot (2026-11-13), the frozen display value
    # that survives the Set row itself later being deleted.
    sets = list(assignment.paper.sets.order_by("order").values_list("id", "label"))
    set_ids = [s[0] for s in sets]
    set_labels = [s[1] for s in sets]
    if not set_ids:
        raise RuntimeError(
            "This paper has no question sets — cannot distribute students to a set."
        )

    students = fetch_batch_roster(str(assignment.batch_id), auth_header)

    existing_ids = set(
        StudentSetAllocation.objects.filter(assignment=assignment)
        .values_list("student_id", flat=True)
    )

    # Empty department_sections (the default) means every department/
    # section in the batch — narrow the roster only when the admin scoped
    # this assignment to specific department+section combination(s)
    # (originally department-only, 2026-08-15; extended to pair with
    # section, 2026-11-14, user decision). Each entry's `sections: []`
    # means "every section in that department" — a department with no
    # section narrowing at all. department/section are both free-text on
    # Student (user-service) — department has no fixed enum, section is a
    # mandatory single A-Z letter — both matched case-insensitively, same
    # convention as the admin results table's existing department filter
    # (department__iexact).
    if assignment.department_sections:
        # {department_lower: {section_lower, ...} | None} — None means
        # "every section in this department" (an empty `sections` list on
        # that entry), distinguished from an empty set (which would
        # wrongly match nothing).
        wanted: dict = {}
        for entry in assignment.department_sections:
            dept = (entry.get("department") or "").strip().lower()
            if not dept:
                continue
            entry_sections = entry.get("sections") or []
            sections = {s.strip().lower() for s in entry_sections if s.strip()} or None
            # A department named twice (e.g. once whole, once narrowed) —
            # None (whole department) always wins over a narrower set,
            # since that's clearly the admin's broader intent.
            if dept in wanted and wanted[dept] is None:
                continue
            wanted[dept] = sections

        def _matches(student: dict) -> bool:
            dept = (student.get("department") or "").strip().lower()
            if dept not in wanted:
                return False
            sections = wanted[dept]
            if sections is None:
                return True
            return (student.get("section") or "").strip().lower() in sections

        matched = [s for s in students if _matches(s)]
        if not matched and students and not existing_ids:
            # Only the FIRST snapshot (nothing allocated yet) can leave this
            # assignment permanently dead — a resync legitimately finding
            # zero new matches (everyone eligible is already allocated)
            # isn't an error, just nothing new to do, so this only fires
            # pre-creation.
            raise RuntimeError(
                "No students in the selected batch match the selected department(s)/section(s). "
                "Double-check the department and section names and try again."
            )
        students = matched

    new_allocations = []
    skipped = 0
    for student in students:
        raw_user_id = student.get("user_id")
        if not raw_user_id:
            # Defensive: a malformed roster entry (e.g. an old auth account
            # never linked correctly) must not abort the entire batch's
            # allocation — skip it and let the count/logs surface the gap.
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
        new_allocations.append(StudentSetAllocation(
            assignment=assignment,
            student_id=student_uuid,
            set_id=set_ids[set_index],
            set_label_snapshot=set_labels[set_index],
        ))

    if skipped:
        logger.warning(
            "Batch %s roster: skipped %d student(s) with missing/invalid user_id "
            "during allocation for assignment=%s.",
            assignment.batch_id, skipped, assignment.id,
        )

    if new_allocations:
        # ignore_conflicts is the final backstop against a race between two
        # concurrent calls for the same assignment (both computing the same
        # "not yet allocated" set before either has committed) — the
        # unique_together constraint makes the loser's rows a no-op instead
        # of an IntegrityError. batch_size=500 (Task 11.1's index/bulk-write
        # audit — same chunk size as Task 7.3's streaming export, for a
        # consistent convention): without it, Django sends every row in one
        # unbatched INSERT, which for a batch in the thousands risks
        # crowding Postgres's parameter-per-statement ceiling and holds one
        # large transaction/lock for the whole insert instead of several
        # smaller ones.
        StudentSetAllocation.objects.bulk_create(new_allocations, ignore_conflicts=True, batch_size=500)

    return len(new_allocations)
