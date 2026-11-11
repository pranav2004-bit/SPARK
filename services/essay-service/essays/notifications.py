"""
notifications.py — Phase 13, Task 13.1: pipeline-health summary + tiered
alert computation, and the daily-summary email's own HTML rendering.

A dedicated module, not inlined into views.py or tasks.py, for the same
reason essays/reports.py is one (Phase 11): this logic is genuinely
shared between an admin-facing view (AdminPipelineHealthSummaryView,
essays/views.py) and a Celery task (send_pipeline_health_summary_email,
essays/tasks.py), and views.py already imports FROM tasks.py throughout
this codebase — the reverse direction (tasks.py importing from views.py)
doesn't exist anywhere else here, so introducing it just for this feature
would be a one-off inconsistency. Putting the shared logic in its own
module, imported by both, avoids the question entirely.

**Correction, verified — not followed as written (also documented in
core/settings.py's own comment on ALERT_EMAIL_RECIPIENTS):** Task 13.1's
own tracker text says the daily summary should "reuse notification-service's
existing send mechanism (per Non-Negotiable Constraint §5's spirit: don't
build a second email-sending path)". Checked directly before writing
anything here: (1) notification-service has no email-sending capability
at all — already verified once for Phase 11's own delivery tracking (see
essays/reports.py's own module docstring), unchanged since; (2)
Non-Negotiable Constraint §5 itself is "No LLM call is ever made
synchronously in a student-facing request" — entirely unrelated to email,
so the tracker's own citation doesn't even support its own claim. Sent
instead via the same direct-SMTP mechanism Phase 11 already built and
proved out (send_essay_report_email, essays/tasks.py) — to a static,
env-var-configured recipient list (ALERT_EMAIL_RECIPIENTS), not a
dynamically-looked-up one, matching the one real precedent anywhere on
this platform for "alert admins by email" (user-service's own dead-letter
outbox) — see core/settings.py's own comment for the full reasoning
behind why a dynamic super-admin lookup isn't available to build against.
"""
import html as _html
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone


def dlq_unresolved_snapshot():
    """(unresolved_count, oldest_unresolved_age_seconds) — a current-state
    snapshot ("how many are stuck RIGHT NOW"), not time-windowed, matching
    Phase 6/12's own established treatment of this exact pair of numbers.
    Used by both AdminSubmissionsPipelineHealthView (Phase 6) and
    compute_pipeline_health_summary below (Phase 13) — the one place this
    query is written, not duplicated."""
    from .models import EssayFailedJob
    unresolved = EssayFailedJob.objects.filter(resolved_at__isnull=True)
    count = unresolved.count()
    oldest = unresolved.order_by("created_at").first()
    age_seconds = int((timezone.now() - oldest.created_at).total_seconds()) if oldest is not None else None
    return count, age_seconds


def undispatched_submissions_snapshot():
    """(stuck_count, oldest_stuck_age_seconds) — the same pair of numbers
    dlq_unresolved_snapshot() returns, for a different failure mode: a
    submission whose dispatch to the AI worker never even reached the
    broker (e.g. Redis was unreachable at the exact moment of submit/
    auto-close), so it never had the chance to fail and land in the DLQ
    (found and fixed post-Task 18.2 — see LIVETRACKER3_V1.md's "Post-18.2
    follow-up" sections). Scoped to the same UNDISPATCHED_GRACE_MINUTES
    threshold sweep_undispatched_submissions (essays/tasks.py) itself
    uses, not every PENDING row — a submission is normally PENDING for
    well under a second before a worker picks it up, so counting all of
    them would show a constantly-nonzero, meaningless number during
    perfectly healthy operation. Used by AdminSubmissionsPipelineHealthView
    so this failure mode is visible in the same live admin tile the DLQ
    count already appears in, not only reachable via a manual shell query."""
    from .models import EssaySubmission, SUBMISSION_STATUS_PENDING
    from .tasks import UNDISPATCHED_GRACE_MINUTES
    threshold = timezone.now() - timedelta(minutes=UNDISPATCHED_GRACE_MINUTES)
    stuck = EssaySubmission.objects.filter(status=SUBMISSION_STATUS_PENDING, created_at__lte=threshold)
    count = stuck.count()
    oldest = stuck.order_by("created_at").first()
    age_seconds = int((timezone.now() - oldest.created_at).total_seconds()) if oldest is not None else None
    return count, age_seconds


