import hashlib
import uuid
from django.db import models


# ── Question Papers ───────────────────────────────────────────────────────────

class QuestionPaper(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_id = models.UUIDField(db_index=True)
    title          = models.CharField(max_length=255)
    description    = models.TextField(blank=True, default="")
    # Shown to students as a mandatory read-before-you-start gate (Rules
    # button, admin/assessments/papers/<id>/). Editable even while the paper
    # is locked — unlike title/description/questions, it's read-only
    # guidance text that can't corrupt exam integrity or scores, so there's
    # no reason to freeze it once assigned (see AdminPaperInstructionsView).
    instructions   = models.TextField(blank=True, default="")
    # JWT user_id claim — no FK (cross-service isolation, matches
    # practice-service's convention for admin-authored content)
    created_by     = models.UUIDField()
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assessment_question_papers"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def is_locked(self) -> bool:
        """A paper becomes read-only the moment it has at least one
        BatchAssignment in SCHEDULED, LIVE, or CLOSED status (i.e. any
        assignment that isn't merely a rejected/never-created attempt) —
        editing questions/options after students may already be relying on
        them would silently corrupt exam integrity and any already-computed
        scores (AT15). Admins wanting a changed version must duplicate the
        paper into a new one and assign that instead. See
        LIVETRACKER2_V1.md Task 3.2 for the full rationale."""
        return self.assignments.filter(
            status__in=[ASSIGNMENT_STATUS_SCHEDULED, ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_CLOSED]
        ).exists()


# ── Question Sets ──────────────────────────────────────────────────────────────

class QuestionSet(models.Model):
    id    = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paper = models.ForeignKey(
        QuestionPaper,
        on_delete=models.CASCADE,
        related_name="sets",
        db_index=True,
    )
    label = models.CharField(max_length=50)  # e.g. "Set A", "Set B"
    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        db_table = "assessment_question_sets"
        ordering = ["order"]
        unique_together = [("paper", "label")]

    def __str__(self):
        return f"{self.paper.title} — {self.label}"

    def total_marks(self) -> int:
        return self.questions.aggregate(total=models.Sum("marks"))["total"] or 0


# ── Question Sections ─────────────────────────────────────────────────────────
# A grouping layer between a QuestionSet and its Questions (e.g. "Quantitative
# Aptitude", "Logical Reasoning" within one set). Questions still carry a
# direct FK to QuestionSet too (unchanged) so existing set-level aggregates
# (total_marks, question counts) keep working untouched — section is an
# additional organisational layer, not a replacement for the set relationship.

class QuestionSection(models.Model):
    id     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    set    = models.ForeignKey(
        QuestionSet,
        on_delete=models.CASCADE,
        related_name="sections",
        db_index=True,
    )
    title  = models.CharField(max_length=100)
    order  = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        db_table = "assessment_question_sections"
        ordering = ["order"]
        unique_together = [("set", "title")]

    def __str__(self):
        return f"{self.set.label} — {self.title}"


# ── Questions ──────────────────────────────────────────────────────────────────

QUESTION_TYPE_MCQ = "mcq"
QUESTION_TYPE_CHOICES = [
    (QUESTION_TYPE_MCQ, "Multiple Choice"),
]

MCQ_TYPE_SINGLE   = "single"
MCQ_TYPE_MULTIPLE = "multiple"
MCQ_TYPE_CHOICES = [
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


class Question(models.Model):
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    set             = models.ForeignKey(
        QuestionSet,
        on_delete=models.CASCADE,
        related_name="questions",
        db_index=True,
    )
    section         = models.ForeignKey(
        QuestionSection,
        on_delete=models.CASCADE,
        related_name="questions",
        db_index=True,
    )
    question_number = models.PositiveIntegerField(default=0, db_index=True)

    question_type = models.CharField(
        max_length=10, choices=QUESTION_TYPE_CHOICES, default=QUESTION_TYPE_MCQ,
    )
    mcq_type = models.CharField(
        max_length=10, choices=MCQ_TYPE_CHOICES, default=MCQ_TYPE_SINGLE,
    )
    question_content_type = models.CharField(
        max_length=10, choices=QUESTION_CONTENT_CHOICES, default=QUESTION_CONTENT_TEXT,
    )
    question_text = models.TextField(blank=True, default="")
    question_image_key = models.CharField(max_length=500, blank=True, default="")
    # Real size from storage (core.storage.verify_uploaded_image), not
    # client-reported — used to enforce the per-paper image storage quota
    # (core.upload_constraints.MAX_BYTES_PER_PAPER).
    question_image_size_bytes = models.BigIntegerField(null=True, blank=True)

    marks = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assessment_questions"
        ordering = ["question_number"]
        indexes = [
            models.Index(fields=["set", "question_number"], name="idx_aq_set_number"),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and self.section_id is None:
            # Callers that don't explicitly pick a section (older/internal
            # code, tests) fall into a default "Section 1" per set rather
            # than erroring — mirrors the migration 0018 backfill for
            # pre-existing rows. The admin question-creation endpoint always
            # passes an explicit section from the section-first UI, so this
            # is a safety net, not the primary path.
            self.section, _ = QuestionSection.objects.get_or_create(
                set=self.set, title="Section 1", defaults={"order": 1},
            )
        if self._state.adding and self.question_number == 0:
            from django.db.models import Max
            # Scoped to this set — every set's questions are numbered
            # 1, 2, 3... independently, mirroring practice-service's
            # per-section numbering (a global counter would make a brand-new
            # set's first question display as e.g. "Question #847").
            max_num = Question.objects.filter(set=self.set).aggregate(
                m=Max("question_number")
            )["m"] or 0
            self.question_number = max_num + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Q{self.question_number} ({self.set.label})"


# ── Question Options ─────────────────────────────────────────────────────────

OPTION_CONTENT_TEXT  = "text"
OPTION_CONTENT_IMAGE = "image"
OPTION_CONTENT_CHOICES = [
    (OPTION_CONTENT_TEXT,  "Text"),
    (OPTION_CONTENT_IMAGE, "Image"),
]


class QuestionOption(models.Model):
    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
        db_index=True,
    )
    label = models.CharField(max_length=5)  # "A", "B", "C", "D"...
    content_type = models.CharField(
        max_length=10, choices=OPTION_CONTENT_CHOICES, default=OPTION_CONTENT_TEXT,
    )
    text       = models.TextField(blank=True, default="")
    image_key  = models.CharField(max_length=500, blank=True, default="")
    is_correct = models.BooleanField(default=False)
    order      = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assessment_question_options"
        ordering = ["order"]

    def __str__(self):
        return f"Q{self.question_id} | {self.label} | {'correct' if self.is_correct else 'wrong'}"


# ── Batch Assignments ────────────────────────────────────────────────────────

ASSIGNMENT_STATUS_SCHEDULED = "SCHEDULED"
ASSIGNMENT_STATUS_LIVE      = "LIVE"
ASSIGNMENT_STATUS_CLOSED    = "CLOSED"
ASSIGNMENT_STATUS_CHOICES = [
    (ASSIGNMENT_STATUS_SCHEDULED, "Scheduled"),
    (ASSIGNMENT_STATUS_LIVE,      "Live"),
    (ASSIGNMENT_STATUS_CLOSED,    "Closed"),
]


class BatchAssignment(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paper = models.ForeignKey(
        QuestionPaper,
        on_delete=models.PROTECT,  # a paper with any assignment is locked (Task 3.2) — never let a cascade silently delete assignment history
        related_name="assignments",
        db_index=True,
    )
    # From user-service — no cross-service FK, matches the isolation
    # convention already established in practice-service/user-service.
    batch_id       = models.UUIDField(db_index=True)
    institution_id = models.UUIDField(db_index=True)
    # Empty list (the default) means every department in the batch — this
    # assignment's roster snapshot (allocation.py's
    # snapshot_roster_and_allocate) only narrows to specific departments
    # when this is non-empty. department itself is free-text on Student
    # (user-service), no fixed enum — matched case-insensitively at
    # allocation time, same convention as the existing department filter
    # on the admin results table (department__iexact).
    departments = models.JSONField(default=list, blank=True)

    global_start_time  = models.DateTimeField(null=True, blank=True)  # set at creation or left null until start/ (Task 3.2)
    global_expire_time = models.DateTimeField()
    exam_duration_minutes = models.PositiveIntegerField()
    # Admin-editable per assignment — lives here (not on QuestionPaper)
    # because the same paper can be reused across assignments with
    # different pass bars (Decision #4, docs/assessment-service-api.md).
    pass_cutoff_percentage = models.PositiveIntegerField(default=40)
    # Per-assignment, not per-paper (same reasoning as pass_cutoff_percentage
    # above) — an admin may want the same paper's score hidden for one batch
    # (e.g. a diagnostic pre-test) but shown for another. Read by
    # StudentSubmitView (right after submit) and StudentResultsView (past
    # results list) — both null out score/total_marks/percentage/passed
    # when this is False, never just hide them client-side.
    show_result_to_student = models.BooleanField(default=True)

    status = models.CharField(
        max_length=10, choices=ASSIGNMENT_STATUS_CHOICES, default=ASSIGNMENT_STATUS_SCHEDULED, db_index=True,
    )
    # JWT user_id claim — no FK, matches QuestionPaper.created_by's convention.
    created_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assessment_batch_assignments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["batch_id"], name="idx_aba_batch_id"),
            models.Index(fields=["status", "global_expire_time"], name="idx_aba_status_expire"),
        ]

    def __str__(self):
        return f"{self.paper.title} → batch {self.batch_id} ({self.status})"


class StudentSetAllocation(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(
        BatchAssignment,
        on_delete=models.CASCADE,
        related_name="allocations",
        # db_index=False (Task 11.1's index audit): Django's FK default
        # would auto-create a single-column index on assignment_id here,
        # but the unique_together index below already covers
        # assignment_id-only lookups (e.g. `assignment.allocations.count()`)
        # via its leftmost column — a second index would just double the
        # per-row write cost of every roster-snapshot bulk_create for zero
        # query benefit.
        db_index=False,
    )
    # The JWT user_id claim (matches request.user.id when the student later
    # authenticates) — snapshotted from user-service's roster at assignment
    # creation time, not a live cross-service FK. See core/user_service_client.py.
    # Kept indexed on its own (unlike `assignment` above): student_id is the
    # *second* column in the unique_together pair, so a query that filters
    # by student_id alone (e.g. "this student's allocations across every
    # assignment") can't use that composite index's leftmost prefix and
    # genuinely needs this standalone index.
    student_id = models.UUIDField(db_index=True)
    set = models.ForeignKey(
        QuestionSet,
        on_delete=models.PROTECT,  # a set with allocations is part of a locked paper (Task 3.2) — never silently delete allocation history
        related_name="allocations",
        db_index=True,
    )
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "assessment_student_set_allocations"
        # unique_together on exactly these two fields already creates a
        # unique btree index covering both single-column (assignment_id=X)
        # and combined (assignment_id=X AND student_id=Y) lookups (Task
        # 11.1's index audit) — a separate explicit index on the same pair
        # would be byte-for-byte redundant, doubling write overhead on
        # every roster snapshot's bulk_create with zero query benefit.
        unique_together = [("assignment", "student_id")]

    def __str__(self):
        return f"{self.student_id} → {self.set.label} ({self.assignment_id})"


def distribute_set_for_student(student_id, assignment_id, set_count: int) -> int:
    """Deterministic-but-unpredictable set index (0-based) for a given
    student within a given assignment. Same student always lands on the
    same set on a re-run (idempotent — Task 3.1's Test Suite), but there is
    no visible ordering pattern a room full of students could exploit
    (closes AT7) since it's a cryptographic hash, not e.g. student_id % N
    (which would cluster consecutively-created accounts on the same set).

    Pure function — no DB access — so it's trivially unit-testable and
    reusable from both assignment creation (Task 3.1) and resync-roster
    (Task 3.2).
    """
    digest = hashlib.sha256(f"{student_id}:{assignment_id}".encode("utf-8")).hexdigest()
    return int(digest, 16) % set_count


# ── Assessment Sessions ───────────────────────────────────────────────────────
# See docs/adr/001-assessment-timer-architecture.md for the full state-machine
# rationale — the database (not an active process) is the source of truth for
# timing, and every transition below is either an authenticated action or a
# now()-gated conditional UPDATE, never reachable from raw client data.

# NOT_STARTED is conceptual only — a session row is created by start-session
# (Task 5.1) already IN_PROGRESS, so no row is ever actually stored with this
# value. It's kept in the choices tuple because both AssessmentSession.status
# and ResultSummary.status (which "mirrors session's terminal status" per
# docs/assessment-service-api.md) share this same enum.
SESSION_STATUS_NOT_STARTED       = "NOT_STARTED"
SESSION_STATUS_IN_PROGRESS       = "IN_PROGRESS"
SESSION_STATUS_SUBMITTED         = "SUBMITTED"
SESSION_STATUS_AUTO_SUBMITTED    = "AUTO_SUBMITTED"
# Reserved, not currently set anywhere (audited 2026-08-17): ADR 001's
# original design was a ResultSummary row written with this status once an
# allocated-but-never-started student's assignment closes, so Results could
# distinguish "didn't attempt" from "attempted and scored." What actually
# shipped instead is simpler and needs no extra write path at all — a
# no-show has no AssessmentSession row, so `views.py`'s
# `_build_results_queryset` (built from StudentSetAllocation, not
# ResultSummary) just reads that absence as `exam_status="pending"` at
# request time. That already serves the same "who never showed up" need
# the admin Results table has today, so this value is kept defined (both
# AssessmentSession.status and ResultSummary.status share this enum, per
# docs/assessment-service-api.md) rather than wired up for real — implementing
# the original write-path would mean auditing every completion-rate/
# analytics aggregate that currently assumes a ResultSummary row means
# "actually completed," to make sure an EXPIRED_UNSTARTED row wouldn't get
# miscounted as one. Not worth that risk for a state the read-time
# computation already covers.
SESSION_STATUS_EXPIRED_UNSTARTED = "EXPIRED_UNSTARTED"
SESSION_STATUS_CHOICES = [
    (SESSION_STATUS_NOT_STARTED,       "Not started"),
    (SESSION_STATUS_IN_PROGRESS,       "In progress"),
    (SESSION_STATUS_SUBMITTED,         "Submitted"),
    (SESSION_STATUS_AUTO_SUBMITTED,    "Auto-submitted"),
    (SESSION_STATUS_EXPIRED_UNSTARTED, "Expired without starting"),
]

# Terminal statuses a session can be finalized into — used by scoring.py to
# validate the target status a caller passes to finalize_sessions().
SESSION_TERMINAL_STATUSES = {SESSION_STATUS_SUBMITTED, SESSION_STATUS_AUTO_SUBMITTED}


class AssessmentSession(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Nullable since 2026-08-27 — an admin "mock test" trial run (taken
    # either before an assignment exists, from the assign form's Final
    # Review step, or repeatably afterward from an existing assignment's
    # toolbar) is a real session on a real QuestionSet, but deliberately has
    # no BatchAssignment: no batch, no roster, no global timer, no
    # malpractice tracking. NULL here is the sole, unambiguous marker of a
    # trial session — every real student session still always has one.
    assignment = models.ForeignKey(
        BatchAssignment,
        on_delete=models.PROTECT,  # a session with results must never silently vanish via cascade
        related_name="sessions",
        db_index=True,
        null=True, blank=True,
    )
    # JWT user_id claim — matches StudentSetAllocation.student_id's
    # convention. For a trial session (assignment is None) this holds the
    # trialing ADMIN's own user_id instead of a student's — there's no
    # separate "who does this session belong to" concept, and reusing this
    # column lets every ownership check across the codebase
    # (`student_id=request.user.id`) work unchanged for both cases. It also
    # means Postgres's unique_together below never blocks a retake: two
    # trial rows both have assignment=NULL, and SQL never considers two
    # NULLs equal for uniqueness purposes, so the same admin can retake the
    # same paper as many times as they want.
    student_id = models.UUIDField(db_index=True)
    set = models.ForeignKey(
        QuestionSet,
        on_delete=models.PROTECT,
        related_name="sessions",
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    # Computed exactly once at creation (Task 5.1) as
    # min(now() + exam_duration_minutes, global_expire_time) — never
    # recomputed on resume. The sole exception is the admin extend/ action
    # (Task 3.2/4.1), which patches this column directly.
    ends_at = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=20, choices=SESSION_STATUS_CHOICES, default=SESSION_STATUS_IN_PROGRESS, db_index=True,
    )

    class Meta:
        db_table = "assessment_sessions"
        ordering = ["-started_at"]
        # One session per student per assignment, ever (Decision #3,
        # docs/assessment-service-api.md — no retake/re-attempt in V1). This
        # is also what makes start-session (Task 5.1) safely idempotent via
        # get_or_create: a concurrent double-call collapses to one row at
        # the DB level, not just in application logic.
        unique_together = [("assignment", "student_id")]
        indexes = [
            # The beat sweep's core query (ADR 001 "Capacity Planning") —
            # must stay sub-second even at tens of thousands of sessions.
            models.Index(fields=["status", "ends_at"], name="idx_as_status_ends_at"),
        ]

    def __str__(self):
        return f"session {self.id} ({self.status})"


class ResultSummary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # OneToOne, not a plain FK — a session has at most one final result,
    # ever. This also gives finalize_sessions() a DB-level uniqueness
    # backstop against double-scoring under a rare concurrent-caller race,
    # on top of the primary race-safety mechanism (the conditional UPDATE
    # on AssessmentSession.status in scoring.py).
    session    = models.OneToOneField(
        AssessmentSession, on_delete=models.PROTECT, related_name="result",
    )
    # Nullable since 2026-08-27, mirroring AssessmentSession.assignment
    # above — a trial (admin mock test) result has no assignment. See that
    # field's comment for why NULL is the sole trial marker, and
    # scoring.py's finalize_sessions() for how institution_id (still NOT
    # NULL below — every result needs SOME tenant) is resolved from the
    # paper instead of the assignment when this is None.
    assignment = models.ForeignKey(
        BatchAssignment, on_delete=models.PROTECT, related_name="results", db_index=True,
        null=True, blank=True,
    )
    # Trial results: the trialing admin's own user_id — see
    # AssessmentSession.student_id's comment.
    student_id     = models.UUIDField(db_index=True)
    institution_id = models.UUIDField(db_index=True)

    started_at       = models.DateTimeField()
    ended_at         = models.DateTimeField()
    duration_seconds = models.PositiveIntegerField()

    # Computed at finalize time (scoring.py's finalize_sessions(), Task
    # 5.2) from the frozen AssessmentResponse set — exact-match multi-select
    # policy (Decision #1, docs/assessment-service-api.md), no partial credit.
    score       = models.PositiveIntegerField(default=0)
    total_marks = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=SESSION_STATUS_CHOICES, db_index=True)

    # Populated by Task 6.2 — a single bool can't say *which* of the
    # anti-cheat thresholds fired, hence the accompanying reasons list.
    malpractice_flag   = models.BooleanField(default=False)
    malpractice_reasons = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "assessment_result_summaries"
        ordering = ["-ended_at"]
        indexes = [
            models.Index(fields=["assignment", "student_id"], name="idx_ars_assignment_student"),
            # Task 7.1's results-table query filters by exactly this pair
            # together (institution_id re-validates the assignment lookup's
            # own scoping at the row level, closes AT8) — a composite index
            # serves that WHERE clause better than two separate single-column
            # indexes would.
            models.Index(fields=["assignment", "institution_id"], name="idx_ars_assignment_institution"),
            # Supports raw-score filtering/sorting (Task 8.x's analytics and
            # any future admin view that needs it) — Task 7.1's own
            # table/export use the computed `percentage` annotation instead
            # (cross-set comparisons need percentage, not raw score), but
            # this index is still what Postgres would use for the
            # `score`/`total_marks` columns that annotation reads from.
            models.Index(fields=["assignment", "score"], name="idx_ars_assignment_score"),
        ]

    def __str__(self):
        return f"result {self.id} for session {self.session_id} ({self.status})"


class AssessmentResponse(models.Model):
    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # db_index=False (Task 11.1's index audit, same reasoning as
    # StudentSetAllocation.assignment above): the unique_together index on
    # (session, question) below already serves session-only lookups via its
    # leftmost column (e.g. StudentSessionQuestionsView's saved-answers
    # query, scoring.py's finalize-time scoring pass) — this is the
    # single hottest write path in the service (every per-question
    # autosave), so an extra redundant index here has an outsized cost.
    session  = models.ForeignKey(
        AssessmentSession, on_delete=models.PROTECT, related_name="responses", db_index=False,
    )
    # Kept indexed (unlike `session` above): question is the *second*
    # column in the (session, question) pair, so it can't ride that
    # composite index's leftmost prefix — Task 8.1's per-question
    # difficulty aggregation filters/groups by question_id across many
    # sessions and genuinely needs this standalone index.
    question = models.ForeignKey(
        Question, on_delete=models.PROTECT, related_name="assessment_responses", db_index=True,
    )
    selected_option_ids = models.JSONField(default=list, blank=True)
    # Computed once, at finalize time (scoring.py's finalize_sessions()) —
    # NOT recomputed on every autosave. Stay at their defaults (False/0)
    # for the entire duration the exam is in progress.
    is_correct    = models.BooleanField(default=False)
    marks_awarded = models.PositiveIntegerField(default=0)
    # auto_now (not auto_now_add) — an autosave is an upsert; each
    # re-answer of the same question bumps this timestamp.
    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assessment_responses"
        # An autosave is an upsert, not an insert — replays are naturally
        # idempotent (closes AT4).
        unique_together = [("session", "question")]
        # No separate session-only index (Task 11.1's index audit found one
        # here previously, idx_ar_session, and removed it): the `session`
        # FK's own db_index=True already indexes session_id alone, and the
        # unique_together index above additionally covers it as a leftmost
        # prefix — a third index on the same column was pure write
        # overhead on the hottest path in the whole service (every
        # per-question autosave).

    def __str__(self):
        return f"response to Q{self.question_id} in session {self.session_id}"


# ── Activity Logs (anti-cheat, Task 6.1/6.2) ────────────────────────────────

ACTIVITY_EVENT_TAB_SWITCH      = "tab_switch"
ACTIVITY_EVENT_WINDOW_BLUR     = "window_blur"
ACTIVITY_EVENT_FULLSCREEN_EXIT = "fullscreen_exit"
ACTIVITY_EVENT_COPY            = "copy"
ACTIVITY_EVENT_PASTE           = "paste"
ACTIVITY_EVENT_CONTEXTMENU     = "contextmenu"
# Added 2026-08-18 — full-transparency audit trail, not just anti-cheat
# signals: every student action during the exam, plus session-affecting
# admin actions, so the timeline (AdminSessionTimelineView) is a complete
# record, not just a violation log. question_answered/question_answer_changed
# are written server-side (StudentAnswerView), never by the client batcher —
# the server already knows definitively whether a PUT was a first answer or
# a genuine change, so there's no client-side detection to get wrong or spoof.
ACTIVITY_EVENT_QUESTION_ANSWERED       = "question_answered"
ACTIVITY_EVENT_QUESTION_ANSWER_CHANGED = "question_answer_changed"
# Client-detected, same best-effort caveat as the existing signals above —
# see useActivityCapture.ts's docstring for exactly what this can and can't see.
ACTIVITY_EVENT_SCREENSHOT_ATTEMPT = "screenshot_attempt"
# Logged once connectivity is restored (with the true original loss time in
# occurred_at and duration_seconds in metadata) — a client can't reliably
# POST an event about losing its own network at the exact moment it happens.
ACTIVITY_EVENT_CONNECTION_LOST = "connection_lost"
# Server-authored (AdminAssignmentExtendSessionView), not client-reported —
# an administrative action that affects the exam, not a student action, but
# still part of "everything that happened during this session."
ACTIVITY_EVENT_ADMIN_EXTENDED_TIME = "admin_extended_time"
# Client-detected (useActivityCapture.ts, via the exam page's active-question
# navigation) — logged once the student navigates away from a question (or
# submits), covering only foreground/visible time: the tab-hidden window is
# excluded, so switching away mid-question doesn't inflate its time. Feeds
# both this session's own timeline and the cohort-level "average time per
# question" analytics (assessments/views.py's _question_time_spent).
ACTIVITY_EVENT_QUESTION_TIME_SPENT = "question_time_spent"
ACTIVITY_EVENT_TYPE_CHOICES = [
    (ACTIVITY_EVENT_TAB_SWITCH,      "Tab switch"),
    (ACTIVITY_EVENT_WINDOW_BLUR,     "Window blur"),
    (ACTIVITY_EVENT_FULLSCREEN_EXIT, "Fullscreen exit"),
    (ACTIVITY_EVENT_COPY,            "Copy"),
    (ACTIVITY_EVENT_PASTE,           "Paste"),
    (ACTIVITY_EVENT_CONTEXTMENU,     "Right-click"),
    (ACTIVITY_EVENT_QUESTION_ANSWERED,       "Answered a question"),
    (ACTIVITY_EVENT_QUESTION_ANSWER_CHANGED, "Changed an answer"),
    (ACTIVITY_EVENT_SCREENSHOT_ATTEMPT,      "Screenshot attempt"),
    (ACTIVITY_EVENT_CONNECTION_LOST,         "Lost internet connection"),
    (ACTIVITY_EVENT_ADMIN_EXTENDED_TIME,     "Admin extended exam time"),
    (ACTIVITY_EVENT_QUESTION_TIME_SPENT,     "Time spent on a question"),
]


# How long a raw ActivityLog row (a single tab-switch/copy/paste/etc.
# event) is kept before the daily purge_old_activity_logs task (tasks.py)
# deletes it. This is a storage/cost retention window for the raw audit
# trail specifically — NOT the exam record itself: AssessmentResponse,
# ResultSummary, and every score/pass-fail/malpractice_flag/reasons value
# are permanent academic records, never touched by this. A single source
# of truth (not duplicated as a bare "15" in tasks.py and the admin
# timeline view's response) so the purge task and the UI's own "deleted
# after N days" notice can never silently drift apart.
ACTIVITY_LOG_RETENTION_DAYS = 15


class ActivityLog(models.Model):
    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        AssessmentSession, on_delete=models.PROTECT, related_name="activity_logs", db_index=True,
    )
    # 30: comfortably fits the longest current value
    # (question_answer_changed, 23 chars) with headroom for a future one.
    event_type = models.CharField(max_length=30, choices=ACTIVITY_EVENT_TYPE_CHOICES, db_index=True)
    # Client-reported event time — unlike session.ends_at/scoring (AT1),
    # trusting the client here is low-risk: falsifying WHEN a tab-switch
    # appeared to happen doesn't grant extra marks or time, it only
    # pollutes the student's own audit trail. Falls back to server now()
    # if missing/unparseable (views.py). created_at (below) is the
    # separate, always-server-authoritative receipt time, for the rare
    # case a discrepancy between the two ever needs auditing.
    occurred_at = models.DateTimeField(db_index=True)
    metadata    = models.JSONField(default=dict, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "assessment_activity_logs"
        ordering = ["occurred_at"]
        indexes = [
            models.Index(fields=["session", "event_type"], name="idx_al_session_type"),
        ]

    def __str__(self):
        return f"{self.event_type} @ {self.occurred_at} (session {self.session_id})"


class FailedJob(models.Model):
    """Task 13.1's dead-letter mechanism for Celery task failures (AT12).

    Not institution-scoped: the two periodic sweep tasks
    (sweep_expired_assignments/sweep_expired_sessions) operate across every
    institution in one pass, so a failure here is an operational/ops-team
    concern, not a tenant-facing one — deliberately not exposed through the
    same per-institution admin API surface the rest of this service uses.
    Written by assessments/tasks.py's on_failure() hook, which Celery calls
    automatically once a task's own retries (max_retries, see tasks.py) are
    exhausted — this table only ever holds *permanently* failed attempts,
    never a task still mid-retry.

    Queried directly (Django shell / a future ops tool), matching Task
    13.2's own "operational dashboard (or documented queries)" allowance —
    see docs/runbooks/assessment-exam-day.md for the exact query an
    on-call engineer runs to find and triage these."""
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_name  = models.CharField(max_length=255, db_index=True)
    task_id    = models.CharField(max_length=255, blank=True, default="")
    args       = models.JSONField(default=list, blank=True)
    kwargs     = models.JSONField(default=dict, blank=True)
    error      = models.TextField()
    traceback  = models.TextField(blank=True, default="")
    attempts   = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    # Set by whoever (a human, or a future reprocessing tool) handles this
    # entry — the runbook's "reprocess a stuck failed job" step ends by
    # marking it resolved so the same failure doesn't get re-investigated.
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "assessment_failed_jobs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task_name", "resolved_at"], name="idx_fj_task_resolved"),
        ]

    def __str__(self):
        status = "resolved" if self.resolved_at else "UNRESOLVED"
        return f"{self.task_name} failed ({status}, {self.attempts} attempt(s)) — {self.id}"
