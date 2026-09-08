"""
tasks.py — the Celery beat sweep (Task 4.1, ADR 001).

Two independent periodic tasks, both scheduled every 20s (within the ADR's
15-30s window — see core/settings.py's CELERY_BEAT_SCHEDULE):

  sweep_expired_assignments — BatchAssignment LIVE -> CLOSED once
    global_expire_time passes, independent of any admin action.

  sweep_expired_sessions — AssessmentSession IN_PROGRESS -> AUTO_SUBMITTED
    once ends_at passes, scored via scoring.finalize_sessions() (the same
    primitive Task 3.2's close/ cascade and Task 5.2's manual submit use).

Failure handling: each task retries with exponential-ish backoff on any
unexpected exception (network hiccup, transient DB error) rather than
silently dropping that sweep cycle. Task 13.1 wires a real dead-letter
queue for exhausted retries (AT12): once a task's own max_retries is used
up, Celery calls on_failure() below, which writes a FailedJob row
(models.py) — that row is the actual dead-letter record; the "sweep
failure" log line that existed before Task 13.1 is still emitted too
(logs and the DLQ table serve different audiences — Sentry/log aggregation
vs. an on-call engineer running the runbook's triage query), but a log
line alone was never enough to guarantee visibility (log retention expires,
nobody's necessarily watching in real time) — the DLQ row persists until a
human resolves it.
"""

import logging

from celery import Task, shared_task
from django.utils import timezone

from core.logging_utils import bind_request_id

logger = logging.getLogger("assessments.sweep")

# Matches CELERY_BEAT_SCHEDULE's cadence — a failed attempt backs off but
# still resolves well within the next scheduled run.
_RETRY_BACKOFF_SECONDS = 10
_MAX_RETRIES = 3


