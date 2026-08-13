import uuid
from django.db import models


# ── Practice Modules ──────────────────────────────────────────────────────────

class PracticeModule(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name         = models.CharField(max_length=200)
    institution_id = models.UUIDField(db_index=True)
    parent       = models.ForeignKey(
        "self",
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="children",
        db_index=True,
    )
    is_published = models.BooleanField(default=False)
    order        = models.PositiveIntegerField(default=0, db_index=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "practice_modules"
        ordering = ["order", "created_at"]

    def __str__(self):
        return self.name


# ── Practice Sections ─────────────────────────────────────────────────────────

class PracticeSection(models.Model):
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name         = models.CharField(max_length=200)
    institution_id = models.UUIDField(db_index=True)
    module       = models.ForeignKey(
        PracticeModule,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="sections",
        db_index=True,
    )
    is_published = models.BooleanField(default=False)
    order        = models.PositiveIntegerField(default=0, db_index=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "practice_sections"
        ordering = ["order", "created_at"]

    def __str__(self):
        return self.name


# ── Practice Questions ────────────────────────────────────────────────────────

QUESTION_TYPE_MCQ = "mcq"
QUESTION_TYPE_FIB = "fib"
QUESTION_TYPE_CHOICES = [
    (QUESTION_TYPE_MCQ, "Multiple Choice"),
    (QUESTION_TYPE_FIB, "Fill in the Blank"),
]

MCQ_TYPE_SINGLE   = "single"
MCQ_TYPE_MULTIPLE = "multiple"
MCQ_TYPE_CHOICES  = [
    (MCQ_TYPE_SINGLE,   "Single correct answer"),
    (MCQ_TYPE_MULTIPLE, "Multiple correct answers"),
]

QUESTION_CONTENT_TEXT  = "text"
QUESTION_CONTENT_IMAGE = "image"
QUESTION_CONTENT_BOTH  = "both"
QUESTION_CONTENT_CHOICES = [
    (QUESTION_CONTENT_TEXT,  "Text only"),
    (QUESTION_CONTENT_IMAGE, "Image only"),
    (QUESTION_CONTENT_BOTH,  "Text and image"),
]


class PracticeQuestion(models.Model):
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section         = models.ForeignKey(
        PracticeSection,
        on_delete=models.CASCADE,
        related_name="questions",
        db_index=True,
    )
    question_number = models.PositiveIntegerField(default=0, db_index=True)
    title           = models.TextField(blank=True, default="")

    question_type = models.CharField(
        max_length=10, choices=QUESTION_TYPE_CHOICES, default=QUESTION_TYPE_MCQ,
    )
    mcq_type = models.CharField(
        max_length=10, choices=MCQ_TYPE_CHOICES, default=MCQ_TYPE_SINGLE,
    )
    question_content_type = models.CharField(
        max_length=10, choices=QUESTION_CONTENT_CHOICES, default=QUESTION_CONTENT_TEXT,
    )
    question_text       = models.TextField(blank=True, default="")
    question_image_key  = models.CharField(max_length=500, blank=True, default="")
    # Real size from storage (verify_uploaded_image), not client-reported —
    # used to enforce the per-section image storage quota.
    question_image_size_bytes = models.BigIntegerField(null=True, blank=True)
    fib_answer          = models.CharField(max_length=500, blank=True, default="")

    EXPLANATION_TYPE_CHOICES = [
        ("none",  "No explanation"),
        ("text",  "Text only"),
        ("image", "Image only"),
        ("both",  "Text and image"),
    ]
    explanation_type      = models.CharField(
        max_length=10, choices=EXPLANATION_TYPE_CHOICES, default="none",
    )
    explanation_text      = models.TextField(blank=True, default="")
    explanation_image_key = models.CharField(max_length=500, blank=True, default="")
    explanation_image_size_bytes = models.BigIntegerField(null=True, blank=True)

    is_published = models.BooleanField(default=False)
    order        = models.PositiveIntegerField(default=0, db_index=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "practice_questions"
        ordering = ["order", "created_at"]
        indexes  = [
            models.Index(fields=["section", "is_published"], name="idx_pq_section_published"),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and self.question_number == 0:
            from django.db.models import Max
            # Scoped to this section — every section's questions are numbered
            # 1, 2, 3... independently. A global counter here would make a
            # brand-new section's first question display as e.g. "Question
            # #847" (whatever the table-wide max happened to be).
            max_num = PracticeQuestion.objects.filter(section=self.section).aggregate(
                m=Max("question_number")
            )["m"] or 0
            self.question_number = max_num + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Q{self.question_number}" + (f" — {self.title[:60]}" if self.title else "")


# ── MCQ Options ───────────────────────────────────────────────────────────────

class PracticeQuestionOption(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question   = models.ForeignKey(
        PracticeQuestion,
        on_delete=models.CASCADE,
        related_name="options",
        db_index=True,
    )
    label      = models.CharField(max_length=5)
    text       = models.TextField(blank=True, default="")
    is_correct = models.BooleanField(default=False)
    order      = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "practice_question_options"
        ordering = ["order", "created_at"]

    def __str__(self):
        return f"Q{self.question_id} | {self.label} | {'✓' if self.is_correct else '✗'}"


# ── Student Question Progress ─────────────────────────────────────────────────

PROGRESS_NOT_VISITED = "not_visited"
PROGRESS_VISITED     = "visited"
PROGRESS_ATTEMPTED   = "attempted"
PROGRESS_COMPLETED   = "completed"

PROGRESS_RANK = {
    PROGRESS_NOT_VISITED: 0,
    PROGRESS_VISITED:     1,
    PROGRESS_ATTEMPTED:   2,
    PROGRESS_COMPLETED:   3,
}

PROGRESS_STATUS_CHOICES = [
    (PROGRESS_NOT_VISITED, "Not Visited"),
    (PROGRESS_VISITED,     "Visited"),
    (PROGRESS_ATTEMPTED,   "Attempted"),
    (PROGRESS_COMPLETED,   "Completed"),
]


class PracticeQuestionProgress(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # JWT user_id claim — no FK to Student (cross-service isolation)
    student_id     = models.UUIDField(db_index=True)
    institution_id = models.UUIDField(db_index=True)
    question       = models.ForeignKey(
        PracticeQuestion,
        on_delete=models.CASCADE,
        related_name="student_progress",
        db_index=True,
    )
    status     = models.CharField(
        max_length=20, choices=PROGRESS_STATUS_CHOICES, default=PROGRESS_NOT_VISITED,
        db_index=True,
    )
    first_visited_at   = models.DateTimeField(null=True, blank=True)
    first_attempted_at = models.DateTimeField(null=True, blank=True)
    first_completed_at = models.DateTimeField(null=True, blank=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = "practice_question_progress"
        unique_together = [("student_id", "question")]
        indexes = [
            models.Index(fields=["student_id", "question"], name="idx_pqp_student_question"),
            models.Index(fields=["student_id"],             name="idx_pqp_student_id"),
            models.Index(fields=["institution_id"],         name="idx_pqp_institution_id"),
        ]

    def __str__(self):
        return f"{self.student_id} | Q{self.question_id} | {self.status}"


# ── Student MCQ Attempt ───────────────────────────────────────────────────────

class PracticeQuestionAttempt(models.Model):
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # JWT user_id claim — no FK to Student (cross-service isolation)
    student_id          = models.UUIDField(db_index=True)
    institution_id      = models.UUIDField(db_index=True)
    question            = models.ForeignKey(
        PracticeQuestion,
        on_delete=models.CASCADE,
        related_name="student_attempts",
        db_index=True,
    )
    selected_option_ids = models.JSONField(default=list)
    is_correct          = models.BooleanField()
    attempt_number      = models.PositiveIntegerField()
    submitted_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "practice_question_attempts"
        ordering = ["attempt_number"]
        indexes  = [
            models.Index(fields=["student_id", "question"], name="idx_pqa_student_question"),
            models.Index(fields=["institution_id"],         name="idx_pqa_institution_id"),
        ]

    def __str__(self):
        return f"{self.student_id} | Q{self.question_id} | #{self.attempt_number} | {'✓' if self.is_correct else '✗'}"
