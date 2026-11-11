"""
tasks.py — Celery beat sweeps (Task 4.1), the LLM evaluation pipeline
(Task 5.2) + its dead-letter queue (Task 5.3), and the text-similarity
check (Task 5.4).

Every Celery task in this service lives in this one file, not scattered
across topic modules — a real, live bug found during this phase's own
verification pass, not a style preference: `core/celery.py`'s
`app.autodiscover_tasks()` only auto-imports each installed app's
`tasks.py` by Celery's own convention. `check_text_similarity` was
originally written in its own `plagiarism.py` module and was silently
NEVER REGISTERED with the worker at all — confirmed live, the real
essay-worker logged "Received unregistered task of type
'essays.plagiarism.check_text_similarity'" and discarded every dispatch.
Moved here to actually work, not just to tidy up.

sweep_expired_assignments / sweep_expired_attempts — unchanged in shape
from Task 4.1, now on `base=DeadLetteringTask` per Task 5.3's own promise
("Task 5.3 extends them in place with DLQ recording once EssayFailedJob
exists") — their single catch-all `except Exception: self.retry()` shape
was always a correct fit for `DeadLetteringTask`'s simple "every failure
after retries exhausted looks the same" hook.

evaluate_essay deliberately does NOT use `base=DeadLetteringTask` — ADR
003 Decision 6 requires genuinely different handling per failure type on
this one task (a transient/malformed error shares a 3-retry budget before
DLQ; a definitive permanent error skips straight to DLQ with zero
retries; a quota-exhaustion wait is not a failure at all and must never
count toward either ceiling or ever land in DLQ). Celery's own
`max_retries` is a single number that can't express two different
ceilings on the same task, so this task sets `max_retries=None` (Celery:
unlimited) and enforces the real 3-retry ceiling itself, writing to
EssayFailedJob directly and explicitly per branch — the same DLQ *model*
Task 5.3 promised to reuse, dispatched CLAP's way (verified: CLAP's own
`_record_dlq()` is called manually per except-branch, not via a
Task.on_failure() hook — assessment-service's `DeadLetteringTask` is a
different, simpler design that only fits a task with one uniform failure
mode, which this one isn't).

The 3-retry ceiling is tracked via an explicit `inline_retry_count`
keyword argument threaded through this task's own retry args/kwargs —
NOT Celery's own `self.request.retries`. A real bug, found and fixed
during this phase's own audit: `self.request.retries` increments
identically on EVERY `self.retry()` call regardless of cause (verified
directly in Celery's source — `Task.retry()` computes
`retries = request.retries + 1` unconditionally). Using it as the inline
budget meant a submission that had already waited out a few quota-
exhaustion cycles (which must never count against this budget — Decision
9) would see its very next genuine transient error DLQ'd immediately,
having appeared to already exhaust a budget it never actually touched.
`inline_retry_count` fixes this by only ever being incremented on the
`_retry_or_dlq()` path itself; the quota-wait branches call `self.retry()`
with no args/kwargs override, which makes Celery reuse this invocation's
own original arguments unchanged — the counter simply doesn't move.
"""

import logging

from celery import Task, shared_task
from django.db import connection
from django.utils import timezone

from core.logging_utils import bind_request_id, get_request_id
from core.cache_utils import safe_cache_delete
from core.celery_utils import safe_task_dispatch

logger = logging.getLogger("essays.sweep")
llm_logger = logging.getLogger("essays.llm")


def _jittered(seconds):
    """Adds up to 30% random extra delay on top of a base backoff.

    Real gap found via a live capacity audit (LIVETRACKER3_V1.md, Phase
    18): every retry countdown in this file used a fixed, deterministic
    formula with zero randomness. That's harmless at low volume, but at
    exam-day scale (e.g. 2,000 students submitting within the same
    second) it's a real "thundering herd" risk — every submission that
    hits a transient failure (or the LLM quota's own per-minute
    rate-limit wait) around the same moment retries at the exact same
    future moment too, re-synchronizing into repeated load spikes
    instead of spreading out. Used only where retries can genuinely be
    dispatched in a large simultaneous batch (evaluate_essay's own two
    retry paths, check_text_similarity — both fired for every submission
    in the same exam-submission spike); the periodic beat sweeps
    (sweep_expired_assignments etc.) dispatch one task at a time on a
    schedule, never thousands together, so they were never at risk of
    this and are deliberately left on their existing fixed schedule."""
    import random
    return seconds + random.uniform(0, seconds * 0.3)


_RETRY_BACKOFF_SECONDS = 10
_MAX_RETRIES = 3

# ADR 003 Decision 6/9: 1 initial + 3 inline retries = 4 total attempts
# before DLQ, then up to 5 additional automatic sweeper retries (below) =
# 9 calls maximum before an entry is circuit-broken.
_EVAL_MAX_INLINE_RETRIES = 3
_EVAL_RETRY_BACKOFF_SECONDS = 10

# DLQ sweeper (Task 5.3 / ADR 003 Decision 6, ported from CLAP's
# dlq_sweeper/retry_dlq_entry — verified by direct code reading).
DLQ_GRACE_PERIOD_MINUTES = 5
DLQ_RETRY_CEILING = 5
_DLQ_ADVISORY_LOCK_KEY = 842001

# Task names (Celery's own dotted default) whose first positional arg is a
# submission id — used by DeadLetteringTask.on_failure() below to decide
# whether a permanent failure also belongs on that submission's own
# EssaySubmissionEvent audit trail. evaluate_essay is NOT listed here even
# though it IS submission-scoped: it uses the separate, manual
# _record_dlq() path (this module's own header comment explains why), not
# DeadLetteringTask, so it already logs its own event there instead.
# send_essay_report_email (Phase 13's own reference precedent for its own
# direct-SMTP mechanism) has the identical shape to generate_essay_report
# — submission-scoped, DeadLetteringTask-based — and had the exact same
# invisibility gap this comment already documents once below; found
# during Phase 13's audit, fixed the same way.
_SUBMISSION_SCOPED_TASK_NAMES = frozenset({
    "essays.tasks.generate_essay_report", "essays.tasks.send_essay_report_email",
})


class DeadLetteringTask(Task):
    """Ported from assessment-service's own DeadLetteringTask
    (assessments/tasks.py) — verbatim shape, renamed to write
    EssayFailedJob instead of FailedJob. Celery calls on_failure() exactly
    once a task gives up for good (max_retries exhausted, or an exception
    escapes without ever calling self.retry()). Used by the two sweep
    tasks below (neither submission-scoped — see the DLQ-visibility note
    on `_SUBMISSION_SCOPED_TASK_NAMES` for why that matters) and, since
    Phase 11, by `generate_essay_report` (which IS submission-scoped) —
    NOT by evaluate_essay, see this module's own docstring for why."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        from .models import EssayFailedJob
        try:
            EssayFailedJob.objects.create(
                task_name=self.name,
                task_id=task_id or "",
                args=list(args or []),
                kwargs=dict(kwargs or {}),
                error=str(exc),
                traceback=str(einfo) if einfo else "",
                attempts=self.request.retries,
            )
            logger.error("%s permanently failed after %d attempt(s) — recorded in EssayFailedJob DLQ.", self.name, self.request.retries)
        except Exception:
            logger.exception("%s permanently failed AND could not be recorded in the EssayFailedJob DLQ.", self.name)

        # Phase 11 gap found by this phase's own final-audit round:
        # evaluate_essay's own DLQ writes go through _record_dlq() (below),
        # which explicitly also logs a SUBMISSION_EVENT_DLQ_RECORDED event
        # so a permanently-stuck evaluation shows up in that submission's
        # own audit trail (Task 6.1's "full audit-log/event trail"
        # promise). generate_essay_report is ALSO tied to one specific
        # submission (its own args[0]) but reaches this DIFFERENT
        # on_failure() path (base=DeadLetteringTask, not a manual
        # _record_dlq() call — see this module's own header comment for
        # why that's the right mechanism for this task) — which never
        # logged that same event, so a permanently-stuck report generation
        # was invisible on the submission's own event trail even though a
        # real EssayFailedJob entry existed for it. Fixed here, not by
        # switching generate_essay_report to the manual pattern (that
        # would lose the simpler, correct-for-this-task DeadLetteringTask
        # mechanism for no benefit) — gated by task name so the two
        # sweep tasks above (not submission-scoped; their own `args` isn't
        # a submission id at all) are unaffected.
        if self.name in _SUBMISSION_SCOPED_TASK_NAMES and args:
            from .models import SUBMISSION_EVENT_DLQ_RECORDED
            _log_submission_event(args[0], SUBMISSION_EVENT_DLQ_RECORDED, str(exc))

        super().on_failure(exc, task_id, args, kwargs, einfo)


def _current_worker_context():
    """Celery's own `current_task` proxy — populated automatically inside
    a real task execution (worker or eager test), empty outside one. Used
    to opportunistically capture "worker id" for Phase 6's own
    EssaySubmissionEvent audit trail (Task 6.1) without threading a new
    parameter through every one of this file's existing call sites."""
    from celery import current_task
    request = getattr(current_task, "request", None) if current_task is not None else None
    if request is None:
        return "", ""
    return request.hostname or "", request.id or ""