def compute_pipeline_health_summary(window_hours):
    """Task 13.1's own explicit list: total/completed/failed submission
    counts over the window, unresolved-DLQ count + oldest-unresolved age
    (current-state — see dlq_unresolved_snapshot's own docstring for why
    that pair is deliberately NOT time-windowed), and recent
    failure-shaped audit events. Platform-wide, not institution-scoped —
    matches AdminSubmissionsPipelineHealthView's own already-established
    precedent (Phase 6) for this exact class of shared-infrastructure
    operational data, not per-tenant content.

    "Failure-shaped audit event" = SUBMISSION_EVENT_DLQ_RECORDED (a
    permanent pipeline failure — written for BOTH evaluate_essay, via
    _record_dlq(), and generate_essay_report, via DeadLetteringTask.
    on_failure() since Phase 11's own audit fix) or an email delivery
    failure (EMAIL_BOUNCED/EMAIL_COMPLAINT, Phase 11). Deliberately does
    NOT also pattern-match STATUS_CHANGE events whose own free-text
    detail happens to mention LLM_FAILED — DLQ_RECORDED is already
    written at the exact same moment a permanent failure occurs, so
    counting both would double-count the same underlying event."""
    from .models import (
        EssaySubmission, EssaySubmissionEvent,
        SUBMISSION_EVENT_DLQ_RECORDED, SUBMISSION_EVENT_EMAIL_BOUNCED, SUBMISSION_EVENT_EMAIL_COMPLAINT,
    )
    # Local import — views.py's own _SUBMISSION_STATUS_BUCKETS is the one
    # place this 4-bucket rollup is defined; reused here rather than
    # re-declaring a second, parallel copy that could drift from it.
    from .views import _SUBMISSION_STATUS_BUCKETS

    window_start = timezone.now() - timedelta(hours=window_hours)

    submissions_in_window = EssaySubmission.objects.filter(created_at__gte=window_start)
    status_counts = dict(
        submissions_in_window.values_list("status").annotate(c=Count("id")).values_list("status", "c")
    )
    total_submissions = sum(status_counts.values())
    completed_submissions = sum(status_counts.get(s, 0) for s in _SUBMISSION_STATUS_BUCKETS["completed"])
    failed_submissions = sum(status_counts.get(s, 0) for s in _SUBMISSION_STATUS_BUCKETS["failed"])

    unresolved_dlq_count, oldest_unresolved_dlq_age_seconds = dlq_unresolved_snapshot()
    undispatched_submission_count, oldest_undispatched_submission_age_seconds = undispatched_submissions_snapshot()

    failure_events = EssaySubmissionEvent.objects.filter(
        event_type__in=[SUBMISSION_EVENT_DLQ_RECORDED, SUBMISSION_EVENT_EMAIL_BOUNCED, SUBMISSION_EVENT_EMAIL_COMPLAINT],
        occurred_at__gte=window_start,
    ).order_by("-occurred_at")
    recent_failure_event_count = failure_events.count()
    recent_failure_events = [
        {"event_type": e.event_type, "detail": e.detail, "occurred_at": e.occurred_at}
        for e in failure_events[:10]
    ]

    return {
        "window_hours": window_hours,
        "generated_at": timezone.now().isoformat(),
        "total_submissions": total_submissions,
        "completed_submissions": completed_submissions,
        "failed_submissions": failed_submissions,
        "unresolved_dlq_count": unresolved_dlq_count,
        "oldest_unresolved_dlq_age_seconds": oldest_unresolved_dlq_age_seconds,
        "undispatched_submission_count": undispatched_submission_count,
        "oldest_undispatched_submission_age_seconds": oldest_undispatched_submission_age_seconds,
        "recent_failure_event_count": recent_failure_event_count,
        "recent_failure_events": recent_failure_events,
    }


