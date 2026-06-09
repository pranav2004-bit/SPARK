import uuid
from django.db import models


# ── Practice Modules ──────────────────────────────────────────────────────────

class PracticeModule(models.Model):
    """
    Admin-managed practice module. Supports arbitrary nesting via self-FK.
    parent=None  → top-level module shown on the Practice hub.
    parent=<id>  → child module nested inside another module.
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name         = models.CharField(max_length=200)
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
    """
    A section within a practice module, or at root level if module=None.
    Sections contain practice questions.
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name         = models.CharField(max_length=200)
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

# ── MCQ answer type ───────────────────────────────────────────────────────────
MCQ_TYPE_SINGLE   = "single"
MCQ_TYPE_MULTIPLE = "multiple"
MCQ_TYPE_CHOICES  = [
    (MCQ_TYPE_SINGLE,   "Single correct answer"),
    (MCQ_TYPE_MULTIPLE, "Multiple correct answers"),
]

# ── Question body content type ────────────────────────────────────────────────
QUESTION_CONTENT_TEXT  = "text"
QUESTION_CONTENT_IMAGE = "image"
QUESTION_CONTENT_BOTH  = "both"
QUESTION_CONTENT_CHOICES = [
    (QUESTION_CONTENT_TEXT,  "Text only"),
    (QUESTION_CONTENT_IMAGE, "Image only"),
    (QUESTION_CONTENT_BOTH,  "Text and image"),
]


class PracticeQuestion(models.Model):
    """
    A practice question. question_type determines the authoring interface:
      mcq → Multiple Choice (options, correct answer, explanation)
      fib → Fill in the Blank (blank-delimited sentence, correct fill)

    question_number is a globally-unique auto-assigned display number (e.g. 346).
    It is set on first save and never changes.
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section         = models.ForeignKey(
        PracticeSection,
        on_delete=models.CASCADE,
        related_name="questions",
        db_index=True,
    )
    question_number = models.PositiveIntegerField(default=0, db_index=True)
    title           = models.TextField(blank=True, default="",
                                      help_text="Short display title / preview")

    # ── Question type ─────────────────────────────────────────────────────────
    question_type = models.CharField(
        max_length=10, choices=QUESTION_TYPE_CHOICES, default=QUESTION_TYPE_MCQ,
    )

    # ── MCQ sub-type (ignored for FIB) ────────────────────────────────────────
    mcq_type = models.CharField(
        max_length=10,
        choices=MCQ_TYPE_CHOICES,
        default=MCQ_TYPE_SINGLE,
        help_text="Single or multiple correct answers. Relevant only for MCQ.",
    )

    # ── Question body ─────────────────────────────────────────────────────────
    question_content_type = models.CharField(
        max_length=10,
        choices=QUESTION_CONTENT_CHOICES,
        default=QUESTION_CONTENT_TEXT,
        help_text="Controls which elements (text / image / both) make up the question body.",
    )
    question_text   = models.TextField(blank=True, default="",
                                       help_text="Full question text. Use ___ for blanks in FIB.")
    question_image_key = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Cloudflare R2 object key for the question body image.",
    )

    # ── FIB answer (ignored for MCQ) ──────────────────────────────────────────
    fib_answer = models.CharField(
        max_length=500, blank=True, default="",
        help_text="FIB: the correct answer for the blank.",
    )

    # ── Explanation (shared by FIB and MCQ) ───────────────────────────────────
    EXPLANATION_NONE  = "none"
    EXPLANATION_TEXT  = "text"
    EXPLANATION_IMAGE = "image"
    EXPLANATION_BOTH  = "both"
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
    explanation_image_key = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Cloudflare R2 object key for the explanation image.",
    )

    is_published = models.BooleanField(default=False)
    order        = models.PositiveIntegerField(default=0, db_index=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "practice_questions"
        ordering = ["order", "created_at"]

    def save(self, *args, **kwargs):
        # Use _state.adding (not self.pk) because UUID primary keys are
        # generated at instantiation — self.pk is never falsy for UUID models.
        if self._state.adding and self.question_number == 0:
            from django.db.models import Max
            max_num = PracticeQuestion.objects.aggregate(m=Max("question_number"))["m"] or 0
            self.question_number = max_num + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Q{self.question_number}" + (f" — {self.title[:60]}" if self.title else "")


# ── MCQ Options ───────────────────────────────────────────────────────────────

class PracticeQuestionOption(models.Model):
    """
    One answer choice for an MCQ question.
    label  : A, B, C, D, … (display letter, set by admin or auto-assigned)
    text   : the option body text
    is_correct : whether this option is a correct answer
    order  : display position

    For single-correct MCQs the backend enforces that at most one option
    has is_correct=True (enforced at the view level, not the DB level,
    to avoid race conditions).
    """
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question   = models.ForeignKey(
        PracticeQuestion,
        on_delete=models.CASCADE,
        related_name="options",
        db_index=True,
    )
    label      = models.CharField(max_length=5, help_text="Display letter: A, B, C, D …")
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

# Numeric rank for transition enforcement (monotone — never regresses).
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
    """
    Per-student progress record for a single practice question.

    Monotone state machine (never regresses):
        not_visited → visited → attempted → completed

    not_visited : implicit default; no DB row until first visit.
    visited     : student opened the question at least once.
    attempted   : student submitted an MCQ answer (correct or wrong).
    completed   : student got the MCQ correct, OR revealed FIB answer.
    """
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student    = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="question_progress",
        db_index=True,
    )
    question   = models.ForeignKey(
        PracticeQuestion,
        on_delete=models.CASCADE,
        related_name="student_progress",
        db_index=True,
    )
    status     = models.CharField(
        max_length=20,
        choices=PROGRESS_STATUS_CHOICES,
        default=PROGRESS_NOT_VISITED,
        db_index=True,
    )
    first_visited_at   = models.DateTimeField(null=True, blank=True)
    first_attempted_at = models.DateTimeField(null=True, blank=True)
    first_completed_at = models.DateTimeField(null=True, blank=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = "practice_question_progress"
        unique_together = [("student", "question")]
        indexes = [
            models.Index(fields=["student", "question"], name="idx_pqp_student_question"),
            models.Index(fields=["student"],             name="idx_pqp_student"),
        ]

    def __str__(self):
        return f"{self.student_id} | Q{self.question_id} | {self.status}"


# ── Student MCQ Attempt ───────────────────────────────────────────────────────

class PracticeQuestionAttempt(models.Model):
    """
    Records every MCQ submission by a student.
    selected_option_ids : JSON list of PracticeQuestionOption UUIDs (as strings).
    is_correct          : True only when the selected set exactly matches the
                          correct option set for the question.
    attempt_number      : 1-based, per (student, question) pair.
    """
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student             = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="question_attempts",
        db_index=True,
    )
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
            models.Index(fields=["student", "question"], name="idx_pqa_student_question"),
        ]

    def __str__(self):
        return f"{self.student_id} | Q{self.question_id} | #{self.attempt_number} | {'✓' if self.is_correct else '✗'}"