def _log_submission_event(submission_id, event_type: str, detail: str):
    """Phase 6, Task 6.1's own audit-trail requirement — see
    EssaySubmissionEvent's own docstring (essays/models.py) for why this
    exists and the two choke points (this function's own two callers)
    that cover every status change/DLQ write without touching each
    individual call site. Best-effort and self-contained: a failure here
    must never break the pipeline write it's merely recording."""
    from .models import EssaySubmissionEvent
    hostname, task_id = _current_worker_context()
    try:
        EssaySubmissionEvent.objects.create(
            submission_id=submission_id, event_type=event_type, detail=detail,
            worker_hostname=hostname, task_id=task_id,
        )
    except Exception:
        llm_logger.exception(
            "Failed to record EssaySubmissionEvent for submission %s (%s) — pipeline write itself is unaffected.",
            submission_id, event_type,
        )


def _record_dlq(task_name: str, args: list, kwargs: dict, error: Exception, attempts: int):
    """The manual, CLAP-style DLQ write evaluate_essay's own branches use
    directly, writing to the same EssayFailedJob table DeadLetteringTask
    writes to above — same DLQ mechanism, different dispatch path, per
    this module's own docstring.

    Real bug found and fixed by this task's own live verification (a
    genuine 2-cycle wait for the real automatic sweeper against the real
    worker, not a mocked shortcut): sweep_dlq_entries dispatches a fresh
    evaluate_essay.delay() for a retried entry, which is a brand-new
    Celery invocation with its own self.request.retries=0. If it fails
    again (e.g. OPENAI_API_KEYS is still unset), the old blind `create()`
    here produced a SECOND, independent EssayFailedJob row for the same
    submission — and since that new row also starts unresolved with
    dlq_retry_count=0, it becomes its OWN separately-swept entry, so a
    single submission's ongoing failure grows an unbounded pile of rows,
    each independently eligible for the sweeper's own retry and circuit
    breaker instead of one evolving lineage. Fixed: reuse the existing
    unresolved entry for the same (task_name, args) if one exists, update
    it in place, rather than creating a duplicate."""
    from .models import EssayFailedJob
    try:
        existing = EssayFailedJob.objects.filter(
            task_name=task_name, args=list(args or []), resolved_at__isnull=True,
        ).first()
        if existing is not None:
            existing.error = str(error)
            existing.attempts = attempts
            existing.save(update_fields=["error", "attempts"])
        else:
            EssayFailedJob.objects.create(
                task_name=task_name, task_id="", args=list(args or []), kwargs=dict(kwargs or {}),
                error=str(error), traceback="", attempts=attempts,
            )
    except Exception:
        llm_logger.exception("%s: permanently failed AND could not be recorded in the EssayFailedJob DLQ.", task_name)

    # Phase 6, Task 6.1: only evaluate_essay's own DLQ writes are tied to a
    # real submission_id (args[0]) — sweep_expired_assignments/attempts and
    # check_text_similarity's own DLQ entries (via DeadLetteringTask.
    # on_failure, not this function) concern an assignment/attempt sweep,
    # not one submission, so there's no submission to attach an event to.
    from .models import SUBMISSION_EVENT_DLQ_RECORDED
    if task_name == "evaluate_essay" and args:
        _log_submission_event(args[0], SUBMISSION_EVENT_DLQ_RECORDED, str(error))


@shared_task(bind=True, base=DeadLetteringTask, max_retries=_MAX_RETRIES, default_retry_delay=_RETRY_BACKOFF_SECONDS)
def sweep_expired_assignments(self):
    from .models import EssayAssignment, ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_CLOSED

    with bind_request_id(self.request.id):
        try:
            # Real gap found by Phase 10's own third final-audit round:
            # this is the AUTOMATIC, time-based path an exam most
            # commonly actually ends through (its own time simply running
            # out) — likely the majority case, not the exception, against
            # the two admin-initiated Start/Close gaps that same phase's
            # second audit round already found and fixed. Yet this sweep
            # had zero dashboard-cache invalidation of its own: a
            # dashboard cached while an assignment was still LIVE would
            # keep claiming so, with a ticking-then-clamped-to-zero
            # countdown, for up to the full 300s TTL after the exam had
            # genuinely already ended by running out the clock — the
            # single most common way this staleness could actually
            # manifest in practice.
            #
            # Selecting candidate ids first, then still doing the exact
            # same conditional UPDATE ... WHERE status='LIVE' the
            # original single-statement version used (this comment's own
            # race-safety property is unchanged — a concurrent admin
            # close/ still just makes that one row match 0 rows here) —
            # the extra SELECT exists only so the affected assignment ids
            # are known for invalidation, not to weaken the race guard.
            candidate_ids = list(
                EssayAssignment.objects.filter(
                    status=ASSIGNMENT_STATUS_LIVE, global_expire_time__lte=timezone.now(),
                ).values_list("id", flat=True)
            )
            closed = 0
            if candidate_ids:
                closed = EssayAssignment.objects.filter(
                    id__in=candidate_ids, status=ASSIGNMENT_STATUS_LIVE,
                ).update(status=ASSIGNMENT_STATUS_CLOSED)
                # Invalidate for every candidate, not just however many
                # THIS call's own update() reports — an id a concurrent
                # racer (an admin's own Close click) closed a moment
                # earlier still genuinely transitioned to CLOSED either
                # way, so invalidating its cache here too is correct and
                # harmless, not just whichever caller "won" the race.
                for assignment_id in candidate_ids:
                    safe_cache_delete(f"essay_dashboard:{assignment_id}")
            if closed:
                logger.info("sweep_expired_assignments: closed %d assignment(s).", closed)
            return {"closed": closed}
        except Exception as exc:
            logger.error(
                "sweep_expired_assignments failed (attempt %d/%d): %s",
                self.request.retries + 1, _MAX_RETRIES, exc,
            )
            raise self.retry(exc=exc, countdown=_RETRY_BACKOFF_SECONDS * (self.request.retries + 1))


@shared_task(bind=True, base=DeadLetteringTask, max_retries=_MAX_RETRIES, default_retry_delay=_RETRY_BACKOFF_SECONDS)
def sweep_expired_attempts(self):
    from .models import EssayAttempt, ATTEMPT_STATUS_AUTO_SUBMITTED
    from .scoring import finalize_attempts

    with bind_request_id(self.request.id):
        try:
            expired = EssayAttempt.objects.filter(ends_at__lte=timezone.now())
            auto_submitted = finalize_attempts(expired, ATTEMPT_STATUS_AUTO_SUBMITTED)
            if auto_submitted:
                logger.info("sweep_expired_attempts: auto-submitted %d attempt(s).", auto_submitted)
            return {"auto_submitted": auto_submitted}
        except Exception as exc:
            logger.error(
                "sweep_expired_attempts failed (attempt %d/%d): %s",
                self.request.retries + 1, _MAX_RETRIES, exc,
            )
            raise self.retry(exc=exc, countdown=_RETRY_BACKOFF_SECONDS * (self.request.retries + 1))


def _transition_submission_status(submission, new_status, *, expected_status=None):
    """Compare-and-swap style status transition (ADR 003 Decision 6's
    "report-generation transition guard" principle, applied here to the
    evaluation step itself) — a conditional UPDATE, never an unconditional
    write, so a retried/duplicate task run can't clobber a status a
    different, later run already advanced past.

    Phase 6, Task 6.1: this is the one place every real status change in
    the whole pipeline already flows through, so it's also the one place
    EssaySubmissionEvent (the admin Submissions Module's audit trail) gets
    written — every call site upstream gets audit-logged automatically,
    with no changes needed there. Logged only when `qs.update()` actually
    changed a row (`updated` truthy): a CAS miss (the row was already past
    `expected_status` — e.g. a redundant retry re-attempting a transition
    a different, earlier call already made) is a real, expected no-op, not
    a new transition, and logging one anyway would show a submission's
    audit trail claiming a status change that never actually happened.

    Phase 11, Task 11.1: also the one place `generate_essay_report` gets
    auto-dispatched, the instant a submission genuinely reaches
    LLM_COMPLETE — matching SUBMISSION_STATUS_REPORT_GENERATING's own
    pre-existing comment (essays/models.py) naming this as the report
    pipeline's real trigger. Deliberately NOT used by
    AdminReportRegenerateView (essays/views.py) for its own LLM_COMPLETE
    reset: that view resets status inside a `transaction.atomic()` block
    and must only dispatch after that block actually commits (the exact
    "invalidate/dispatch after commit, not before" lesson Phase 10's own
    audit already found and fixed for the dashboard cache below) — it
    does its own raw conditional UPDATE and dispatches
    `generate_essay_report.delay()` itself once the block exits, the same
    convention AdminSubmissionRetriggerView already established for
    `evaluate_essay`."""
    from .models import EssaySubmission, SUBMISSION_EVENT_STATUS_CHANGE, SUBMISSION_STATUS_LLM_COMPLETE
    qs = EssaySubmission.objects.filter(pk=submission.pk)
    if expected_status is not None:
        qs = qs.filter(status=expected_status)
    updated = qs.update(status=new_status)
    if updated:
        detail = f"{expected_status} -> {new_status}" if expected_status else f"-> {new_status}"
        _log_submission_event(submission.pk, SUBMISSION_EVENT_STATUS_CHANGE, detail)
        # Phase 10, Task 10.1's own dashboard cache — unlike Phase 9's
        # Analytics (a post-hoc deep-dive, correctly left on a plain TTL
        # per that phase's own verified correction), a live-status
        # dashboard genuinely IS the "watched live during an exam" case
        # assessment-service's own explicit-invalidation pattern exists
        # for (see AdminEssayAssignmentDashboardView's own docstring).
        # This is the automatic-pipeline choke point every status change
        # in the whole service already flows through except three
        # deliberately-bypassing admin views (see that same docstring for
        # why those three call this directly too, not through here).
        safe_cache_delete(f"essay_dashboard:{submission.attempt.assignment_id}")
        if new_status == SUBMISSION_STATUS_LLM_COMPLETE:
            # Safe to dispatch here (unlike the regenerate view's own
            # case, see this function's own docstring above): every
            # existing caller of this branch (evaluate_essay's three
            # LLM_COMPLETE call sites) invokes this function as a bare,
            # already-autocommitted statement, never from inside its own
            # transaction.atomic() block.
            #
            # Real gap found auditing every .delay() call site against the
            # same broker-unreachable class of bug already fixed in
            # scoring.py — this one mattered more than most: this function
            # is called from inside evaluate_essay itself, right after the
            # real (costly) LLM grading call already succeeded. An
            # unhandled crash here would propagate into evaluate_essay's
            # own ADR-003 retry/DLQ machinery, which would retry the
            # WHOLE task — including a second, genuinely unnecessary LLM
            # API call — just because this small, unrelated follow-up
            # dispatch failed. Caught locally instead: the grading result
            # already committed and stays committed regardless; the
            # submission is simply left at LLM_COMPLETE with no report,
            # and sweep_undispatched_submissions (essays/tasks.py) now
            # scans for exactly that state and redispatches it.
            safe_task_dispatch(
                generate_essay_report, str(submission.pk),
                context=f"generate_essay_report for submission {submission.pk}",
            )
    return updated


