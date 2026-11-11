import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayStudentSetAllocation,
    distribute_set_for_student,
    ASSIGNMENT_STATUS_SCHEDULED, ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_CLOSED,
)


@pytest.mark.django_db
class TestEssayPaper:
    def test_create_paper(self):
        paper = EssayPaper.objects.create(
            institution_id=uuid.uuid4(), title="Midterm Essay", created_by=uuid.uuid4(),
        )
        assert paper.id is not None
        assert str(paper) == "Midterm Essay"

    def test_institution_scoping(self):
        inst_a, inst_b = uuid.uuid4(), uuid.uuid4()
        EssayPaper.objects.create(institution_id=inst_a, title="A's paper", created_by=uuid.uuid4())
        EssayPaper.objects.create(institution_id=inst_b, title="B's paper", created_by=uuid.uuid4())
        assert EssayPaper.objects.filter(institution_id=inst_a).count() == 1
        assert EssayPaper.objects.filter(institution_id=inst_b).count() == 1

    def test_no_status_field(self):
        # Locks in the Task 2.1 correction: no draft/published/archived
        # field exists — mirrors assessment-service's QuestionPaper exactly.
        assert not hasattr(EssayPaper, "status")

    def test_is_locked_false_with_no_assignment(self):
        paper = EssayPaper.objects.create(institution_id=uuid.uuid4(), title="x", created_by=uuid.uuid4())
        assert paper.is_locked() is False

    @pytest.mark.parametrize("status", [ASSIGNMENT_STATUS_SCHEDULED, ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_CLOSED])
    def test_is_locked_true_for_any_non_terminal_or_terminal_assignment_status(self, status):
        # Locked the moment ANY assignment exists in these three statuses —
        # unlike a session/attempt state machine, there is no "rejected/
        # never happened" assignment status that would NOT lock the paper.
        paper = EssayPaper.objects.create(institution_id=uuid.uuid4(), title="x", created_by=uuid.uuid4())
        EssayAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=paper.institution_id,
            global_expire_time=timezone.now() + timedelta(days=1),
            status=status, created_by=uuid.uuid4(),
        )
        assert paper.is_locked() is True


@pytest.mark.django_db
class TestEssaySet:
    def test_create_set(self):
        paper = EssayPaper.objects.create(institution_id=uuid.uuid4(), title="P", created_by=uuid.uuid4())
        eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
        assert eset in paper.sets.all()

    def test_unique_label_per_paper(self):
        paper = EssayPaper.objects.create(institution_id=uuid.uuid4(), title="P", created_by=uuid.uuid4())
        EssaySet.objects.create(paper=paper, label="Set A", order=1)
        with pytest.raises(IntegrityError):
            EssaySet.objects.create(paper=paper, label="Set A", order=2)

    def test_same_label_different_paper_allowed(self):
        p1 = EssayPaper.objects.create(institution_id=uuid.uuid4(), title="P1", created_by=uuid.uuid4())
        p2 = EssayPaper.objects.create(institution_id=uuid.uuid4(), title="P2", created_by=uuid.uuid4())
        EssaySet.objects.create(paper=p1, label="Set A", order=1)
        # No IntegrityError — unique_together is scoped to (paper, label).
        EssaySet.objects.create(paper=p2, label="Set A", order=1)

    def test_cascade_delete_from_paper(self):
        paper = EssayPaper.objects.create(institution_id=uuid.uuid4(), title="P", created_by=uuid.uuid4())
        eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
        paper.delete()
        assert not EssaySet.objects.filter(pk=eset.pk).exists()


@pytest.mark.django_db
class TestEssayQuestion:
    def _make_set(self):
        paper = EssayPaper.objects.create(institution_id=uuid.uuid4(), title="P", created_by=uuid.uuid4())
        return EssaySet.objects.create(paper=paper, label="Set A", order=1)

    def test_create_question(self):
        eset = self._make_set()
        q = EssayQuestion.objects.create(
            set=eset, question_text="Describe a challenge you overcame.",
            llm_rubric_prompt="Score for clarity, structure, and grammar.",
            word_limit=500, time_limit_minutes=30,
        )
        assert q.max_score == 10  # default, per the workflow spec
        assert eset.question == q

    def test_one_question_per_set_enforced_at_db_level(self):
        eset = self._make_set()
        EssayQuestion.objects.create(
            set=eset, question_text="Q1", llm_rubric_prompt="R1",
            word_limit=500, time_limit_minutes=30,
        )
        with pytest.raises(IntegrityError):
            EssayQuestion.objects.create(
                set=eset, question_text="Q2", llm_rubric_prompt="R2",
                word_limit=500, time_limit_minutes=30,
            )

    def test_cascade_delete_from_set(self):
        eset = self._make_set()
        q = EssayQuestion.objects.create(
            set=eset, question_text="Q1", llm_rubric_prompt="R1",
            word_limit=500, time_limit_minutes=30,
        )
        eset.delete()
        assert not EssayQuestion.objects.filter(pk=q.pk).exists()