ALERT_TIER_P1 = "P1"
ALERT_TIER_P2 = "P2"


def generate_pipeline_alerts(summary):
    """Checks the summary against core/settings.py's own tiered
    thresholds — re-derived for this service (see those settings' own
    comments for the full derivation reasoning), not CLAP's numbers
    copied as-is, per Task 13.1's own explicit instruction. A metric that
    breaches both tiers only ever reports the higher one (P1), never
    both, so an admin never sees two alerts for the same underlying
    number."""
    from django.conf import settings

    alerts = []

    dlq_count = summary["unresolved_dlq_count"]
    p1_dlq, p2_dlq = settings.PIPELINE_ALERT_DLQ_UNRESOLVED_P1, settings.PIPELINE_ALERT_DLQ_UNRESOLVED_P2
    if dlq_count > p1_dlq:
        alerts.append({
            "tier": ALERT_TIER_P1, "metric": "dlq_unresolved_count",
            "message": f"{dlq_count} unresolved DLQ entries (critical threshold: {p1_dlq}).",
            "value": dlq_count, "threshold": p1_dlq,
        })
    elif dlq_count > p2_dlq:
        alerts.append({
            "tier": ALERT_TIER_P2, "metric": "dlq_unresolved_count",
            "message": f"{dlq_count} unresolved DLQ entries (warning threshold: {p2_dlq}).",
            "value": dlq_count, "threshold": p2_dlq,
        })

    age_seconds = summary["oldest_unresolved_dlq_age_seconds"]
    if age_seconds is not None:
        age_minutes = age_seconds / 60
        p1_age, p2_age = settings.PIPELINE_ALERT_DLQ_OLDEST_AGE_P1_MINUTES, settings.PIPELINE_ALERT_DLQ_OLDEST_AGE_P2_MINUTES
        if age_minutes > p1_age:
            alerts.append({
                "tier": ALERT_TIER_P1, "metric": "dlq_oldest_unresolved_age",
                "message": f"Oldest unresolved DLQ entry is {int(age_minutes)} minute(s) old (critical threshold: {p1_age}).",
                "value": age_seconds, "threshold": p1_age * 60,
            })
        elif age_minutes > p2_age:
            alerts.append({
                "tier": ALERT_TIER_P2, "metric": "dlq_oldest_unresolved_age",
                "message": f"Oldest unresolved DLQ entry is {int(age_minutes)} minute(s) old (warning threshold: {p2_age}).",
                "value": age_seconds, "threshold": p2_age * 60,
            })

    # Deliberately age-only, no count-based tier — see
    # PIPELINE_ALERT_UNDISPATCHED_AGE_P1/P2_MINUTES's own comment
    # (core/settings.py) for why: this count is expected to spike into
    # the hundreds during a mass-simultaneous exam expiry overlapping a
    # brief outage and self-drains within minutes on its own — alerting
    # on count alone would fire false alarms for exactly that expected,
    # bounded case. Age is what actually indicates the broker itself is
    # still down, regardless of how many piled up while it was.
    undispatched_age_seconds = summary["oldest_undispatched_submission_age_seconds"]
    if undispatched_age_seconds is not None:
        undispatched_age_minutes = undispatched_age_seconds / 60
        p1_undispatched_age = settings.PIPELINE_ALERT_UNDISPATCHED_AGE_P1_MINUTES
        p2_undispatched_age = settings.PIPELINE_ALERT_UNDISPATCHED_AGE_P2_MINUTES
        if undispatched_age_minutes > p1_undispatched_age:
            alerts.append({
                "tier": ALERT_TIER_P1, "metric": "undispatched_submission_oldest_age",
                "message": (
                    f"Oldest undispatched submission is {int(undispatched_age_minutes)} minute(s) old "
                    f"(critical threshold: {p1_undispatched_age}) — the broker may still be unreachable."
                ),
                "value": undispatched_age_seconds, "threshold": p1_undispatched_age * 60,
            })
        elif undispatched_age_minutes > p2_undispatched_age:
            alerts.append({
                "tier": ALERT_TIER_P2, "metric": "undispatched_submission_oldest_age",
                "message": (
                    f"Oldest undispatched submission is {int(undispatched_age_minutes)} minute(s) old "
                    f"(warning threshold: {p2_undispatched_age})."
                ),
                "value": undispatched_age_seconds, "threshold": p2_undispatched_age * 60,
            })

    failure_count = summary["recent_failure_event_count"]
    p2_events = settings.PIPELINE_ALERT_FAILURE_EVENTS_P2
    if failure_count > p2_events:
        alerts.append({
            "tier": ALERT_TIER_P2, "metric": "recent_failure_events",
            "message": f"{failure_count} failure-shaped event(s) in the last {summary['window_hours']}h (warning threshold: {p2_events}).",
            "value": failure_count, "threshold": p2_events,
        })

    return alerts