@shared_task(bind=True, max_retries=None, time_limit=90, soft_time_limit=75, acks_late=True, reject_on_worker_lost=True)
def evaluate_essay(self, submission_id, inline_retry_count=0, correlation_id=None):
    # acks_late/reject_on_worker_lost — Task 18.2's own real finding, live-
    # verified, not theorized: without these (Celery's own default is
    # early-ack, task removed from the broker queue the moment it's
    # RECEIVED, not once it completes), a worker killed mid-evaluation
    # loses that task from Celery's own redelivery mechanism entirely.
    # Reproduced live: dispatched a real evaluation, killed essay-worker
    # (SIGKILL) while the task was genuinely in flight, restarted the
    # worker, and the submission sat at LLM_PROCESSING forever — zero DLQ
    # entry (the exception path never fired; the process was just gone),
    # zero automatic recovery, invisible to every existing safety net
    # (the DLQ sweeper only touches EssayFailedJob rows, and none was ever
    # created). Exactly the "permanently-stuck submission" Task 18.2's own
    # testing bar exists to catch. `acks_late=True` makes Celery
    # acknowledge (remove from queue) only after the task function
    # actually returns, so a worker killed mid-task causes real
    # redelivery instead of silent loss; `reject_on_worker_lost=True`
    # ensures the same happens even if the worker process itself
    # vanishes uncleanly rather than the task raising. Safe to add, not
    # just convenient: the CAS transition below already documents itself
    # as "harmless no-op on a retry of this same task (already
    # LLM_PROCESSING from its own prior attempt)" — this resumability was
    # already the intended design, just never actually wired to Celery's
    # own delivery guarantee. The existing "already_scored" idempotency
    # check above absorbs acks_late's own well-known tradeoff (a task
    # redelivered after it already fully completed, if the ack itself was
    # lost) exactly the way it already does for the narrower race that
    # comment describes.
    #
    # time_limit/soft_time_limit — a real gap found by this phase's own
    # second final-audit round: ported from CLAP's own evaluate_writing
    # (verified: time_limit=200, soft_time_limit=175 there) but never
    # actually carried over here. Without it, a hung OpenAI call or a
    # hung Redis connection during quota checking could block a worker
    # slot indefinitely — the OpenAI SDK's own timeout=45.0 only bounds
    # the network call itself, not the whole task. 90/75s gives headroom
    # for that 45s call plus PII redaction/DB work either side of it,
    # scaled down from CLAP's own budget since this task does
    # meaningfully less per invocation (one domain, no rule-based stage).
    #
    # Task 17.2 — `correlation_id`: unlike the periodic sweep tasks
    # elsewhere in this file (which correctly use their own Celery
    # task_id as their correlation id, matching assessment-service's own
    # precedent — there's no originating HTTP request to recover), this
    # task is dispatched directly from a real request (student submit,
    # admin retrigger) or from the DLQ sweep's own retry pass. Every real
    # call site threads `get_request_id()` through as `correlation_id` so
    # this task's log lines carry the SAME id as the nginx access log line
    # and essay-service HTTP log lines for that request — falls back to
    # this task's own Celery id only if none was passed (defensive; every
    # real call site always passes one). `bind_request_id` now wraps the
    # WHOLE function, not just _evaluate_essay_impl's own body, so the
    # SoftTimeLimitExceeded except-clause's own log line below carries it
    # too — it used to fall outside the (narrower) binding and log with no
    # correlation id at all, a real gap found by this same audit.
    with bind_request_id(correlation_id or self.request.id):
        from celery.exceptions import SoftTimeLimitExceeded
        try:
            return _evaluate_essay_impl(self, submission_id, inline_retry_count, correlation_id)
        except SoftTimeLimitExceeded:
            llm_logger.error("evaluate_essay: soft time limit exceeded for submission %s.", submission_id)
            _record_dlq("evaluate_essay", [submission_id], {}, RuntimeError("SoftTimeLimitExceeded"), inline_retry_count)
            from .models import EssaySubmission, SUBMISSION_STATUS_LLM_FAILED
            try:
                submission = EssaySubmission.objects.get(pk=submission_id)
                _transition_submission_status(submission, SUBMISSION_STATUS_LLM_FAILED)
            except EssaySubmission.DoesNotExist:
                pass
            raise