class DeadLetteringTask(Task):
    """Celery calls on_failure() exactly once a task gives up for good —
    either max_retries is exhausted (self.retry() re-raises
    MaxRetriesExceededError) or an exception escapes without being
    retried. Both land here. Set as `base=` on both sweep tasks below
    instead of duplicating this logic inside each task's own except block."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        from .models import FailedJob
        try:
            FailedJob.objects.create(
                task_name=self.name,
                task_id=task_id or "",
                args=list(args or []),
                kwargs=dict(kwargs or {}),
                error=str(exc),
                traceback=str(einfo) if einfo else "",
                attempts=_MAX_RETRIES,
            )
            logger.error("%s permanently failed after %d attempts — recorded in FailedJob DLQ.", self.name, _MAX_RETRIES)
        except Exception:
            # A failure while trying to *record* a failure must never mask
            # the original one Celery is already handling here, and must
            # never itself become an unhandled exception inside Celery's
            # own failure-handling path.
            logger.exception("%s permanently failed AND could not be recorded in the FailedJob DLQ.", self.name)
        super().on_failure(exc, task_id, args, kwargs, einfo)


@shared_task(bind=True, base=DeadLetteringTask, max_retries=_MAX_RETRIES, default_retry_delay=_RETRY_BACKOFF_SECONDS)
def sweep_expired_assignments(self):
    from .models import BatchAssignment, ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_CLOSED

    # bind_request_id (Task 13.2): every log line this run produces —
    # including ones from deeper in the call stack — shares this run's own
    # Celery task_id as its correlation ID, the task-run equivalent of an
    # HTTP request's X-Request-ID.
    with bind_request_id(self.request.id):
        try:
            # Single conditional UPDATE ... WHERE status='LIVE' — race-safe
            # against a concurrent admin close/ (Task 3.2): whichever write
            # lands second simply matches 0 rows.
            closed = BatchAssignment.objects.filter(
                status=ASSIGNMENT_STATUS_LIVE, global_expire_time__lte=timezone.now(),
            ).update(status=ASSIGNMENT_STATUS_CLOSED)
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
def sweep_expired_sessions(self):
    from .models import AssessmentSession, SESSION_STATUS_AUTO_SUBMITTED
    from .scoring import finalize_sessions

    with bind_request_id(self.request.id):
        try:
            expired = AssessmentSession.objects.filter(ends_at__lte=timezone.now())
            auto_submitted = finalize_sessions(expired, SESSION_STATUS_AUTO_SUBMITTED)
            if auto_submitted:
                logger.info("sweep_expired_sessions: auto-submitted %d session(s).", auto_submitted)
            return {"auto_submitted": auto_submitted}
        except Exception as exc:
            logger.error(
                "sweep_expired_sessions failed (attempt %d/%d): %s",
                self.request.retries + 1, _MAX_RETRIES, exc,
            )
            raise self.retry(exc=exc, countdown=_RETRY_BACKOFF_SECONDS * (self.request.retries + 1))


# purge_old_activity_logs runs once/day (CELERY_BEAT_SCHEDULE), not every
# 20s like the two sweeps above — this is low-urgency storage housekeeping,
# not exam-timing enforcement, so it doesn't need their tight cadence.
_PURGE_BATCH_SIZE = 1000
# Safety cap, same convention as allocation.py's _MAX_PAGES: bounds one
# run's worst case (500k rows/run) instead of one run silently churning
# through an unbounded backlog forever if the schedule was ever paused for
# a long stretch and there's a huge purge queued up. The *next* day's run
# picks up wherever this one left off — nothing is lost, just deferred.
_PURGE_MAX_BATCHES = 500


@shared_task(bind=True, base=DeadLetteringTask, max_retries=_MAX_RETRIES, default_retry_delay=_RETRY_BACKOFF_SECONDS)
def purge_old_activity_logs(self):
    """Deletes ActivityLog rows older than ACTIVITY_LOG_RETENTION_DAYS
    (models.py) — the raw tab-switch/copy/paste/etc. audit trail only.
    AssessmentResponse, ResultSummary, and every score/malpractice value
    are permanent academic records and are never touched here.

    Two safety properties, both deliberate:
      1. Only ever deletes logs belonging to a session that has already
         finished (status != IN_PROGRESS) — even though 15 days is
         hugely longer than any realistic exam duration and this could
         never matter in practice, an active session's own audit trail
         must never be a candidate no matter what, on principle.
      2. Deletes in small batches (_PURGE_BATCH_SIZE), not one unbounded
         DELETE — keeps each individual transaction/lock short instead of
         holding the whole (potentially huge) backlog in one transaction,
         same batching discipline as allocation.py's bulk_create and
         scoring.py's bulk_update.
    """
    from .models import ActivityLog, ACTIVITY_LOG_RETENTION_DAYS, SESSION_STATUS_IN_PROGRESS

    with bind_request_id(self.request.id):
        try:
            cutoff = timezone.now() - timezone.timedelta(days=ACTIVITY_LOG_RETENTION_DAYS)
            total_deleted = 0
            for _ in range(_PURGE_MAX_BATCHES):
                stale_ids = list(
                    ActivityLog.objects.filter(occurred_at__lt=cutoff)
                    .exclude(session__status=SESSION_STATUS_IN_PROGRESS)
                    .values_list("id", flat=True)[:_PURGE_BATCH_SIZE]
                )
                if not stale_ids:
                    break
                ActivityLog.objects.filter(id__in=stale_ids).delete()
                total_deleted += len(stale_ids)
            else:
                logger.warning(
                    "purge_old_activity_logs: hit the %d-batch safety cap (%d rows deleted this "
                    "run) — there may still be more stale rows left; tomorrow's run will continue.",
                    _PURGE_MAX_BATCHES, total_deleted,
                )
            if total_deleted:
                logger.info("purge_old_activity_logs: deleted %d row(s) older than %d days.", total_deleted, ACTIVITY_LOG_RETENTION_DAYS)
            return {"deleted": total_deleted}
        except Exception as exc:
            logger.error(
                "purge_old_activity_logs failed (attempt %d/%d): %s",
                self.request.retries + 1, _MAX_RETRIES, exc,
            )
            raise self.retry(exc=exc, countdown=_RETRY_BACKOFF_SECONDS * (self.request.retries + 1))