def _esc(value) -> str:
    return _html.escape(str(value)) if value is not None else ""


def render_daily_summary_email_html(summary, alerts) -> str:
    """The daily summary's own HTML body — self-contained, matching
    essays/reports.py's own render_report_html() convention (inline
    <style>, no external assets, safe to hand straight to send_mail's
    own html_message=)."""
    tier_colors = {ALERT_TIER_P1: "#DC2626", ALERT_TIER_P2: "#D97706"}
    alert_rows = "".join(
        f'<tr><td style="color:{tier_colors.get(a["tier"], "#6B7280")};font-weight:bold;">{_esc(a["tier"])}</td>'
        f'<td>{_esc(a["message"])}</td></tr>'
        for a in alerts
    )
    alerts_html = (
        f'<table style="width:100%;border-collapse:collapse;margin-top:8px;">'
        f'<thead><tr><th style="text-align:left;">Tier</th><th style="text-align:left;">Alert</th></tr></thead>'
        f'<tbody>{alert_rows}</tbody></table>'
    ) if alerts else '<p style="color:#16A34A;">No active alerts — pipeline looks healthy.</p>'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Essay Service Daily Summary</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; max-width: 640px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 18px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; font-size: 13px; }}
  .meta {{ color: #555; font-size: 12px; }}
</style>
</head>
<body>
  <h1>Essay Service — Daily Pipeline Summary</h1>
  <p class="meta">Window: last {_esc(summary['window_hours'])}h &middot; generated {_esc(summary['generated_at'])}</p>

  <table>
    <tr><td>Total submissions</td><td>{_esc(summary['total_submissions'])}</td></tr>
    <tr><td>Completed</td><td>{_esc(summary['completed_submissions'])}</td></tr>
    <tr><td>Failed</td><td>{_esc(summary['failed_submissions'])}</td></tr>
    <tr><td>Unresolved DLQ entries</td><td>{_esc(summary['unresolved_dlq_count'])}</td></tr>
    <tr><td>Oldest unresolved DLQ age</td><td>{_esc(round(summary['oldest_unresolved_dlq_age_seconds'] / 60)) if summary['oldest_unresolved_dlq_age_seconds'] is not None else "—"} min</td></tr>
    <tr><td>Undispatched submissions</td><td>{_esc(summary['undispatched_submission_count'])}</td></tr>
    <tr><td>Oldest undispatched submission age</td><td>{_esc(round(summary['oldest_undispatched_submission_age_seconds'] / 60)) if summary['oldest_undispatched_submission_age_seconds'] is not None else "—"} min</td></tr>
    <tr><td>Failure-shaped events in window</td><td>{_esc(summary['recent_failure_event_count'])}</td></tr>
  </table>

  <h2 style="font-size:15px;margin-top:20px;">Alerts</h2>
  {alerts_html}
</body>
</html>"""