def _evaluate_essay_impl(self, submission_id, inline_retry_count, correlation_id=None):
    from .llm_client import (
        call_openai_evaluate, LLMTransientError, LLMMalformedResponseError, LLMPermanentError,
    )
    from .models import (
        EssaySubmission, EssayScore, EssayLLMTrace,
        SUBMISSION_STATUS_PENDING, SUBMISSION_STATUS_LLM_PROCESSING,
        SUBMISSION_STATUS_LLM_COMPLETE, SUBMISSION_STATUS_LLM_FAILED,
    )
    from .pii_redaction import redact_pii
    from .prompts import build_evaluation_messages
    from .quota_tracker import QuotaDailyExhaustedException, QuotaTemporarilyUnavailableException
    from .semantic_guard import is_semantically_consistent

    # Re-binds to the same id the caller (evaluate_essay, above) already
    # bound — a harmless no-op that keeps this block's own indentation
    # rather than reworking every line below it.
    with bind_request_id(get_request_id()):
        try:
            submission = EssaySubmission.objects.select_related("attempt__set__question").get(pk=submission_id)
        except EssaySubmission.DoesNotExist:
            llm_logger.error("evaluate_essay: submission %s not found — skipping.", submission_id)
            return {"status": "skipped", "reason": "submission_not_found"}

        # Idempotency (ADR 003 Decision 10): never re-score an already-scored
        # submission. Also self-healing (a narrow but real gap found by this
        # phase's own final audit): EssayScore creation and the status
        # transition to LLM_COMPLETE below are two separate writes, not one
        # atomic step, and this task has no `acks_late=True` — a worker
        # crash landing exactly between them would leave a real score
        # sitting on a submission stuck at LLM_PROCESSING forever, with no
        # DLQ entry for the sweeper to ever find (the failure never reached
        # an except branch). Repairing the status here, on the very next
        # time anything re-touches this submission, closes that window
        # without needing a new mechanism — the same "check and repair
        # opportunistically" pattern already used for orphaned submissions
        # in scoring.py.
        if EssayScore.objects.filter(submission=submission).exists():
            _transition_submission_status(submission, SUBMISSION_STATUS_LLM_COMPLETE)
            return {"status": "skipped", "reason": "already_scored"}

        response_text = submission.attempt.draft_response or ""

        # No-submission guard (Decision 6) — never calls the LLM at all.
        if not response_text.strip():
            EssayScore.objects.get_or_create(
                submission=submission,
                defaults={
                    "score": 0,
                    "feedback": {"overall": "No submission received — zero score awarded.", "breakdown": {}},
                    "is_no_submission": True,
                },
            )
            _transition_submission_status(submission, SUBMISSION_STATUS_LLM_COMPLETE)
            llm_logger.info("evaluate_essay: no-submission guard, submission %s scored 0.", submission_id)
            return {"status": "ok", "skipped": True, "reason": "no_submission"}

        question = getattr(submission.attempt.set, "question", None)
        if question is None:
            # Defensive only — Task 3.2's readiness gate should make this
            # unreachable in practice.
            _record_dlq("evaluate_essay", [submission_id], {}, RuntimeError("attempt's set has no question"), inline_retry_count)
            _transition_submission_status(submission, SUBMISSION_STATUS_LLM_FAILED)
            return {"status": "failed", "reason": "no_question"}

        # Compare-and-swap: only PENDING -> LLM_PROCESSING. Harmless no-op
        # on a retry of this same task (already LLM_PROCESSING from its
        # own prior attempt).
        _transition_submission_status(submission, SUBMISSION_STATUS_LLM_PROCESSING, expected_status=SUBMISSION_STATUS_PENDING)

        redacted_text, _redaction_count = redact_pii(response_text)
        messages = build_evaluation_messages(question.llm_rubric_prompt, question.question_text, redacted_text)

        try:
            result = call_openai_evaluate(messages)
        except LLMTransientError as exc:
            return _retry_or_dlq(self, submission, "evaluate_essay", submission_id, inline_retry_count, exc, correlation_id)
        except LLMMalformedResponseError as exc:
            return _retry_or_dlq(self, submission, "evaluate_essay", submission_id, inline_retry_count, exc, correlation_id)
        except QuotaDailyExhaustedException as exc:
            # Not a failure — never DLQ'd, never counted against the
            # inline-retry ceiling (ADR 003 Decision 9). Deliberately
            # calls self.retry() with NO args/kwargs override: Celery then
            # re-uses this invocation's own original args, so
            # inline_retry_count passes through completely unchanged — a
            # quota wait must never eat into the separate 3-attempt inline
            # budget below, no matter how many times it happens (a real,
            # once-found-and-fixed bug: both used to share Celery's own
            # single `self.request.retries` counter, which increments
            # identically for every retry() call regardless of cause, so a
            # submission that waited out a few quota cycles would have its
            # very next genuine transient error DLQ'd immediately instead
            # of getting its own fresh 3 tries).
            countdown = _jittered(exc.wait_seconds)
            llm_logger.warning("evaluate_essay: daily quota exhausted, retrying in %.1fs.", countdown)
            raise self.retry(exc=exc, countdown=countdown)
        except QuotaTemporarilyUnavailableException as exc:
            # Jittered (Phase 18 finding): this is the dominant retry path
            # at real exam-day scale, not the rarer transient-error one
            # below — wait_seconds comes from a shared per-minute Redis
            # TTL, so many submissions hitting the rate limit around the
            # same moment would otherwise all retry at the same future
            # moment too.
            countdown = _jittered(exc.wait_seconds)
            llm_logger.warning("evaluate_essay: quota temporarily unavailable, retrying in %.1fs.", countdown)
            raise self.retry(exc=exc, countdown=countdown)
        except LLMPermanentError as exc:
            # Definitive provider error — DLQ immediately, no retry at all.
            llm_logger.error("evaluate_essay: permanent LLM error for submission %s: %s", submission_id, exc)
            _record_dlq("evaluate_essay", [submission_id], {}, exc, inline_retry_count)
            _transition_submission_status(submission, SUBMISSION_STATUS_LLM_FAILED)
            return {"status": "failed", "reason": "permanent_llm_error"}

        # ── Validate shape + semantic guard — both share the same
        # "malformed" retry-then-DLQ bucket (Decision 6). ──────────────────
        # Phase 7, Task 7.1: `result` is now an LLMEvaluationResult, not a
        # bare dict — `.parsed` is exactly the dict this code always
        # worked with before that phase's trace-view requirement.
        parsed = result.parsed
        score = parsed.get("score") if isinstance(parsed, dict) else None
        feedback = parsed.get("feedback") if isinstance(parsed, dict) else None
        valid_shape = (
            isinstance(score, (int, float)) and 0 <= score <= 10
            and isinstance(feedback, dict) and isinstance(feedback.get("overall"), str)
        )
        if not valid_shape:
            return _retry_or_dlq(
                self, submission, "evaluate_essay", submission_id, inline_retry_count,
                LLMMalformedResponseError(f"Unexpected response shape: {parsed!r}"), correlation_id,
            )
        if not is_semantically_consistent(int(round(score)), feedback["overall"]):
            return _retry_or_dlq(
                self, submission, "evaluate_essay", submission_id, inline_retry_count,
                LLMMalformedResponseError("Semantic-consistency guard rejected the response."), correlation_id,
            )

        EssayScore.objects.get_or_create(
            submission=submission,
            defaults={"score": int(round(score)), "feedback": feedback, "is_no_submission": False},
        )
        # Phase 7, Task 7.1's own trace/debug view — best-effort, never
        # allowed to fail the actual scoring it's merely recording
        # alongside: a genuinely scored submission must never end up
        # DLQ'd just because the audit trace itself couldn't be written.
        try:
            EssayLLMTrace.objects.get_or_create(
                submission=submission,
                defaults={
                    "prompt_messages": messages, "raw_response": result.raw_response,
                    "request_id": result.request_id, "model_used": result.model,
                },
            )
        except Exception:
            llm_logger.exception("evaluate_essay: failed to record LLM trace for submission %s.", submission_id)
        _transition_submission_status(submission, SUBMISSION_STATUS_LLM_COMPLETE)
        llm_logger.info("evaluate_essay: submission %s scored %s/10.", submission_id, int(round(score)))
        return {"status": "ok", "submission_id": submission_id, "score": int(round(score))}


def _retry_or_dlq(self, submission, task_name, submission_id, inline_retry_count, exc, correlation_id=None):
    """Shared branch for the transient/malformed bucket: retry within the
    3-attempt ceiling, else DLQ and mark LLM_FAILED.

    Uses `inline_retry_count` — an explicit value threaded through this
    task's own args/kwargs — NOT `self.request.retries` (Celery's own
    counter, which also increments on every quota-wait retry above; a real
    bug, already found and fixed, from originally using that shared
    counter here — see evaluate_essay's own quota-exception comments).

    `correlation_id` (Task 17.2) is threaded the same way so the SAME
    nginx/HTTP correlation id survives every inline retry of this same
    evaluation, not just the first attempt."""
    from .models import SUBMISSION_STATUS_LLM_FAILED
    if inline_retry_count < _EVAL_MAX_INLINE_RETRIES:
        llm_logger.warning(
            "evaluate_essay: retryable error (attempt %d/%d): %s",
            inline_retry_count + 1, _EVAL_MAX_INLINE_RETRIES + 1, exc,
        )
        # Task 17.1 — real bug found via live LLM-outage verification (not a
        # mock/unit test): passing only `kwargs=` here left Celery's retry()
        # reuse the ORIGINAL request's `args` too (every real call site
        # dispatches positionally — evaluate_essay.delay(submission_id)),
        # so the retried invocation received submission_id BOTH positionally
        # (from the reused original args) AND as this kwarg — a
        # `TypeError: evaluate_essay() got multiple values for argument
        # 'submission_id'` that fired before the task body ever ran, so no
        # except-clause here could ever catch it. That silently broke the
        # entire 3-inline-retry mechanism this function exists to provide:
        # the very first transient error on ANY submission would crash the
        # retry outright, leaving it stuck at LLM_PROCESSING forever with
        # no DLQ entry (since _record_dlq is never reached) and no operator
        # visibility. Fixed by passing `args=()` explicitly so only this
        # call's own kwargs are used, never the stale positional ones.
        # Jittered (Phase 18 finding) — dispatched for every submission in
        # an exam-day spike, so a fixed schedule would let many
        # simultaneous transient failures retry in sync, re-forming the
        # same load spike instead of spreading out.
        raise self.retry(
            exc=exc, countdown=_jittered(_EVAL_RETRY_BACKOFF_SECONDS * (inline_retry_count + 1)),
            args=(), kwargs={
                "submission_id": submission_id, "inline_retry_count": inline_retry_count + 1,
                "correlation_id": correlation_id,
            },
        )
    llm_logger.error("evaluate_essay: retry ceiling reached, DLQ: %s", exc)
    _record_dlq(task_name, [submission_id], {}, exc, inline_retry_count)
    _transition_submission_status(submission, SUBMISSION_STATUS_LLM_FAILED)
    return {"status": "failed", "reason": "retry_ceiling_exceeded"}


# ── Report Generation & Delivery (Phase 11) ─────────────────────────────────
# Reference (verified — actually read, not inferred): CLAP's
# report_management.py + email_management.py. See essays/reports.py's own
# module docstring for the full reasoning behind every deviation from
# CLAP's own approach (HTML-not-PDF storage, direct SMTP instead of
# notification-service, deferred bounce/complaint webhook, skipped
# branding). `generate_essay_report` uses `base=DeadLetteringTask` (like
# the two sweep tasks above, not evaluate_essay's own manual-DLQ shape):
# rendering a report from already-local DB data has exactly one uniform
# failure mode (a bug in reports.py, or a DB hiccup), unlike
# evaluate_essay's genuinely branching LLM failure taxonomy — the simpler
# mechanism is the correct fit here, not a copy-paste of the more complex
# one "to be consistent".

