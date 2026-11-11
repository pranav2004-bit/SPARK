"""
reports.py — Phase 11, Task 11.1: renders a per-submission report as a
self-contained HTML string.

**Storage decision (verified — actually read, not inferred, from CLAP's own
django-backend/api/views/admin/report_management.py):** CLAP generates a
PDF and stores it on S3, then keeps `report_url` pointing at it.
essay-service does neither: it has no S3 wiring (docs/adr/002 Decision 5
deliberately keeps this service binary-upload-free) and no PDF-rendering
dependency anywhere in its own requirements.txt. Re-adding either just for
this one feature would be new infrastructure for a service whose own
capacity numbers (Task 0.4 — tens-to-low-hundreds of reports per
assignment, not thousands) don't need it. A self-contained HTML string,
stored directly on `EssaySubmission.report_html` (a plain TextField), is
the proportionate substitute: it's viewable in a browser tab, downloadable
as-is, and attachable to an email (`send_mail(..., html_message=...)`,
see `send_essay_report_email`, essays/tasks.py) with zero extra
dependencies. What actually matters from CLAP's own history — preserved
here in full — is the STATUS MACHINE reliability lessons (the
LLM_COMPLETE -> REPORT_GENERATING -> REPORT_READY guard,
`generate_essay_report`/`AdminReportRegenerateView`), not the storage
medium those lessons happened to be documented against.

**Delivery-mechanism correction (verified — see also
SUBMISSION_EVENT_EMAIL_BOUNCED's own comment, essays/models.py, and
core/settings.py's own Email Delivery section):** the Phase 11 tracker's
own text names reusing notification-service's "existing outbox/delivery
integration". Checked directly against that service's real code before
writing any of this module: notification-service's only model
(`Notification`) is purely in-app (user_id, institution_id, type, title,
body, is_read) — there is no EMAIL_BACKEND/SMTP configuration anywhere in
it, no bounce/complaint tracking, and no other service on this platform
calls it to send an email. The only genuine SMTP precedent anywhere in
this monorepo is user-service's own settings (used there only for
`mail_admins()` dead-letter alerts) — mirrored into this service's own
settings instead, and used directly via Django's own `django.core.mail`,
not a nonexistent notification-service integration.

**Bounce/complaint tracking — honestly disclosed, not faked (matching this
project's own ADR 004 "real OpenAI account tier" precedent for a deferred
external dependency):** `SUBMISSION_EVENT_EMAIL_BOUNCED` /
`_COMPLAINT` and the delivery-status computation that reads them
(`_essay_delivery_status`, essays/views.py) are real, fully working, and
fully tested today via directly-recorded test events. What does NOT exist
yet, anywhere on this platform, is a live webhook endpoint that lets a
real email provider (e.g. SES/SendGrid) actually write those events from
a real bounce/complaint — building one would mean standing up inbound
webhook infrastructure this platform has never needed before, for a
provider integration that hasn't been chosen yet. Deferred, not faked:
the schema and status logic are ready for a future webhook to start
writing to without any further change here.

**Institution branding — evaluated, not built:** Task 11.1 asks this to
be evaluated before building it. Searched this platform for any existing
per-institution branding config (logo/name/layout) — none exists; the
only institution-scoped model anywhere is analytics-service's
`InstitutionSnapshot`, which is unrelated aggregate data, not branding.
SPARK's own institution model has no `logo_url`/`display_name`/theme
fields today. Building a new, standalone branding config just for this
one report's own header would be exactly the over-engineering this
project's own conventions warn against, for a need nothing else on the
platform has ever established. Skipped — the report below uses the
institution/paper/assignment's own already-real data (title, question)
for its header, nothing more.
"""

import html
from datetime import timezone as _dt_timezone


def _esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def _fmt_dt(dt) -> str:
    if dt is None:
        return "—"
    return dt.astimezone(_dt_timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render_report_html(submission) -> str:
    """Builds the full report for one submission. Expects `submission` to
    have `attempt__assignment__paper` and `attempt__set__question`
    select_related (generate_essay_report, essays/tasks.py, already does
    this) — falls back to a live query for either if not, so this
    function is still correct (just less efficient) if ever called
    without that select_related.
    """
    attempt = submission.attempt
    assignment = attempt.assignment
    paper = assignment.paper
    question = getattr(attempt.set, "question", None)
    score = getattr(submission, "score", None)

    question_text = question.question_text if question is not None else ""
    rubric_criteria = (score.feedback.get("breakdown") if score is not None else None) or {}
    overall_feedback = (score.feedback.get("overall") if score is not None else None) or ""

    criteria_rows = "".join(
        f"<tr><td>{_esc(name)}</td><td>{_esc(detail.get('score', ''))} / {_esc(detail.get('maxScore', ''))}</td>"
        f"<td>{_esc(detail.get('feedback', ''))}</td></tr>"
        for name, detail in rubric_criteria.items()
        if isinstance(detail, dict)
    )

    malpractice_html = ""
    if attempt.malpractice_flag:
        reasons = ", ".join(_esc(r) for r in (attempt.malpractice_reasons or [])) or "unspecified"
        malpractice_html = (
            f'<p class="flag">⚠ This attempt was flagged for a possible integrity concern: {reasons}.</p>'
        )

    score_html = (
        f'<p class="score">Score: <strong>{_esc(score.score)} / 10</strong>'
        f'{" (admin override)" if score is not None and score.evaluated_by == "admin" else ""}</p>'
        if score is not None else '<p class="score">Not yet scored.</p>'
    )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Essay Report — {_esc(paper.title)}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; max-width: 720px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 20px; }}
  h2 {{ font-size: 16px; margin-top: 28px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
  .meta {{ color: #555; font-size: 13px; }}
  .score {{ font-size: 16px; }}
  .flag {{ color: #92400e; background: #fef3c7; padding: 8px 12px; border-radius: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; font-size: 13px; vertical-align: top; }}
  .response {{ white-space: pre-wrap; background: #fafafa; border: 1px solid #eee; padding: 12px; font-size: 13px; }}
</style>
</head>
<body>
  <h1>Essay Evaluation Report</h1>
  <p class="meta">{_esc(paper.title)} &middot; generated {_fmt_dt(submission.updated_at)}</p>

  {score_html}
  {malpractice_html}

  <h2>Question</h2>
  <p>{_esc(question_text)}</p>

  <h2>Response</h2>
  <div class="response">{_esc(attempt.draft_response)}</div>

  <h2>Feedback</h2>
  <p>{_esc(overall_feedback)}</p>
  {f"<table><thead><tr><th>Criterion</th><th>Score</th><th>Feedback</th></tr></thead><tbody>{criteria_rows}</tbody></table>" if criteria_rows else ""}
</body>
</html>"""
