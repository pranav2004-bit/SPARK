import hashlib
import uuid
from django.db import models


# ── Essay Papers ─────────────────────────────────────────────────────────────
# Mirrors assessment-service's QuestionPaper shape (title/description/
# institution_id/created_by). No status field (see LIVETRACKER3_V1.md Task
# 2.1's correction note).

class EssayPaper(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_id = models.UUIDField(db_index=True)
    title          = models.CharField(max_length=255)
    description    = models.TextField(blank=True, default="")
    # JWT user_id claim — no FK (cross-service isolation, matches
    # assessment-service's QuestionPaper.created_by convention).
    created_by     = models.UUIDField()
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "essay_papers"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def is_locked(self) -> bool:
        """A paper becomes read-only the moment it has at least one
        EssayAssignment in SCHEDULED/LIVE/CLOSED status — added in Phase 3
        (Task 3.2), not Phase 2, since it needs `self.assignments`, the
        reverse FK from EssayAssignment below. Mirrors
        assessment-service's QuestionPaper.is_locked() exactly, including
        its own Task 3.2 timing — see LIVETRACKER3_V1.md Task 2.1's
        correction note for why this was deliberately not built earlier."""
        return self.assignments.filter(
            status__in=[ASSIGNMENT_STATUS_SCHEDULED, ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_CLOSED]
        ).exists()


# ── Essay Sets ───────────────────────────────────────────────────────────────
# Anti-collusion prompt variants, mirroring assessment-service's QuestionSet
# concept — used by Phase 3's Latin-square/hash set-distribution.

class EssaySet(models.Model):
    id    = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paper = models.ForeignKey(
        EssayPaper,
        on_delete=models.CASCADE,
        related_name="sets",
        # Task 16.1 — a standalone index here is redundant: unique_together
        # below already covers paper-only lookups via its own leftmost
        # column (the same reasoning already applied to
        # EssayStudentSetAllocation.assignment below, missed here until
        # this phase's own audit).
        db_index=False,
    )
    label = models.CharField(max_length=50)  # e.g. "Set A", "Set B"
    order = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        db_table = "essay_sets"
        ordering = ["order"]
        unique_together = [("paper", "label")]

    def __str__(self):
        return f"{self.paper.title} — {self.label}"


# ── Essay Questions ──────────────────────────────────────────────────────────
# Exactly one question per set (this tracker's explicit requirement — unlike
# assessment-service's Question, which is many-per-set via a plain FK, this
# is a OneToOneField so "one question per set" is a real database constraint,
# not just an application-level rule that could be bypassed by a bug).

class EssayQuestion(models.Model):
    id    = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    set   = models.OneToOneField(
        EssaySet,
        on_delete=models.CASCADE,
        related_name="question",
    )
    # The prompt/topic the student writes about.
    question_text = models.TextField()
    # The "admin defined prompt" from the workflow requirement — the
    # LLM-evaluation rubric/instructions for THIS question specifically,
    # sent to the LLM alongside the question text and the student's
    # response (see docs/adr/003-essay-llm-evaluation-pipeline.md Decision 2).
    # Stored per-question, not hardcoded, since different questions need
    # different evaluation criteria.
    llm_rubric_prompt = models.TextField()
    word_limit = models.PositiveIntegerField()
    time_limit_minutes = models.PositiveIntegerField()
    # Fixed at 10 per the workflow spec, but kept as a field (not a
    # hardcoded literal) for future flexibility — matches this task's own
    # explicit instruction.
    max_score = models.PositiveIntegerField(default=10)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "essay_questions"

    def __str__(self):
        return f"Question for {self.set.label}"


# ── Essay Assignments (Phase 3) ──────────────────────────────────────────────

ASSIGNMENT_STATUS_SCHEDULED = "SCHEDULED"
ASSIGNMENT_STATUS_LIVE      = "LIVE"
ASSIGNMENT_STATUS_CLOSED    = "CLOSED"
ASSIGNMENT_STATUS_CHOICES = [
    (ASSIGNMENT_STATUS_SCHEDULED, "Scheduled"),
    (ASSIGNMENT_STATUS_LIVE,      "Live"),
    (ASSIGNMENT_STATUS_CLOSED,    "Closed"),
]


class EssayAssignment(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paper = models.ForeignKey(
        EssayPaper,
        on_delete=models.PROTECT,  # a paper with any assignment is locked (is_locked()) — never let a cascade silently delete assignment history
        related_name="assignments",
        db_index=True,
    )
    # From user-service — no cross-service FK, matches
    # assessment-service's BatchAssignment.batch_id convention.
    # Task 16.1 — field-level db_index=True here was a literal duplicate
    # of this Meta's own explicit idx_ea_batch_id below (two separate
    # indexes on the exact same single column) — removed, kept the
    # explicit one since it's named and this model's own convention
    # already lists indexes explicitly in Meta.
    batch_id       = models.UUIDField()
    institution_id = models.UUIDField(db_index=True)
    # Empty list (the default) means every department in the batch — matches
    # assessment-service's BatchAssignment.departments convention exactly
    # (free-text, matched case-insensitively at allocation time).
    departments = models.JSONField(default=list, blank=True)

    # The outer scheduling window. Per-attempt duration is NOT duplicated
    # here — unlike assessment-service's exam_duration_minutes, each
    # EssaySet's own EssayQuestion already carries its own
    # time_limit_minutes (Task 2.1). Phase 4's EssayAttempt computes
    # ends_at = min(now() + allocated_question.time_limit_minutes,
    # global_expire_time), the same pattern as ADR 001 with the per-question
    # duration substituted for a service-wide constant.
    global_start_time  = models.DateTimeField(null=True, blank=True)
    global_expire_time = models.DateTimeField()

    # Task 16.1 final-audit round — field-level db_index=True here was
    # redundant with this Meta's own idx_ea_status_expire below (status is
    # that composite's leftmost column), the exact same class of duplicate
    # already caught for batch_id above but missed for this field in the
    # first pass.
    status = models.CharField(
        max_length=10, choices=ASSIGNMENT_STATUS_CHOICES, default=ASSIGNMENT_STATUS_SCHEDULED, db_index=False,
    )
    # JWT user_id claim — no FK, matches EssayPaper.created_by's convention.
    created_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "essay_assignments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["batch_id"], name="idx_ea_batch_id"),
            models.Index(fields=["status", "global_expire_time"], name="idx_ea_status_expire"),
        ]

    def __str__(self):
        return f"{self.paper.title} → batch {self.batch_id} ({self.status})"


class EssayStudentSetAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(
        EssayAssignment,
        on_delete=models.CASCADE,
        related_name="allocations",
        db_index=False,  # unique_together below already covers assignment-only lookups via its leftmost column — matches assessment-service's StudentSetAllocation reasoning exactly
    )
    # The JWT user_id claim — snapshotted from user-service's roster at
    # assignment creation time, not a live cross-service FK.
    student_id = models.UUIDField(db_index=True)
    set = models.ForeignKey(
        EssaySet,
        on_delete=models.PROTECT,  # a set with allocations is part of a locked paper — never silently delete allocation history
        related_name="allocations",
        db_index=True,
    )
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "essay_student_set_allocations"
        unique_together = [("assignment", "student_id")]

    def __str__(self):
        return f"{self.student_id} → {self.set.label} ({self.assignment_id})"


def distribute_set_for_student(student_id, assignment_id, set_count: int) -> int:
    """Deterministic-but-unpredictable set index (0-based) for a given
    student within a given assignment — reused verbatim (SHA-256 hash of
    student_id:assignment_id) from assessment-service's own function, per
    ET7's explicit "do not reinvent" instruction. Same student always lands
    on the same set on a re-run (idempotent), with no visible ordering
    pattern a room full of students could exploit.

    Evaluated, not reinvented: CLAP's Latin-square mode (`(row+col) % N`)
    provably guarantees no adjacent neighbor shares a set, which this hash
    approach can only make statistically unlikely — a real, documented
    trade-off, not an oversight. Not adopted for V1 because it needs a real
    seating-chart (row, col) per student, and no such data model exists
    anywhere on this platform today (user-service has no seating-grid
    concept) — building one now would be new infrastructure, not "reuse,"
    for a platform-wide feature no other service has ever needed. CLAP's
    round-robin fallback (cycle sets over students sorted by roll number)
    needs no new data model, but it's an approximation of the same
    "correlates with physical seating" guarantee this hash approach doesn't
    claim at all — trading a working, already-tested primitive for a
    different, no-better-verified approximation isn't a improvement.
    ET7's own instruction to reuse this exact function, not reinvent it, is
    the deciding factor.
    """
    digest = hashlib.sha256(f"{student_id}:{assignment_id}".encode("utf-8")).hexdigest()
    return int(digest, 16) % set_count


# ── Essay Attempts (Phase 4) ─────────────────────────────────────────────────
# The direct analog of assessment-service's AssessmentSession and CLAP's
# StudentClapAssignment (ADR 002 Decision 1) — per-student, per-assignment
# timer/attempt state, separate from EssaySubmission (Phase 5), which is
# only ever created once an attempt reaches a terminal status (see this
# model's own docstring below and LIVETRACKER3_V1.md Task 4.1's notes).

# NOT_STARTED is conceptual only, matching assessment-service's own
# SESSION_STATUS_NOT_STARTED precedent exactly — an attempt row is created
# already IN_PROGRESS (see StudentEssayAttemptStartView, Task 4.1), so no row
# is ever actually stored with this value; kept in the choices tuple only
# because it's part of the state machine ADR 002 Decision 2 describes.
ATTEMPT_STATUS_NOT_STARTED       = "NOT_STARTED"
ATTEMPT_STATUS_IN_PROGRESS       = "IN_PROGRESS"
ATTEMPT_STATUS_SUBMITTED         = "SUBMITTED"
ATTEMPT_STATUS_AUTO_SUBMITTED    = "AUTO_SUBMITTED"
# Reserved, not currently set anywhere — same audited, deliberate precedent
# as assessment-service's own SESSION_STATUS_EXPIRED_UNSTARTED (see that
# model's own comment): a student who never started before the deadline
# passed simply has no EssayAttempt row at all (StudentEssayAttemptStartView
# rejects the start-attempt call with a 403 rather than creating an
# already-expired row), and the student list view already reads that
# absence correctly (`attempt_status` comes back null, and the frontend
# falls back to the assignment's own status pill). Kept defined, per the
# same enum both reference systems share, rather than wired up for real —
# there is no current read path that would benefit from a materialized row
# over the existing null-means-never-started convention.
ATTEMPT_STATUS_EXPIRED_UNSTARTED = "EXPIRED_UNSTARTED"
ATTEMPT_STATUS_CHOICES = [
    (ATTEMPT_STATUS_NOT_STARTED,       "Not started"),
    (ATTEMPT_STATUS_IN_PROGRESS,       "In progress"),
    (ATTEMPT_STATUS_SUBMITTED,         "Submitted"),
    (ATTEMPT_STATUS_AUTO_SUBMITTED,    "Auto-submitted"),
    (ATTEMPT_STATUS_EXPIRED_UNSTARTED, "Expired without starting"),
]

# Terminal statuses an attempt can be finalized into — mirrors
# assessment-service's SESSION_TERMINAL_STATUSES, used by finalize_attempts()
# to validate the target status a caller passes.
ATTEMPT_TERMINAL_STATUSES = {ATTEMPT_STATUS_SUBMITTED, ATTEMPT_STATUS_AUTO_SUBMITTED}


class EssayAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(
        EssayAssignment,
        on_delete=models.PROTECT,  # an attempt with a submission/score must never silently vanish via cascade
        related_name="attempts",
        # Task 16.1 — redundant: unique_together below already covers
        # assignment-only lookups (including the institution->assignment->
        # attempt join chain AdminSubmissionsListView and friends use) via
        # its own leftmost column, the exact same reasoning already
        # applied to EssayStudentSetAllocation.assignment, missed here.
        db_index=False,
    )
    # JWT user_id claim — matches EssayStudentSetAllocation.student_id's convention.
    student_id = models.UUIDField(db_index=True)
    set = models.ForeignKey(
        EssaySet,
        on_delete=models.PROTECT,
        related_name="attempts",
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    # Computed exactly once at creation (Task 4.1) as
    # min(now() + allocated_question.time_limit_minutes, assignment.global_expire_time)
    # — ADR 001's pattern with the per-question duration substituted for
    # assessment-service's per-exam constant. Never recomputed on resume.
    ends_at = models.DateTimeField(db_index=True)
    # Task 16.1 final-audit round — field-level db_index=True here was
    # redundant with this Meta's own idx_ea_att_status_ends_at below
    # (status is that composite's leftmost column), missed in the first
    # pass for the identical reason EssayAssignment.status was.
    status = models.CharField(
        max_length=20, choices=ATTEMPT_STATUS_CHOICES, default=ATTEMPT_STATUS_IN_PROGRESS, db_index=False,
    )
    # The in-progress autosaved draft — see LIVETRACKER3_V1.md Task 4.1's
    # second gap-fix note: EssaySubmission is never created before a
    # terminal status (ADR 002 Decision 1), so the draft the student is
    # actively writing has nowhere else to live but here.
    draft_response = models.TextField(blank=True, default="")

    # Populated at finalize time (Task 4.3's extension of finalize_attempts())
    # — mirrors assessment-service's ResultSummary.malpractice_flag/reasons,
    # but lives on the attempt itself here per ADR 002 Decision 1's own
    # reasoning ("malpractice is an attempt-time concern... belongs on the
    # attempt record, not the submission record").
    malpractice_flag   = models.BooleanField(default=False)
    malpractice_reasons = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "essay_attempts"
        ordering = ["-started_at"]
        # One attempt per student per assignment, ever — matches
        # assessment-service's AssessmentSession (no retake/re-attempt in
        # V1, per ADR 002 Decision 3's explicit deferral).
        unique_together = [("assignment", "student_id")]
        indexes = [
            # The beat sweep's core query — must stay sub-second even at
            # thousands of attempts, matches assessment-service's own
            # idx_as_status_ends_at precedent exactly.
            models.Index(fields=["status", "ends_at"], name="idx_ea_att_status_ends_at"),
        ]

    def __str__(self):
        return f"attempt {self.id} ({self.status})"


# ── Malpractice / Integrity Events (Phase 4, Task 4.3) ──────────────────────
# Reuses assessment-service's ActivityLog shape and fullscreen/tab-switch
# client behavior directly (Task 4.3's explicit instruction), scoped down to
# the event types that actually apply to a single-question essay-writing
# exam — not assessment-service's full set (question_answered/
# connection_lost/admin_extended_time etc. are MCQ- or feature-specific and
# don't have an essay-writing equivalent yet; adding them speculatively
# would be exactly the over-engineering this project's conventions warn
# against). `paste_attempt` is the one genuinely new addition Task 4.3 asks
# for — pasting into an essay response is a much stronger, essay-specific
# integrity signal than in an MCQ exam (there's no free-text field to paste
# into there at all).
MALPRACTICE_EVENT_TAB_SWITCH        = "tab_switch"
MALPRACTICE_EVENT_WINDOW_BLUR       = "window_blur"
MALPRACTICE_EVENT_FULLSCREEN_EXIT   = "fullscreen_exit"
MALPRACTICE_EVENT_COPY              = "copy"
MALPRACTICE_EVENT_PASTE_ATTEMPT     = "paste_attempt"
MALPRACTICE_EVENT_CONTEXTMENU       = "contextmenu"
MALPRACTICE_EVENT_SCREENSHOT_ATTEMPT = "screenshot_attempt"
# Phase 5, Task 5.4 — server-side only (never client-reported): recorded
# by plagiarism.py::check_text_similarity, not the browser activity
# capture hook above. Kept in this same model/enum rather than a separate
# table since it's the same underlying concept (an attempt-level integrity
# event), matching ADR 002 Decision 4's own framing of text-similarity as
# a malpractice signal.
MALPRACTICE_EVENT_TEXT_SIMILARITY = "text_similarity"
MALPRACTICE_EVENT_TYPE_CHOICES = [
    (MALPRACTICE_EVENT_TAB_SWITCH,        "Tab switch"),
    (MALPRACTICE_EVENT_WINDOW_BLUR,       "Window blur"),
    (MALPRACTICE_EVENT_FULLSCREEN_EXIT,   "Fullscreen exit"),
    (MALPRACTICE_EVENT_COPY,              "Copy"),
    (MALPRACTICE_EVENT_PASTE_ATTEMPT,     "Paste attempt"),
    (MALPRACTICE_EVENT_CONTEXTMENU,       "Right-click"),
    (MALPRACTICE_EVENT_SCREENSHOT_ATTEMPT, "Screenshot attempt"),
    (MALPRACTICE_EVENT_TEXT_SIMILARITY,   "Text similarity (plagiarism)"),
]


class EssayMalpracticeEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # FK'd to EssayAttempt, not EssaySubmission — matches ADR 002 Decision 1's
    # own reasoning: malpractice is an attempt-time concern, mirroring
    # assessment-service's ActivityLog -> AssessmentSession relationship.
    attempt = models.ForeignKey(
        EssayAttempt, on_delete=models.PROTECT, related_name="malpractice_events",
        # Task 16.1 — redundant with this Meta's own idx_eme_attempt_type
        # below (attempt is that composite's leftmost column).
        db_index=False,
    )
    event_type = models.CharField(max_length=30, choices=MALPRACTICE_EVENT_TYPE_CHOICES, db_index=True)
    # Client-reported event time — falsifying WHEN an event appeared to
    # happen doesn't grant any advantage (unlike ends_at/started_at), so
    # trusting the client here is low-risk, matching assessment-service's
    # ActivityLog.occurred_at convention exactly.
    occurred_at = models.DateTimeField(db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "essay_malpractice_events"
        ordering = ["occurred_at"]
        indexes = [
            models.Index(fields=["attempt", "event_type"], name="idx_eme_attempt_type"),
        ]

    def __str__(self):
        return f"{self.event_type} @ {self.occurred_at} (attempt {self.attempt_id})"


# ── Submission & LLM Evaluation Pipeline (Phase 5) ──────────────────────────
# ADR 002 Decision 2's pipeline state machine, reduced from CLAP's
# multi-domain shape to essay-service's single LLM domain (no RULES_COMPLETE
# — there is no rule-based component in an essay-only test). Created once an
# EssayAttempt reaches SUBMITTED/AUTO_SUBMITTED, never before (ADR 002
# Decision 1) — see scoring.py's finalize_attempts() for the one place this
# ever happens, per Task 5.1's own "one unified entry point" decision (see
# that function's own docstring for why a separate create-submission path
# was deliberately not built).
SUBMISSION_STATUS_PENDING        = "PENDING"
SUBMISSION_STATUS_LLM_PROCESSING = "LLM_PROCESSING"
SUBMISSION_STATUS_LLM_COMPLETE   = "LLM_COMPLETE"
SUBMISSION_STATUS_LLM_FAILED     = "LLM_FAILED"
# Phase 11's own report-generation sub-machine, added now that Task 11.1
# genuinely needs it — verified from CLAP's report_management.py (actually
# read, not inferred): a submission transitions LLM_COMPLETE ->
# REPORT_GENERATING (set by generate_essay_report itself, the instant it
# starts) -> REPORT_READY. REPORT_GENERATING is the exact state CLAP's own
# history warns about: an early regenerate implementation there set status
# to REPORT_GENERATING directly, but the generation task's own guard only
# ever proceeds when status == LLM_COMPLETE, so the task saw
# REPORT_GENERATING and skipped immediately — the report never actually
# regenerated. essays/views.py's own AdminReportRegenerateView (and the
# automatic dispatch from _transition_submission_status(), essays/tasks.py)
# both reset to LLM_COMPLETE, never to this state, for exactly this reason.
SUBMISSION_STATUS_REPORT_GENERATING = "REPORT_GENERATING"
SUBMISSION_STATUS_REPORT_READY   = "REPORT_READY"
SUBMISSION_STATUS_CHOICES = [
    (SUBMISSION_STATUS_PENDING,        "Pending"),
    (SUBMISSION_STATUS_LLM_PROCESSING, "LLM processing"),
    (SUBMISSION_STATUS_LLM_COMPLETE,   "LLM complete"),
    (SUBMISSION_STATUS_LLM_FAILED,     "LLM failed"),
    (SUBMISSION_STATUS_REPORT_GENERATING, "Report generating"),
    (SUBMISSION_STATUS_REPORT_READY,   "Report ready"),
]


class EssaySubmission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # OneToOne, not FK — ADR 002 Decision 1: exactly one submission per
    # attempt, ever (no retake in V1, Decision 3). PROTECT: a submission
    # with a score must never silently vanish via an attempt-side cascade.
    attempt = models.OneToOneField(
        EssayAttempt, on_delete=models.PROTECT, related_name="submission",
    )
    status = models.CharField(
        max_length=20, choices=SUBMISSION_STATUS_CHOICES, default=SUBMISSION_STATUS_PENDING, db_index=True,
    )
    # Phase 11 — the report's own rendered content. A self-contained HTML
    # string, not a separately-stored file (unlike CLAP's own PDF-on-S3
    # approach): essay-service has no S3 wiring and no PDF-rendering
    # dependency of its own, and a Text field is proportionate at this
    # service's own established scale (Task 0.4's capacity numbers —
    # tens-to-low-hundreds of reports, not thousands) — see
    # essays/reports.py's own module docstring for the full reasoning.
    # Null until generated; cleared back to null on regenerate (matching
    # CLAP's own report_url reset) so "no report yet" and "report exists"
    # are never ambiguous.
    report_html = models.TextField(null=True, blank=True)
    # Phase 11 — set once the report email is actually sent; reset to
    # null on regenerate/resend so a corrected report genuinely gets
    # redelivered rather than silently staying marked "sent" for stale
    # content (CLAP's own documented reliability lesson).
    email_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "essay_submissions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"submission {self.id} ({self.status})"


EVALUATED_BY_LLM = "llm"
EVALUATED_BY_ADMIN = "admin"
EVALUATED_BY_CHOICES = [
    (EVALUATED_BY_LLM, "LLM"),
    (EVALUATED_BY_ADMIN, "Admin"),
]


class EssayScore(models.Model):
    """Created exactly once per submission, normally by essays/tasks.py's
    evaluate_essay task (Task 5.2) — never re-created for that path
    (Decision 10's idempotency: an existing EssayScore is the task's own
    "already scored, skip" check). Phase 7, Task 7.1 adds the one other
    way a score comes to exist: an admin's manual override from a
    permanently-stuck DLQ entry, when the LLM just won't cooperate for
    one essay — see AdminSubmissionScoreOverrideView (essays/views.py).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.OneToOneField(
        EssaySubmission, on_delete=models.PROTECT, related_name="score",
    )
    # Always normalized to 0-10 regardless of the admin rubric's own
    # internal criteria count (ADR 003 Decision 2) — independent of
    # EssayQuestion.max_score, which downstream Results/Analytics phases
    # use for their own display scaling, not this field.
    score = models.PositiveSmallIntegerField()
    # {"overall": "...", "breakdown": {"<criterion>": {"score", "maxScore", "feedback"}, ...}}
    # — see ADR 003 Decision 2 for the exact contract. Never trusted beyond
    # this shape (Non-Negotiable Constraint §8): the model's output can only
    # ever become this one score + this one feedback string, nothing else.
    feedback = models.JSONField(default=dict)
    # True for the no-submission-guard's fixed 0-score path (Decision 6) —
    # lets Results/Analytics distinguish "genuinely scored 0 by the rubric"
    # from "never wrote anything" without parsing the feedback string.
    is_no_submission = models.BooleanField(default=False)
    # Phase 7, Task 7.1 — distinguishes an LLM-assigned score from a human
    # admin's manual override "in every later view" (Phase 8's own general
    # override reuses this same field for its own, broader override path —
    # one field for both mechanisms, not two parallel ones).
    evaluated_by = models.CharField(max_length=10, choices=EVALUATED_BY_CHOICES, default=EVALUATED_BY_LLM)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "essay_scores"

    def __str__(self):
        return f"score {self.score}/10 for submission {self.submission_id} ({self.evaluated_by})"


class EssayLLMTrace(models.Model):
    """Phase 7, Task 7.1's own "LLM trace/debug view" requirement — "the
    exact prompt used, the raw LLM response, the request id, and when it
    was evaluated", for an admin diagnosing "why did this essay get this
    score". Did not exist before this phase: evaluate_essay (Phase 5)
    only ever needed the PARSED score/feedback to do its own job and
    discarded everything else about the raw exchange — genuinely new
    storage this task requires, not a retrofit of an existing mechanism.

    One row per submission (OneToOne, matching EssayScore's own
    cardinality) — only ever written on a genuinely successful LLM call
    (see _evaluate_essay_impl), so a submission whose evaluation failed
    before ever getting a valid response (transient/malformed/permanent
    errors, or an admin's manual override) simply has no trace row; the
    trace view's own job is to say so plainly, not to fabricate one."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.OneToOneField(
        EssaySubmission, on_delete=models.PROTECT, related_name="llm_trace",
    )
    # The exact [{role, content}, ...] list sent — see prompts.py's own
    # build_evaluation_messages(), already redacted (pii_redaction.py) and
    # delimited (ADR 003 Decision 3) by the time it reaches here.
    prompt_messages = models.JSONField(default=list)
    # The raw response text BEFORE json.loads() — deliberately not just
    # the already-parsed score/feedback (EssayScore already has that);
    # this is for a human diagnosing "why did the model say what it
    # said," which needs the model's own exact words.
    raw_response = models.TextField()
    # OpenAI's own response.id — lets an admin cross-reference OpenAI's
    # own dashboard/support for a specific evaluation if ever needed.
    request_id = models.CharField(max_length=255, blank=True, default="")
    model_used = models.CharField(max_length=100, blank=True, default="")
    evaluated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "essay_llm_traces"

    def __str__(self):
        return f"LLM trace for submission {self.submission_id} ({self.model_used})"


# ── Dead-Letter Queue (Phase 5, Task 5.3) ───────────────────────────────────
# Ported from assessment-service's own FailedJob (assessments/models.py)
# per ET12's "reuse directly, don't build a parallel DLQ mechanism" — same
# core field shape and the same "resolved" convention (derived from
# resolved_at IS NULL, no separate status enum). One genuine addition:
# `dlq_retry_count`, which assessment-service's own FailedJob has no need
# for (it has no automatic sweeper at all — Task 5.3's own research
# confirmed this). Kept deliberately distinct from `attempts` (how many
# INLINE Celery retries happened before this entry was first created) —
# conflating the two would mean the automatic sweeper's circuit breaker
# and the original inline-retry count fight over the same number.
SUBMISSION_EVENT_STATUS_CHANGE   = "STATUS_CHANGE"
SUBMISSION_EVENT_DLQ_RECORDED    = "DLQ_RECORDED"
# Phase 7, Task 7.1 — an admin's own actions on a submission belong in the
# exact same chronological trail as the pipeline's own automatic events
# (the detail view already promises "full audit-log/event trail," not
# "automatic events only"), not a second, parallel admin-actions log.
SUBMISSION_EVENT_ADMIN_RETRIGGER = "ADMIN_RETRIGGER"
SUBMISSION_EVENT_ADMIN_OVERRIDE  = "ADMIN_OVERRIDE"
# Phase 11, Task 11.2 — delivery-status computation reads these, never a
# separately-maintained "bounced" field that can drift (verified from
# CLAP's email_management.py: it computes status live from event history,
# the same principle this event trail already follows for everything
# else). Reused here rather than a new, parallel event/model — the same
# "one unified audit trail" choice already made for admin actions above.
# Genuinely NOT ingested from a live email provider yet (no bounce/
# complaint webhook exists anywhere in this platform — see
# essays/reports.py's own module docstring for the honest, disclosed
# reasoning); these event types and the status computation that reads
# them are real and fully tested today via directly-recorded test events,
# ready for a future webhook to start writing to without any further
# schema change.
SUBMISSION_EVENT_EMAIL_BOUNCED   = "EMAIL_BOUNCED"
SUBMISSION_EVENT_EMAIL_COMPLAINT = "EMAIL_COMPLAINT"
SUBMISSION_EVENT_TYPE_CHOICES = [
    (SUBMISSION_EVENT_STATUS_CHANGE,   "Status change"),
    (SUBMISSION_EVENT_DLQ_RECORDED,    "DLQ recorded"),
    (SUBMISSION_EVENT_ADMIN_RETRIGGER, "Admin retrigger"),
    (SUBMISSION_EVENT_ADMIN_OVERRIDE,  "Admin override"),
    (SUBMISSION_EVENT_EMAIL_BOUNCED,   "Email bounced"),
    (SUBMISSION_EVENT_EMAIL_COMPLAINT, "Email complaint"),
]


class EssaySubmissionEvent(models.Model):
    """Phase 6, Task 6.1 — the "full audit-log/event trail in chronological
    order (every status transition, worker id, error detail)" the admin
    Submissions Module's detail view requires. Did not exist before this
    phase: Phase 5's own pipeline never needed a materialized event
    history to function correctly (EssaySubmission.status/updated_at was
    always sufficient for the pipeline's own logic), so this is genuinely
    new, task-driven infrastructure, not something retrofitted onto an
    existing mechanism.

    Written from exactly two choke points, both in essays/tasks.py, so
    every existing call site gets audit-logged automatically without
    having to touch each one individually:
      1. _transition_submission_status() — one row per status change that
         ACTUALLY took effect (the function's own conditional UPDATE
         returns 0 for a no-op CAS miss, e.g. a redundant retry finding
         the row already past that state; skipped rather than logged, or
         the same submission would show duplicate/misleading transitions
         for something that never actually happened).
      2. _record_dlq() — one row per DLQ write, carrying the real error
         string, satisfying this task's own "error detail" requirement.

    Phase 7, Task 7.1 adds a third and fourth writer, both admin-initiated
    (essays/views.py): AdminSubmissionRetriggerView and
    AdminSubmissionScoreOverrideView, which also populate `admin_user_id`
    and `reason` — the "which admin did it and why" requirement those two
    actions specifically call for, that the two automatic pipeline writers
    above have no need for (nothing to attribute a Celery task run to).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(
        EssaySubmission, on_delete=models.PROTECT, related_name="events",
        # Task 16.1 — redundant with this Meta's own idx_ese_submission_time
        # below (submission is that composite's leftmost column).
        db_index=False,
    )
    # Task 16.1 — no standalone db_index: Phase 13's own notifications.py
    # query (event_type__in=[...], occurred_at__gte=window_start, cross-
    # submission — the one real place this field is ever filtered without
    # also filtering submission) is served by this Meta's own new
    # idx_ese_type_time composite below (event_type is its leftmost
    # column), found missing an adequate index by this same audit round —
    # the previous standalone index only helped the equality filter, not
    # the occurred_at range/ordering that query also needs.
    event_type = models.CharField(max_length=20, choices=SUBMISSION_EVENT_TYPE_CHOICES)
    detail = models.TextField(blank=True, default="")
    # Celery's own current_task.request.hostname/id, captured opportunistically
    # (essays/tasks.py's own helper) — blank when logged outside a real task
    # context (there is no such call site today, but nothing here assumes one).
    worker_hostname = models.CharField(max_length=255, blank=True, default="")
    task_id = models.CharField(max_length=255, blank=True, default="")
    # Phase 7 — set only by the two admin-initiated writers above; blank/
    # null for the two automatic pipeline writers, which have no admin to
    # attribute to. The JWT user_id claim, matching this service's own
    # no-cross-service-FK convention (EssayPaper.created_by etc.).
    admin_user_id = models.UUIDField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "essay_submission_events"
        ordering = ["occurred_at"]
        indexes = [
            models.Index(fields=["submission", "occurred_at"], name="idx_ese_submission_time"),
            # Task 16.1 — Phase 13's own compute_pipeline_health_summary()
            # (essays/notifications.py) filters event_type__in=[...] +
            # occurred_at__gte=window_start across ALL submissions, not
            # scoped to one — the composite above doesn't help it at all
            # (submission isn't filtered), found missing by this audit.
            models.Index(fields=["event_type", "occurred_at"], name="idx_ese_type_time"),
        ]

    def __str__(self):
        return f"{self.event_type} @ {self.occurred_at} (submission {self.submission_id})"


class EssayFailedJob(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Task 16.1 — no standalone db_index: this Meta's own
    # idx_efj_task_resolved already covers task_name-only lookups via its
    # leftmost column (the _record_dlq() dedup check's own query shape).
    task_name  = models.CharField(max_length=255)
    task_id    = models.CharField(max_length=255, blank=True, default="")
    args       = models.JSONField(default=list, blank=True)
    kwargs     = models.JSONField(default=dict, blank=True)
    error      = models.TextField()
    traceback  = models.TextField(blank=True, default="")
    attempts   = models.PositiveSmallIntegerField(default=0)
    # How many times the automatic DLQ sweeper (tasks.py::sweep_dlq_entries)
    # has re-dispatched this entry — checked against DLQ_RETRY_CEILING.
    dlq_retry_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    # Set once a human, or the automatic sweeper (circuit-broken past the
    # ceiling, or self-healed via a successful automatic retry),
    # resolves this entry.
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "essay_failed_jobs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task_name", "resolved_at"], name="idx_efj_task_resolved"),
            # Task 16.1 — sweep_dlq_entries' own primary hot-path query
            # (essays/tasks.py) filters resolved_at__isnull=True +
            # created_at__lte=threshold, ordered by created_at — task_name
            # is never filtered there at all, so the composite above
            # (leftmost task_name) doesn't help it; found missing by this
            # audit. Matches idx_ea_att_status_ends_at's own identical
            # shape (unresolved/pending state + time column, sweep query).
            models.Index(fields=["resolved_at", "created_at"], name="idx_efj_resolved_created"),
        ]

    def __str__(self):
        status = "resolved" if self.resolved_at else "UNRESOLVED"
        return f"{self.task_name} failed ({status}, {self.attempts} attempt(s)) — {self.id}"