@shared_task(bind=True, base=DeadLetteringTask, max_retries=_MAX_RETRIES, default_retry_delay=_RETRY_BACKOFF_SECONDS)
def generate_essay_report(self, submission_id):
    """Dispatched automatically from `_transition_submission_status()` the
    instant a submission reaches LLM_COMPLETE, and re-dispatched by
    `AdminReportRegenerateView` (essays/views.py) after it resets a
    submission back to LLM_COMPLETE.

    CAS-guarded exactly like `evaluate_essay`'s own PENDING->LLM_PROCESSING
    guard: only ever proceeds LLM_COMPLETE -> REPORT_GENERATING. This is
    the exact guard CLAP's own history warns about (see
    SUBMISSION_STATUS_REPORT_GENERATING's own docstring, essays/models.py)
    — a caller that ever set REPORT_GENERATING directly instead of
    resetting to LLM_COMPLETE would make this guard reject the dispatch
    and silently do nothing, reproducing CLAP's own already-documented bug.

    On any rendering failure, rolls back to LLM_COMPLETE via a plain
    `.update()` (not the CAS transaction that claimed REPORT_GENERATING)
    before retrying/DLQ'ing — so a failed render never strands a
    submission in REPORT_GENERATING forever, and each retry attempt
    re-claims the CAS guard fresh rather than assuming it still holds it."""
    from .models import (
        EssaySubmission, SUBMISSION_STATUS_LLM_COMPLETE,
        SUBMISSION_STATUS_REPORT_GENERATING, SUBMISSION_STATUS_REPORT_READY,
    )
    from .reports import render_report_html

    with bind_request_id(self.request.id):
        try:
            submission = EssaySubmission.objects.select_related(
                "attempt__assignment__paper", "attempt__set__question", "score",
            ).get(pk=submission_id)
        except EssaySubmission.DoesNotExist:
            logger.error("generate_essay_report: submission %s not found — skipping.", submission_id)
            return {"status": "skipped", "reason": "submission_not_found"}

        claimed = _transition_submission_status(
            submission, SUBMISSION_STATUS_REPORT_GENERATING, expected_status=SUBMISSION_STATUS_LLM_COMPLETE,
        )
        if not claimed:
            logger.info(
                "generate_essay_report: submission %s not in LLM_COMPLETE (already generating/generated, "
                "or not yet scored) — skipping.", submission_id,
            )
            return {"status": "skipped", "reason": "not_llm_complete"}

        try:
            report_html = render_report_html(submission)
        except Exception as exc:
            logger.exception("generate_essay_report: failed to render report for submission %s.", submission_id)
            EssaySubmission.objects.filter(pk=submission.pk).update(status=SUBMISSION_STATUS_LLM_COMPLETE)
            raise self.retry(exc=exc, countdown=_RETRY_BACKOFF_SECONDS * (self.request.retries + 1))

        EssaySubmission.objects.filter(pk=submission.pk).update(report_html=report_html)
        submission.status = SUBMISSION_STATUS_REPORT_GENERATING
        _transition_submission_status(
            submission, SUBMISSION_STATUS_REPORT_READY, expected_status=SUBMISSION_STATUS_REPORT_GENERATING,
        )
        logger.info("generate_essay_report: report generated for submission %s.", submission_id)
        return {"status": "ok", "submission_id": submission_id}


@shared_task(bind=True, base=DeadLetteringTask, max_retries=_MAX_RETRIES, default_retry_delay=_RETRY_BACKOFF_SECONDS,
             time_limit=60, soft_time_limit=45)
def send_essay_report_email(self, submission_id, student_email):
    """Dispatched only from an explicit admin action — single resend
    (`AdminSubmissionReportResendView`) or bulk resend
    (`AdminAssignmentReportBulkResendView`), essays/views.py — never
    automatically: report GENERATION (Task 11.1) is automatic, report
    DELIVERY is admin-triggered, matching CLAP's own generate/send split
    (report_management.py vs email_management.py) and Task 11.2's own
    wording ("single-submission resend and a capped bulk-resend" — there
    is no separate first-send action; "resend" is the one send verb,
    covering both an initial delivery and a redelivery).

    `student_email` is passed in by the caller, not looked up here:
    core/user_service_client.py authenticates by forwarding the calling
    admin's own JWT (see that module's own docstring) — that doesn't exist
    inside a Celery worker's task context, so the admin-facing view does
    the roster lookup itself, with its own real request, before
    dispatching this task — exactly how every other user-service call in
    this service already works."""
    from django.conf import settings as django_settings
    from django.core.mail import send_mail
    from .models import EssaySubmission

    with bind_request_id(self.request.id):
        try:
            submission = EssaySubmission.objects.select_related("attempt__assignment__paper").get(pk=submission_id)
        except EssaySubmission.DoesNotExist:
            logger.error("send_essay_report_email: submission %s not found — skipping.", submission_id)
            return {"status": "skipped", "reason": "submission_not_found"}

        if not submission.report_html:
            logger.warning("send_essay_report_email: submission %s has no report yet — skipping.", submission_id)
            return {"status": "skipped", "reason": "no_report"}

        paper_title = submission.attempt.assignment.paper.title
        try:
            send_mail(
                subject=f"Your essay report — {paper_title}",
                message="Your essay evaluation report is ready. Please view this email in an HTML-capable client.",
                html_message=submission.report_html,
                # DEFAULT_FROM_EMAIL, not SERVER_EMAIL — this is a real
                # student-facing email, not a mail_admins()-style system
                # alert. See core/settings.py's own comment on both
                # settings for the gap this corrects (found by Phase 11's
                # own final-audit round).
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[student_email],
                fail_silently=False,
            )
        except Exception as exc:
            logger.exception("send_essay_report_email: send failed for submission %s.", submission_id)
            raise self.retry(exc=exc, countdown=_RETRY_BACKOFF_SECONDS * (self.request.retries + 1))

        # Reset, never accumulated — matches EssaySubmission.email_sent_at's
        # own field comment (essays/models.py): always the most recent
        # successful send, so a stale "sent" marker never survives a
        # regenerate that cleared it back to null.
        EssaySubmission.objects.filter(pk=submission.pk).update(email_sent_at=timezone.now())
        logger.info("send_essay_report_email: sent report email for submission %s.", submission_id)
        return {"status": "ok", "submission_id": submission_id}