@pytest.mark.django_db
class TestEssayAssignment:
    def _make_paper(self):
        return EssayPaper.objects.create(institution_id=uuid.uuid4(), title="P", created_by=uuid.uuid4())

    def test_create_assignment_defaults_to_scheduled(self):
        paper = self._make_paper()
        assignment = EssayAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=paper.institution_id,
            global_expire_time=timezone.now() + timedelta(days=1), created_by=uuid.uuid4(),
        )
        assert assignment.status == ASSIGNMENT_STATUS_SCHEDULED
        assert assignment.departments == []

    def test_paper_protect_on_delete(self):
        # A paper with an assignment must never silently cascade-delete —
        # matches assessment-service's BatchAssignment.paper PROTECT.
        paper = self._make_paper()
        EssayAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=paper.institution_id,
            global_expire_time=timezone.now() + timedelta(days=1), created_by=uuid.uuid4(),
        )
        with pytest.raises(Exception):  # ProtectedError
            paper.delete()


@pytest.mark.django_db
class TestEssayStudentSetAllocation:
    def _make_assignment_with_sets(self, n_sets=2):
        paper = EssayPaper.objects.create(institution_id=uuid.uuid4(), title="P", created_by=uuid.uuid4())
        sets = [EssaySet.objects.create(paper=paper, label=f"Set {chr(65+i)}", order=i) for i in range(n_sets)]
        assignment = EssayAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=paper.institution_id,
            global_expire_time=timezone.now() + timedelta(days=1), created_by=uuid.uuid4(),
        )
        return assignment, sets

    def test_one_allocation_per_student_per_assignment(self):
        assignment, sets = self._make_assignment_with_sets()
        student_id = uuid.uuid4()
        EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=student_id, set=sets[0])
        with pytest.raises(IntegrityError):
            EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=student_id, set=sets[1])

    def test_same_student_different_assignment_allowed(self):
        assignment1, sets1 = self._make_assignment_with_sets()
        assignment2, sets2 = self._make_assignment_with_sets()
        student_id = uuid.uuid4()
        EssayStudentSetAllocation.objects.create(assignment=assignment1, student_id=student_id, set=sets1[0])
        # No IntegrityError — unique_together is scoped to (assignment, student_id).
        EssayStudentSetAllocation.objects.create(assignment=assignment2, student_id=student_id, set=sets2[0])

    def test_set_protect_on_delete(self):
        assignment, sets = self._make_assignment_with_sets()
        EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=uuid.uuid4(), set=sets[0])
        with pytest.raises(Exception):  # ProtectedError
            sets[0].delete()

    def test_cascade_delete_from_assignment(self):
        assignment, sets = self._make_assignment_with_sets()
        alloc = EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=uuid.uuid4(), set=sets[0])
        assignment.delete()
        assert not EssayStudentSetAllocation.objects.filter(pk=alloc.pk).exists()


class TestDistributeSetForStudent:
    def test_determinism_same_inputs_same_set(self):
        student_id = uuid.uuid4()
        assignment_id = uuid.uuid4()
        first = distribute_set_for_student(student_id, assignment_id, 4)
        second = distribute_set_for_student(student_id, assignment_id, 4)
        assert first == second

    def test_different_students_can_land_on_different_sets(self):
        assignment_id = uuid.uuid4()
        indices = {distribute_set_for_student(uuid.uuid4(), assignment_id, 4) for _ in range(50)}
        # Over 50 random students and 4 sets, landing on only one set the
        # entire time would indicate a broken/constant hash, not chance.
        assert len(indices) > 1

    def test_result_always_within_bounds(self):
        assignment_id = uuid.uuid4()
        for _ in range(200):
            idx = distribute_set_for_student(uuid.uuid4(), assignment_id, 3)
            assert 0 <= idx < 3

    def test_distribution_fairness_roughly_even_spread(self):
        # Not a statistical proof — a sanity check that a realistic batch
        # size (300 students) across 3 sets doesn't land overwhelmingly on
        # one set (which would indicate a biased hash, not a fair one).
        assignment_id = uuid.uuid4()
        n_sets = 3
        counts = [0] * n_sets
        for _ in range(300):
            counts[distribute_set_for_student(uuid.uuid4(), assignment_id, n_sets)] += 1
        expected = 300 / n_sets
        for count in counts:
            assert abs(count - expected) < expected * 0.5  # within 50% of even split
