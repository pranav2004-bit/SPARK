import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from assessments.models import (
    QuestionPaper, QuestionSet, Question, QuestionOption,
    QUESTION_CONTENT_TEXT, QUESTION_CONTENT_BOTH,
    MCQ_TYPE_SINGLE, MCQ_TYPE_MULTIPLE,
)

# Fixed dev-only UUIDs so re-running this command is idempotent and the
# seeded IDs are predictable for manual testing / screenshots.
DEV_INSTITUTION_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
DEV_ADMIN_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


class Command(BaseCommand):
    help = (
        "Seeds one demo QuestionPaper with two equivalent sets (Set A / Set B), "
        "each with mixed text/image, single/multiple-choice questions — for local "
        "dev testing (Task 2.1). Idempotent: safe to re-run."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        paper, created = QuestionPaper.objects.get_or_create(
            institution_id=DEV_INSTITUTION_ID,
            title="Aptitude Mock Test — Demo Paper",
            defaults={
                "description": "Seed data for local dev testing (Task 2.1).",
                "created_by": DEV_ADMIN_ID,
            },
        )
        if not created:
            self.stdout.write(self.style.WARNING(
                f"Paper already exists ({paper.id}) — skipping (idempotent, no duplicate created)."
            ))
            return

        for set_label in ("Set A", "Set B"):
            qset = QuestionSet.objects.create(paper=paper, label=set_label, order=0 if set_label == "Set A" else 1)

            # Q1 — text-only, single-choice
            q1 = Question.objects.create(
                set=qset,
                question_content_type=QUESTION_CONTENT_TEXT,
                question_text="What is the next number in the series: 2, 4, 8, 16, ?",
                mcq_type=MCQ_TYPE_SINGLE,
                marks=1,
            )
            self._options(q1, [("A", "24", False), ("B", "32", True), ("C", "30", False), ("D", "36", False)])

            # Q2 — text-only, multiple-choice
            q2 = Question.objects.create(
                set=qset,
                question_content_type=QUESTION_CONTENT_TEXT,
                question_text="Which of the following are prime numbers?",
                mcq_type=MCQ_TYPE_MULTIPLE,
                marks=2,
            )
            self._options(q2, [("A", "7", True), ("B", "9", False), ("C", "11", True), ("D", "15", False)])

            # Q3 — text + image (placeholder key — demo data only, not a real
            # uploaded/scanned file; real uploads go through Task 2.2's
            # presign endpoint once it exists)
            q3 = Question.objects.create(
                set=qset,
                question_content_type=QUESTION_CONTENT_BOTH,
                question_text="Refer to the diagram below. What shape is highlighted?",
                question_image_key=f"uploads/question/seed-demo-{qset.label.replace(' ', '').lower()}.png",
                question_image_size_bytes=102400,
                mcq_type=MCQ_TYPE_SINGLE,
                marks=1,
            )
            self._options(q3, [("A", "Triangle", False), ("B", "Hexagon", True), ("C", "Pentagon", False)])

        self.stdout.write(self.style.SUCCESS(
            f"Seeded paper '{paper.title}' ({paper.id}) with 2 sets, 3 questions each."
        ))

    @staticmethod
    def _options(question, specs):
        for order, (label, text, is_correct) in enumerate(specs, start=1):
            QuestionOption.objects.create(
                question=question, label=label, text=text,
                is_correct=is_correct, order=order,
            )