@shared_task(bind=True, max_retries=0, acks_late=True, reject_on_worker_lost=True, time_limit=60, soft_time_limit=50)
def sweep_dlq_entries(self):
    """Task 5.3 / ADR 003 Decision 6 — the shape (grace period, automatic
    retry, circuit-breaker ceiling, Postgres advisory lock, and the
    time_limit/soft_time_limit pair — a real gap this phase's own second
    final-audit round found missing here too) is ported from CLAP's
    dlq_sweeper/retry_dlq_entry (verified by direct code reading);
    the exact bookkeeping is essay-service's own, simpler design — CLAP
    spreads one failure lineage's history across multiple DeadLetterQueue
    rows with two loosely-related counters, which this service does not
    replicate (a deliberate simplification, not an oversight: ADR 003
    Decision 6 specifies the observable behavior, not CLAP's exact
    row-per-attempt bookkeeping). One evolving EssayFailedJob row per
    original failure, a dedicated dlq_retry_count, and a check for the
    submission having since been scored (self-healed by an earlier
    automatic retry this same sweeper already dispatched) before ever
    re-dispatching it again.

    Scheduled every 5 minutes (core/settings.py's CELERY_BEAT_SCHEDULE) —
    the grace-period filter below is a defensive floor, not the sole
    pacing mechanism; the schedule interval itself is what actually keeps
    automatic retries spaced out, not a tight sweep loop."""
    from .models import EssayFailedJob, EssayScore, EssaySubmission

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s);", [_DLQ_ADVISORY_LOCK_KEY])
        acquired = cursor.fetchone()[0]

    if not acquired:
        return {"status": "skipped", "reason": "advisory_lock_not_acquired"}

    # Task 17.2 — this sweep previously ran with no correlation id bound at
    # all (every other periodic task in this file already does this; this
    # one was missed), so its own "retried/self-healed/circuit-broke"
    # summary log line carried none. Also lets each retried
    # evaluate_essay.delay() below tag its own log lines with THIS sweep
    # run's id, so an on-call engineer can trace "which sweep retried this
    # submission" the same way an HTTP-triggered evaluation traces back to
    # its own originating request.
    with bind_request_id(self.request.id):
        try:
            threshold = timezone.now() - timezone.timedelta(minutes=DLQ_GRACE_PERIOD_MINUTES)
            entries = EssayFailedJob.objects.filter(
                resolved_at__isnull=True, created_at__lte=threshold, dlq_retry_count__lt=DLQ_RETRY_CEILING,
            ).order_by("created_at")[:100]

            retried = 0
            self_healed = 0
            broker_down = False
            # Phase 10's own dashboard cache — real gap found by that phase's
            # own FOURTH final-audit round: both the self-heal branch below
            # and the circuit-breaker bulk-update after this loop RESOLVE
            # EssayFailedJob entries (reducing dlq_backlog_count, a dashboard
            # KPI scoped to task_name="evaluate_essay" entries specifically)
            # with zero invalidation of their own. Collected here, invalidated
            # once after both paths have run.
            affected_submission_ids = set()
            for entry in entries:
                if entry.task_name != "evaluate_essay" or not entry.args:
                    # No dispatch mapping for this task_name — nothing to
                    # automatically retry; leave it unresolved for manual
                    # triage rather than silently marking it resolved.
                    continue

                submission_id = entry.args[0]
                if EssayScore.objects.filter(submission_id=submission_id).exists():
                    # A previous automatic retry (or a manual admin action)
                    # already succeeded since this entry was recorded.
                    entry.resolved_at = timezone.now()
                    entry.save(update_fields=["resolved_at"])
                    self_healed += 1
                    affected_submission_ids.add(submission_id)
                    continue

                # Real gap found auditing every .delay() call site against
                # the same broker-unreachable class of bug already fixed
                # in scoring.py. Two compounding issues if left
                # unprotected: (1) dlq_retry_count was incremented BEFORE
                # the dispatch attempt, so a broker outage would burn part
                # of an entry's own retry budget on an attempt that never
                # even reached the broker, pushing it toward the
                # circuit-breaker ceiling for no real try; (2) an unhandled
                # crash here would abort this whole sweep pass, leaving
                # every remaining entry in `entries` untouched until the
                # next scheduled run. Fixed the same way as scoring.py's
                # own loop: only count it as a retry if dispatch actually
                # succeeded, and once the broker proves unreachable once,
                # stop attempting the rest of this pass — it's one shared
                # condition, not N independent ones, so there's no reason
                # to burn N reconnect-timeout budgets to learn the same
                # fact N times. The remaining entries are untouched (not
                # resolved, not retry-counted) and simply wait for this
                # sweep's own next scheduled pass.
                if broker_down:
                    continue
                if not safe_task_dispatch(
                    evaluate_essay, submission_id, correlation_id=get_request_id(),
                    dispatch_logger=logger, context=f"evaluate_essay DLQ retry for submission {submission_id}",
                ):
                    broker_down = True
                    continue
                entry.dlq_retry_count += 1
                entry.save(update_fields=["dlq_retry_count"])
                retried += 1

            # Circuit breaker: entries at the ceiling (from this pass's
            # increment or a prior one) become a permanent, admin-visible
            # item rather than being retried forever. Submission ids captured
            # BEFORE the bulk update (not re-queried after, since the same
            # filter no longer matches those rows once resolved_at is set).
            broken_qs = EssayFailedJob.objects.filter(resolved_at__isnull=True, dlq_retry_count__gte=DLQ_RETRY_CEILING)
            affected_submission_ids.update(
                e.args[0] for e in broken_qs if e.task_name == "evaluate_essay" and e.args
            )
            circuit_broken = broken_qs.update(resolved_at=timezone.now())

            if affected_submission_ids:
                # Same .distinct()-defeated-by-default-ordering bug found
                # and fixed in scoring.py's own identical cache-invalidation
                # loop (EssaySubmission.Meta.ordering silently breaks
                # .distinct() on Postgres unless order_by() clears it
                # first) — up to 100 entries per DLQ sweep pass could
                # otherwise mean up to 100 redundant cache-delete calls
                # instead of one per genuinely distinct assignment.
                assignment_ids = EssaySubmission.objects.filter(
                    id__in=affected_submission_ids,
                ).order_by().values_list("attempt__assignment_id", flat=True).distinct()
                for assignment_id in assignment_ids:
                    safe_cache_delete(f"essay_dashboard:{assignment_id}")

            if retried or circuit_broken or self_healed:
                logger.info(
                    "sweep_dlq_entries: retried %d, self-healed %d, circuit-broke %d.",
                    retried, self_healed, circuit_broken,
                )
            return {"status": "ok", "retried": retried, "self_healed": self_healed, "circuit_broken": circuit_broken}
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s);", [_DLQ_ADVISORY_LOCK_KEY])


# A submission whose evaluate_essay dispatch itself failed (essays/scoring.py's
# _create_and_dispatch_submissions, real Redis-outage gap found live) has no
# EssayFailedJob row at all — _record_dlq is only ever called from INSIDE
# evaluate_essay's own exception handling, which never got the chance to run
# for these. sweep_dlq_entries above can't find them either (it only looks at
# EssayFailedJob). This is a genuinely different failure mode needing its own
# check: a PENDING submission that's been sitting long enough that it can't
# just be "about to be dispatched normally" (that happens synchronously,
# within milliseconds, in the same request) is one whose dispatch silently
# never happened.
UNDISPATCHED_GRACE_MINUTES = 2


@shared_task(bind=True, max_retries=0, acks_late=True, reject_on_worker_lost=True, time_limit=60, soft_time_limit=50)
def sweep_undispatched_submissions(self):
    """Re-dispatches evaluate_essay for any EssaySubmission stuck at
    PENDING past UNDISPATCHED_GRACE_MINUTES — the self-heal for a Redis
    outage that happened at the exact moment a student's own submit
    request tried to hand their evaluation off to the queue. Deliberately
    NOT scoped to attempts whose own `ends_at` has passed (unlike
    _repair_orphaned_submissions, which the periodic expired-attempts
    sweep already covers) — a student who submits early, well before
    their own time limit, would otherwise wait until their original
    deadline before this ever looked at them, which defeats the point of
    a *prompt* recovery. Runs independently of both existing sweeps for
    exactly this reason.

    No advisory lock, unlike sweep_dlq_entries: a genuine double-dispatch
    race here is already safe by construction — evaluate_essay's own CAS
    (PENDING -> LLM_PROCESSING) makes a second concurrent call a harmless
    no-op past that point, and EssayScore.objects.get_or_create()'s own
    atomicity (Decision 10's idempotency check) is what already protects
    every other path that could double-dispatch this same task. Adding a
    second locking mechanism here would just be redundant, not safer.

    Real gap found auditing this task's own dispatch calls: they were
    unprotected against the exact broker-unreachable failure this task
    exists to recover from — if the broker was still down (or went back
    down) at the moment this sweep tried to redispatch, the raised
    exception would have crashed this whole task run, leaving every
    submission after the failing one in `stuck` unprocessed until
    whatever's left of Celery's own retry/redelivery budget kicked in
    (this task uses max_retries=0, so redelivery would depend entirely on
    acks_late's own visibility_timeout — minutes, not this task's own 60s
    schedule). Fixed with the same safe_task_dispatch()/log-and-continue
    pattern as scoring.py's own dispatch loop, so one submission's broker
    hiccup can't stall the rest of this run — each one is independent and
    will simply be picked up again on this task's own next scheduled pass
    if it's still stuck.

    Also covers a second, different dispatch gap found in the same audit:
    AdminGeneralScoreOverrideView (essays/views.py) fires
    generate_essay_report.delay() after a manual score override, with no
    status of its own set beforehand (generate_essay_report's own CAS
    handles LLM_COMPLETE -> REPORT_GENERATING -> REPORT_READY entirely
    internally) — so a broker-unreachable failure there leaves the
    submission sitting at LLM_COMPLETE with report_html still null,
    indefinitely, with nothing else that would ever notice or retry it.
    Same root cause as the PENDING case above (an unprotected dispatch
    with no recovery path), so it gets the same fix here rather than a
    separate new mechanism."""
    with bind_request_id(self.request.id):
        from .models import EssaySubmission, SUBMISSION_STATUS_PENDING, SUBMISSION_STATUS_LLM_COMPLETE

        threshold = timezone.now() - timezone.timedelta(minutes=UNDISPATCHED_GRACE_MINUTES)
        redispatched = 0

        stuck = list(
            EssaySubmission.objects.filter(status=SUBMISSION_STATUS_PENDING, created_at__lte=threshold)
            .select_related("attempt")
            .values_list("id", "attempt_id")[:100]
        )
        for submission_id, attempt_id in stuck:
            dispatched = safe_task_dispatch(
                evaluate_essay, str(submission_id), correlation_id=get_request_id(),
                dispatch_logger=llm_logger, context=f"evaluate_essay redispatch for submission {submission_id}",
            )
            if dispatched:
                safe_task_dispatch(
                    check_text_similarity, str(attempt_id),
                    dispatch_logger=llm_logger, context=f"check_text_similarity redispatch for attempt {attempt_id}",
                )
                redispatched += 1

        stuck_reports = list(
            EssaySubmission.objects.filter(
                status=SUBMISSION_STATUS_LLM_COMPLETE, report_html__isnull=True, updated_at__lte=threshold,
            ).values_list("id", flat=True)[:100]
        )
        redispatched_reports = 0
        for submission_id in stuck_reports:
            if safe_task_dispatch(
                generate_essay_report, str(submission_id),
                dispatch_logger=llm_logger, context=f"generate_essay_report redispatch for submission {submission_id}",
            ):
                redispatched_reports += 1

        if redispatched:
            llm_logger.warning("sweep_undispatched_submissions: re-dispatched %d stuck submission(s).", redispatched)
        if redispatched_reports:
            llm_logger.warning(
                "sweep_undispatched_submissions: re-dispatched %d stuck report generation(s).", redispatched_reports,
            )
        return {"status": "ok", "redispatched": redispatched, "redispatched_reports": redispatched_reports}


# ── Text-Similarity / Plagiarism Check (Task 5.4, ADR 002 Decision 4) ──────
# Ported from CLAP's check_text_similarity (verified by direct code
# reading): plain difflib.SequenceMatcher, O(N) per newly-completed
# student against already-completed peers, no MinHash/shingling
# pre-filter for V1 (Decision 4 point 2 — revisit only if a real timing
# measurement shows a problem, not in advance of one). Scope (Decision 4
# point 1): only the SAME EssayAssignment + SAME EssaySet. Dispatched
# fire-and-forget from scoring.py::finalize_attempts() — never blocks or
# delays the student.
# Defensive fallback only — core/settings.py::ESSAY_TEXT_SIMILARITY_THRESHOLD
# is the real, active default and always defined; see that setting's own
# comment for the full re-derivation this must be kept in sync with.
_TEXT_SIMILARITY_THRESHOLD_DEFAULT = 0.30
_TEXT_SIMILARITY_MIN_LENGTH_DEFAULT = 50
_SHINGLE_SIZE = 5
plagiarism_logger = logging.getLogger("essays.plagiarism")


def _text_shingles(text, k=_SHINGLE_SIZE):
    """Set of every run of k consecutive lowercase words in the text.

    Word-level n-gram matching instead of difflib.SequenceMatcher: the
    whole-text sequence alignment was both order-sensitive (a copied
    essay with its paragraphs reordered scored only ~33-42%) and, with
    autojunk disabled, roughly 100x slower on realistic essays (~600ms per
    comparison, ~1 hour for 2,000 peers). Shingle containment is
    order-independent, catches copied passages wherever they sit, and runs
    in ~0.02ms per comparison at 2,000 peers.
    """
    import re
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {tuple(words[i:i + k]) for i in range(max(0, len(words) - k + 1))}


def _shingle_containment(mine, theirs):
    """Fraction of this student's shingles that also appear in the peer's
    text. 0.0 when this student has no shingles (text shorter than k words)."""
    if not mine:
        return 0.0
    return len(mine & theirs) / len(mine)


@shared_task(bind=True, base=DeadLetteringTask, max_retries=3, default_retry_delay=10, time_limit=60, soft_time_limit=45)
def check_text_similarity(self, attempt_id):
    # CLAP's own check_text_similarity sets soft_time_limit=180 for its
    # platform-wide comparison scope; this task's own real timing
    # measurement (test_plagiarism.py, 150 peers) runs in well under a
    # second, so 45/60s is already generous headroom for this service's
    # deliberately narrower per-assignment scope (ADR 002 Decision 4), not
    # a blind copy of CLAP's much larger number.
    #
    # Real gap found by this phase's own 5th final-audit round: this
    # task's own decorator has always declared max_retries=3,
    # default_retry_delay=10 — values that only mean anything if the body
    # actually calls self.retry() — but the body never did. A transient
    # failure (a DB blip mid-comparison, not the two expected/permanent
    # "attempt not found" or "below floor" outcomes below) would simply
    # propagate and fail the task outright: no retry despite the
    # decorator's own declared budget, and no DLQ record at all, unlike
    # every sibling task in this file. Fixed the same way
    # sweep_expired_assignments/sweep_expired_attempts already do it: wrap
    # the substantive comparison work (not the permanent-skip branches
    # above it) in try/except, retry on failure, and add
    # base=DeadLetteringTask so a retry-ceiling-exceeded failure is
    # recorded in the same EssayFailedJob DLQ every other task in this
    # service uses — this task's own failure mode is a single uniform
    # "retry, then give up" shape, the exact fit DeadLetteringTask's own
    # docstring says it's for (unlike evaluate_essay's multi-branch shape).
    from django.conf import settings
    from .models import (
        EssayAttempt, EssayMalpracticeEvent, MALPRACTICE_EVENT_TEXT_SIMILARITY, ATTEMPT_TERMINAL_STATUSES,
    )

    threshold = getattr(settings, "ESSAY_TEXT_SIMILARITY_THRESHOLD", _TEXT_SIMILARITY_THRESHOLD_DEFAULT)
    min_length = getattr(settings, "ESSAY_TEXT_SIMILARITY_MIN_LENGTH", _TEXT_SIMILARITY_MIN_LENGTH_DEFAULT)

    with bind_request_id(self.request.id):
        try:
            attempt = EssayAttempt.objects.get(pk=attempt_id)
        except EssayAttempt.DoesNotExist:
            plagiarism_logger.warning("check_text_similarity: attempt %s not found.", attempt_id)
            return {"status": "skipped", "reason": "attempt_not_found"}

        my_text = (attempt.draft_response or "").strip()
        if len(my_text) < min_length:
            # Short overlapping phrases on trivial content produce
            # false-positive high-ratio matches — excluded entirely
            # rather than compared (Decision 4 point 4).
            return {"status": "skipped", "reason": "below_min_length"}

        try:
            # Real gap found by this phase's own final audit: this query
            # had no status filter at all, comparing against ANY peer with
            # non-empty draft text — including a student still actively
            # mid-exam, whose autosaved draft is a moving target, not the
            # "already-completed peers" ADR 002 Decision 4 and CLAP's own
            # reference implementation (verified: `status='completed'`)
            # both specify. Fixed: only compare against peers who have
            # themselves reached a terminal status.
            peers = EssayAttempt.objects.filter(
                assignment_id=attempt.assignment_id, set_id=attempt.set_id, status__in=ATTEMPT_TERMINAL_STATUSES,
            ).exclude(pk=attempt.pk).exclude(draft_response="")

            flagged = 0
            compared = 0
            my_shingles = _text_shingles(my_text)
            for peer in peers:
                peer_text = (peer.draft_response or "").strip()
                if len(peer_text) < min_length:
                    continue
                compared += 1
                ratio = _shingle_containment(my_shingles, _text_shingles(peer_text))
                if ratio >= threshold:
                    # Idempotent (Decision 4's own testing requirement): skip
                    # if this exact pair was already flagged (e.g. a task retry).
                    already = EssayMalpracticeEvent.objects.filter(
                        attempt=attempt, event_type=MALPRACTICE_EVENT_TEXT_SIMILARITY,
                        metadata__other_attempt_id=str(peer.id),
                    ).exists()
                    if not already:
                        EssayMalpracticeEvent.objects.create(
                            attempt=attempt, event_type=MALPRACTICE_EVENT_TEXT_SIMILARITY,
                            occurred_at=timezone.now(),
                            metadata={"similarity_ratio": round(ratio, 3), "other_attempt_id": str(peer.id)},
                        )
                        flagged += 1

            if flagged:
                _flag_attempt_for_text_similarity(attempt)
                plagiarism_logger.warning("check_text_similarity: attempt %s flagged %d match(es).", attempt_id, flagged)

            return {"status": "ok", "flagged": flagged, "peers_compared": compared}
        except Exception as exc:
            plagiarism_logger.error(
                "check_text_similarity failed for attempt %s (attempt %d/%d): %s",
                attempt_id, self.request.retries + 1, _MAX_RETRIES, exc,
            )
            # Jittered (Phase 18 finding) — dispatched alongside
            # evaluate_essay for every submission in the same exam-day
            # spike, same thundering-herd risk on a fixed schedule.
            raise self.retry(exc=exc, countdown=_jittered(_RETRY_BACKOFF_SECONDS * (self.request.retries + 1)))


def _flag_attempt_for_text_similarity(attempt):
    """Unlike the tab_switch/fullscreen_exit/paste_attempt reasons
    (computed once, synchronously, at finalize time — scoring.py's
    _compute_malpractice()), a text-similarity match can only be known
    after finalize, asynchronously, once a peer's essay exists to compare
    against — so this is a genuine, necessary exception to "malpractice
    fields are set once and never touched again." A plain read-then-write
    (not a second conditional UPDATE) — the race window (two
    check_text_similarity runs for the same attempt overlapping) is
    narrow and self-correcting: the membership check above means a lost
    update at worst delays one flag by one more match being found, never
    silently drops the underlying EssayMalpracticeEvent row itself, which
    is the actual audit trail."""
    from .models import EssayAttempt
    attempt.refresh_from_db(fields=["malpractice_reasons"])
    reasons = list(attempt.malpractice_reasons or [])
    if "text_similarity" not in reasons:
        reasons.append("text_similarity")
    EssayAttempt.objects.filter(pk=attempt.pk).update(malpractice_flag=True, malpractice_reasons=reasons)


# ── Generic DLQ Retry (Phase 12) ─────────────────────────────────────────────
# Reference (verified — actually read, not inferred): CLAP's own
# django-backend/api/views/admin/dlq.py::retry_dlq_entry — a generic,
# task-name-agnostic re-dispatch of whatever originally failed, not a
# per-task-type special case. Mirrored the same way here: every task this
# service can ever DLQ (evaluate_essay, generate_essay_report,
# sweep_expired_assignments, sweep_expired_attempts, check_text_similarity)
# is re-dispatched identically — `.delay(*args, **kwargs)` against the
# exact stored payload, nothing more.
#
# Deliberately simpler than evaluate_essay's own dedicated single-submission
# retry (AdminSubmissionRetriggerView, essays/views.py, Phase 7): that view
# ALSO deletes a stale EssayScore/EssayLLMTrace and pre-sets
# LLM_PROCESSING before dispatching. Neither step is needed here — a
# DLQ'd evaluate_essay entry's submission is, by construction, always at
# LLM_FAILED with NO EssayScore yet (a permanent failure only happens
# before a score is ever created), so there's nothing stale to clear. One
# accepted, deliberately-disclosed trade-off: the submission's own status
# briefly still reads LLM_FAILED for the few seconds until the retried
# evaluation actually completes (Retrigger's own explicit pre-update
# avoids that lag; this generic path can't, since it has no task-specific
# knowledge of what "in progress" should look like for an arbitrary task)
# — cosmetic only, not a correctness gap: a genuinely successful retry
# still reaches LLM_COMPLETE (and, since Phase 11, auto-generates a
# report) exactly the same either way.
#
# Second known, deliberately-disclosed limitation, found by Phase 12's own
# final-audit round: essays/views.py's own DLQ retry views now CAS-claim
# an EssayFailedJob entry (resolved_at) before dispatching, which closes
# the race between two admin-facing callers of THIS module cleanly. It
# does NOT fully close a race against sweep_dlq_entries specifically: that
# automatic sweeper dispatches evaluate_essay for an entry it has already
# fetched into its own in-memory batch, without re-checking resolved_at
# per-entry immediately before each dispatch — so an admin's manual retry
# winning the CAS claim a moment after the sweeper's own batch query ran,
# but before the sweeper's own loop reaches that specific entry, can still
# result in two concurrent evaluate_essay calls for the same submission
# (a real, billed duplicate LLM cost — ET11 — not a data-corruption risk:
# evaluate_essay's own idempotency check only prevents re-scoring an
# ALREADY-scored submission, not two truly concurrent in-flight calls).
# This same gap already exists, independently, between the sweeper and
# Phase 7's own AdminSubmissionRetriggerView — Phase 12 doesn't introduce
# a new instance of it, just a second reachable path to the same
# pre-existing one. Fully closing it needs a genuine distributed lock
# neither the sweeper nor any admin-facing retry view has today; out of
# this phase's own scope to build for a narrow, cost-only, self-converging
# race (both concurrent calls still resolve to the same correct final
# state), matching the same "honestly disclosed, not silently glossed
# over" standard as this project's other deferred-infrastructure notes
# (e.g. the bounce/complaint webhook, essays/reports.py).
def _dlq_retryable_tasks():
    """A function, not a module-level dict literal, so every task name
    below resolves against the fully-initialized module rather than
    depending on import order within this same file."""
    return {
        # Bare literal — matches _record_dlq()'s own hand-chosen name,
        # NOT Celery's real dotted one (evaluate_essay doesn't use
        # DeadLetteringTask — see this module's own header docstring for
        # why). Every other entry below goes through DeadLetteringTask.
        # on_failure(), which records Celery's real (dotted) task name —
        # see _compute_essay_dashboard's own comment (essays/views.py,
        # Phase 11) for the first place this exact inconsistency already
        # had to be handled.
        "evaluate_essay": evaluate_essay,
        "essays.tasks.generate_essay_report": generate_essay_report,
        "essays.tasks.sweep_expired_assignments": sweep_expired_assignments,
        "essays.tasks.sweep_expired_attempts": sweep_expired_attempts,
        "essays.tasks.check_text_similarity": check_text_similarity,
        # Phase 11's own task, found missing from this registry during
        # Phase 13's audit (it uses DeadLetteringTask like the others
        # above, so it does DLQ, but was never wired up to be re-dispatch-
        # able) — fixed here per this registry's own maintenance note.
        "essays.tasks.send_essay_report_email": send_essay_report_email,
        # Phase 13 — registered proactively (not left for a later audit
        # round to find, matching this registry's own "every task added
        # to this file must also be added here" maintenance note above):
        # takes no args, same shape as the two sweep tasks, safe to
        # re-dispatch generically.
        "essays.tasks.send_pipeline_health_summary_email": send_pipeline_health_summary_email,
    }


def retry_dlq_entry(entry):
    """Re-dispatches the exact task + args + kwargs an EssayFailedJob
    entry recorded. Raises ValueError for an unrecognized task_name
    (defensive only — every task this service can actually DLQ is
    registered above; an unrecognized name would mean a new task was
    added to this file without also being added here) rather than
    silently doing nothing."""
    task = _dlq_retryable_tasks().get(entry.task_name)
    if task is None:
        raise ValueError(f"Don't know how to retry task {entry.task_name!r}.")
    task.delay(*(entry.args or []), **(entry.kwargs or {}))


# Task names whose EssayFailedJob entries are tied to one specific
# submission (their own first positional arg) — used by the DLQ module's
# own retry/resolve views (essays/views.py) to decide whether an action
# also belongs on that submission's own EssaySubmissionEvent audit trail
# (Task 6.1's "full audit-log/event trail" promise). Broader than
# _SUBMISSION_SCOPED_TASK_NAMES above (which exists specifically for
# DeadLetteringTask.on_failure() and deliberately excludes evaluate_essay,
# since ITS OWN failures already log through _record_dlq() instead) —
# this one is for the DLQ module's own new, generic admin actions, where
# evaluate_essay entries need the exact same audit-trail treatment as
# generate_essay_report ones. check_text_similarity is deliberately NOT
# included: its own args[0] is an attempt id, not a submission id, and
# EssaySubmissionEvent has no attempt-scoped equivalent to log to.
# send_essay_report_email added during Phase 13's audit — same reasoning
# as _SUBMISSION_SCOPED_TASK_NAMES above.
DLQ_SUBMISSION_SCOPED_TASK_NAMES = frozenset({
    "evaluate_essay", "essays.tasks.generate_essay_report", "essays.tasks.send_essay_report_email",
})

# Derived, not copied from CLAP's own "100" (Task 12.1's own explicit
# instruction): this service is single-domain (writing only) against
# CLAP's own writing+speaking pipeline, so its own realistic DLQ backlog
# is smaller. At the effective aggregate throughput ADR 003/004 already
# establish (~40 RPM with a reasonably-sized rotated key pool, per
# QuotaTracker's own 90%-margin math), 50 simultaneous fresh dispatches
# drain in close to a minute — a small, bounded burst, not a flood — while
# still being large enough to clear a genuine systemic-outage backlog in
# one action rather than forcing dozens of repeated small retries.
DLQ_BULK_RETRY_CAP = 50


# ── Notifications Module (Phase 13) ─────────────────────────────────────────
# See essays/notifications.py's own module docstring for the full,
# doubly-verified correction to Task 13.1's own "reuse notification-
# service" claim (factually wrong about that service's real capabilities,
# and citing a Non-Negotiable Constraint that says something unrelated).
# Sent via the same direct-SMTP mechanism Phase 11 already built
# (send_essay_report_email's own precedent), to a static,
# env-var-configured recipient list.
@shared_task(bind=True, base=DeadLetteringTask, max_retries=_MAX_RETRIES, default_retry_delay=_RETRY_BACKOFF_SECONDS,
             time_limit=60, soft_time_limit=45)
def send_pipeline_health_summary_email(self):
    """Both the automatic daily dispatch (core/settings.py's own
    CELERY_BEAT_SCHEDULE entry, "send-daily-pipeline-summary") and the
    manual "send now" action (AdminSendDailySummaryView, essays/views.py)
    call this exact task — never two separate code paths that could
    silently drift apart in content or recipients. No-ops (logs, doesn't
    send, doesn't raise) when ALERT_EMAIL_RECIPIENTS is empty — matches
    Task 13.1's own "optional" framing without needing conditional
    beat-schedule registration; a bare, empty-recipients config is the
    expected default in dev/test, not an error state."""
    from django.conf import settings
    from django.core.mail import send_mail
    from .notifications import (
        compute_pipeline_health_summary, generate_pipeline_alerts, render_daily_summary_email_html,
        ALERT_TIER_P1, ALERT_TIER_P2,
    )

    with bind_request_id(self.request.id):
        if not settings.ALERT_EMAIL_RECIPIENTS:
            logger.info("send_pipeline_health_summary_email: no ALERT_EMAIL_RECIPIENTS configured — skipping.")
            return {"status": "skipped", "reason": "no_recipients"}

        summary = compute_pipeline_health_summary(settings.PIPELINE_SUMMARY_DEFAULT_WINDOW_HOURS)
        alerts = generate_pipeline_alerts(summary)

        if any(a["tier"] == ALERT_TIER_P1 for a in alerts):
            tier_label = "P1 CRITICAL"
        elif any(a["tier"] == ALERT_TIER_P2 for a in alerts):
            tier_label = "P2 WARNING"
        else:
            tier_label = "OK"

        try:
            send_mail(
                subject=f"Essay Service Daily Summary — {tier_label}",
                message=f"{len(alerts)} alert(s). View this email in an HTML-capable client for details.",
                html_message=render_daily_summary_email_html(summary, alerts),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=settings.ALERT_EMAIL_RECIPIENTS,
                fail_silently=False,
            )
        except Exception as exc:
            logger.exception("send_pipeline_health_summary_email: send failed.")
            raise self.retry(exc=exc, countdown=_RETRY_BACKOFF_SECONDS * (self.request.retries + 1))

        logger.info(
            "send_pipeline_health_summary_email: sent (%s, %d alert(s)) to %d recipient(s).",
            tier_label, len(alerts), len(settings.ALERT_EMAIL_RECIPIENTS),
        )
        return {"status": "ok", "tier": tier_label, "alert_count": len(alerts)}
