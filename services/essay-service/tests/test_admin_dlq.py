"""
test_admin_dlq.py — Phase 12's own testing checklist (Task 12.1): retry-
from-DLQ happy path, bulk-retry cap enforced, resolve-then-retry-attempt
handled gracefully (idempotent, not an error), detail view exposes enough
to actually debug a real failure (full task payload).

The automatic sweeper (sweep_dlq_entries) and evaluate_essay's own DLQ
recording are already covered by test_dlq.py and test_evaluate_essay.py —
not duplicated here. This file is the ADMIN-FACING module (Phase 12):
list/detail/retry/resolve/bulk-retry views.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt, EssaySubmission,
    EssaySubmissionEvent, EssayFailedJob,
    SUBMISSION_STATUS_LLM_FAILED, SUBMISSION_EVENT_ADMIN_RETRIGGER, SUBMISSION_EVENT_ADMIN_OVERRIDE,
)
from essays.tasks import DLQ_BULK_RETRY_CAP, retry_dlq_entry

from .conftest import INSTITUTION_A, INSTITUTION_B, ADMIN_USER_ID


def _make_submission(*, institution_id=INSTITUTION_A, status=SUBMISSION_STATUS_LLM_FAILED):
    paper = EssayPaper.objects.create(institution_id=institution_id, title="P", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
    assignment = EssayAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=institution_id,
        global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
    )
    attempt = EssayAttempt.objects.create(
        assignment=assignment, student_id=uuid.uuid4(), set=eset,
        ends_at=timezone.now() + timedelta(hours=1), draft_response="An essay response.",
    )
    submission = EssaySubmission.objects.create(attempt=attempt)
    EssaySubmission.objects.filter(pk=submission.pk).update(status=status)
    submission.refresh_from_db()
    return submission


def _make_entry(*, task_name="evaluate_essay", args=None, error="boom", resolved_at=None, age_minutes=0):
    entry = EssayFailedJob.objects.create(
        task_name=task_name, args=args or [], error=error, attempts=3, resolved_at=resolved_at,
    )
    if age_minutes:
        EssayFailedJob.objects.filter(pk=entry.pk).update(created_at=timezone.now() - timedelta(minutes=age_minutes))
        entry.refresh_from_db()
    return entry


@pytest.mark.django_db
class TestDLQList:
    def test_lists_entries_newest_first(self, admin_client):
        e1 = _make_entry(task_name="evaluate_essay", args=["a"])
        e2 = _make_entry(task_name="essays.tasks.generate_essay_report", args=["b"])

        resp = admin_client.get("/api/essay/admin/dlq/")
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.data["results"]]
        assert ids == [str(e2.id), str(e1.id)]

    def test_resolved_true_filters_to_resolved_only(self, admin_client):
        _make_entry(args=["unresolved"])
        resolved = _make_entry(args=["resolved"], resolved_at=timezone.now())

        resp = admin_client.get("/api/essay/admin/dlq/", {"resolved": "true"})
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["id"] == str(resolved.id)

    def test_resolved_false_filters_to_unresolved_only(self, admin_client):
        unresolved = _make_entry(args=["unresolved"])
        _make_entry(args=["resolved"], resolved_at=timezone.now())

        resp = admin_client.get("/api/essay/admin/dlq/", {"resolved": "false"})
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["id"] == str(unresolved.id)

    def test_no_filter_shows_everything(self, admin_client):
        _make_entry(args=["a"])
        _make_entry(args=["b"], resolved_at=timezone.now())

        resp = admin_client.get("/api/essay/admin/dlq/")
        assert len(resp.data["results"]) == 2

    def test_unknown_resolved_filter_rejected(self, admin_client):
        resp = admin_client.get("/api/essay/admin/dlq/", {"resolved": "maybe"})
        assert resp.status_code == 400

    def test_not_scoped_to_institution(self, admin_client):
        # Deliberate: EssayFailedJob has no institution_id of its own —
        # shared platform infrastructure, matching
        # AdminSubmissionsPipelineHealthView's own already-established
        # precedent (Phase 6) and IsAdminOrSuperAdmin's own docstring.
        sub_b = _make_submission(institution_id=INSTITUTION_B)
        _make_entry(args=[str(sub_b.id)])

        resp = admin_client.get("/api/essay/admin/dlq/")
        assert len(resp.data["results"]) == 1

    def test_student_role_rejected(self, student_client):
        resp = student_client.get("/api/essay/admin/dlq/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestDLQDetail:
    def test_exposes_the_full_original_task_payload(self, admin_client):
        entry = _make_entry(
            task_name="evaluate_essay", args=["sub-1"], error="LLM permanent error",
        )
        EssayFailedJob.objects.filter(pk=entry.pk).update(
            kwargs={"inline_retry_count": 2}, traceback="Traceback (most recent call last):\n...",
        )

        resp = admin_client.get(f"/api/essay/admin/dlq/{entry.id}/")
        assert resp.status_code == 200
        data = resp.data["data"]
        assert data["args"] == ["sub-1"]
        assert data["kwargs"] == {"inline_retry_count": 2}
        assert data["error"] == "LLM permanent error"
        assert "Traceback" in data["traceback"]
        assert data["attempts"] == 3

    def test_unknown_entry_404s(self, admin_client):
        resp = admin_client.get(f"/api/essay/admin/dlq/{uuid.uuid4()}/")
        assert resp.status_code == 404

    def test_student_role_rejected(self, student_client):
        entry = _make_entry()
        resp = student_client.get(f"/api/essay/admin/dlq/{entry.id}/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestDLQRetry:
    def test_retry_dispatches_and_resolves_and_logs_a_submission_event(self, admin_client):
        submission = _make_submission()
        entry = _make_entry(task_name="evaluate_essay", args=[str(submission.id)])

        with patch("essays.tasks.retry_dlq_entry") as mock_retry:
            resp = admin_client.post(
                f"/api/essay/admin/dlq/{entry.id}/retry/", {"reason": "root cause fixed"}, format="json",
            )
        assert resp.status_code == 200
        mock_retry.assert_called_once()
        assert mock_retry.call_args[0][0].id == entry.id

        entry.refresh_from_db()
        assert entry.resolved_at is not None

        event = EssaySubmissionEvent.objects.get(submission=submission, event_type=SUBMISSION_EVENT_ADMIN_RETRIGGER)
        assert "root cause fixed" in event.reason

    def test_retry_requires_a_reason(self, admin_client):
        entry = _make_entry()
        resp = admin_client.post(f"/api/essay/admin/dlq/{entry.id}/retry/", {}, format="json")
        assert resp.status_code == 400

    def test_retrying_an_already_resolved_entry_is_a_safe_noop(self, admin_client):
        entry = _make_entry(resolved_at=timezone.now())
        with patch("essays.tasks.retry_dlq_entry") as mock_retry:
            resp = admin_client.post(
                f"/api/essay/admin/dlq/{entry.id}/retry/", {"reason": "x"}, format="json",
            )
        assert resp.status_code == 200
        mock_retry.assert_not_called()

    def test_double_click_only_one_retry_dispatched(self, admin_client):
        # Real race found by this phase's own final-audit round: the
        # first version read entry.resolved_at from an already-fetched
        # object, then dispatched, then separately wrote resolved_at —
        # two concurrent callers (two admins, or an admin racing the
        # automatic sweeper) could both pass that read and both dispatch.
        # Fixed with a conditional UPDATE that claims the entry before
        # dispatch, mirroring AdminSubmissionRetriggerView's own
        # already-tested double-click guard (Phase 7) — proven the same
        # way here: two sequential requests, only the first should
        # actually dispatch.
        entry = _make_entry(task_name="evaluate_essay", args=["sub-1"])

        with patch("essays.tasks.retry_dlq_entry") as mock_retry:
            first = admin_client.post(f"/api/essay/admin/dlq/{entry.id}/retry/", {"reason": "first"}, format="json")
            second = admin_client.post(f"/api/essay/admin/dlq/{entry.id}/retry/", {"reason": "second"}, format="json")

        assert first.status_code == 200
        assert second.status_code == 200
        mock_retry.assert_called_once()

    def test_retry_dispatch_failure_returns_502_and_leaves_entry_unresolved(self, admin_client):
        entry = _make_entry()
        with patch("essays.tasks.retry_dlq_entry", side_effect=RuntimeError("broker down")):
            resp = admin_client.post(
                f"/api/essay/admin/dlq/{entry.id}/retry/", {"reason": "x"}, format="json",
            )
        assert resp.status_code == 502
        entry.refresh_from_db()
        assert entry.resolved_at is None

    def test_unrecognized_task_name_returns_422(self, admin_client):
        entry = _make_entry(task_name="essays.tasks.some_task_removed_long_ago")
        resp = admin_client.post(f"/api/essay/admin/dlq/{entry.id}/retry/", {"reason": "x"}, format="json")
        assert resp.status_code == 422
        entry.refresh_from_db()
        assert entry.resolved_at is None

    def test_generate_essay_report_entry_also_logs_a_submission_event(self, admin_client):
        submission = _make_submission()
        entry = _make_entry(task_name="essays.tasks.generate_essay_report", args=[str(submission.id)])

        with patch("essays.tasks.retry_dlq_entry"):
            admin_client.post(f"/api/essay/admin/dlq/{entry.id}/retry/", {"reason": "x"}, format="json")

        assert EssaySubmissionEvent.objects.filter(
            submission=submission, event_type=SUBMISSION_EVENT_ADMIN_RETRIGGER,
        ).exists()

    def test_send_essay_report_email_entry_also_logs_a_submission_event(self, admin_client):
        # Found missing during Phase 13's audit — same shape as
        # generate_essay_report right above, same fix.
        submission = _make_submission()
        entry = _make_entry(
            task_name="essays.tasks.send_essay_report_email", args=[str(submission.id), "student@example.com"],
        )

        with patch("essays.tasks.retry_dlq_entry"):
            admin_client.post(f"/api/essay/admin/dlq/{entry.id}/retry/", {"reason": "x"}, format="json")

        assert EssaySubmissionEvent.objects.filter(
            submission=submission, event_type=SUBMISSION_EVENT_ADMIN_RETRIGGER,
        ).exists()

    def test_non_submission_scoped_entry_does_not_crash_or_log_an_event(self, admin_client):
        # sweep_expired_assignments takes no args — nothing to attach an
        # event to, and this must not raise.
        entry = _make_entry(task_name="essays.tasks.sweep_expired_assignments", args=[])
        with patch("essays.tasks.retry_dlq_entry") as mock_retry:
            resp = admin_client.post(f"/api/essay/admin/dlq/{entry.id}/retry/", {"reason": "x"}, format="json")
        assert resp.status_code == 200
        mock_retry.assert_called_once()
        assert EssaySubmissionEvent.objects.count() == 0

    def test_student_role_rejected(self, student_client):
        entry = _make_entry()
        resp = student_client.post(f"/api/essay/admin/dlq/{entry.id}/retry/", {"reason": "x"}, format="json")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestRetryDlqEntryFunction:
    """essays.tasks.retry_dlq_entry itself — the generic re-dispatch
    mechanism the view above delegates to."""

    def test_evaluate_essay_replays_with_a_fresh_inline_retry_budget(self):
        entry = _make_entry(task_name="evaluate_essay", args=["sub-1"], resolved_at=None)
        with patch("essays.tasks.evaluate_essay.delay") as mock_delay:
            retry_dlq_entry(entry)
        mock_delay.assert_called_once_with("sub-1")

    def test_generate_essay_report_replays_with_stored_args(self):
        entry = _make_entry(task_name="essays.tasks.generate_essay_report", args=["sub-2"])
        with patch("essays.tasks.generate_essay_report.delay") as mock_delay:
            retry_dlq_entry(entry)
        mock_delay.assert_called_once_with("sub-2")

    def test_send_essay_report_email_replays_with_stored_args(self):
        entry = _make_entry(
            task_name="essays.tasks.send_essay_report_email", args=["sub-3", "student@example.com"],
        )
        with patch("essays.tasks.send_essay_report_email.delay") as mock_delay:
            retry_dlq_entry(entry)
        mock_delay.assert_called_once_with("sub-3", "student@example.com")

    def test_unknown_task_name_raises_value_error(self):
        entry = _make_entry(task_name="essays.tasks.no_such_task")
        with pytest.raises(ValueError):
            retry_dlq_entry(entry)


@pytest.mark.django_db
class TestDLQResolve:
    def test_resolve_happy_path_logs_admin_override_event(self, admin_client):
        submission = _make_submission()
        entry = _make_entry(task_name="evaluate_essay", args=[str(submission.id)])

        resp = admin_client.post(
            f"/api/essay/admin/dlq/{entry.id}/resolve/", {"reason": "handled via manual score override"}, format="json",
        )
        assert resp.status_code == 200
        entry.refresh_from_db()
        assert entry.resolved_at is not None

        event = EssaySubmissionEvent.objects.get(submission=submission, event_type=SUBMISSION_EVENT_ADMIN_OVERRIDE)
        assert "handled via manual score override" in event.reason

    def test_resolve_requires_a_reason(self, admin_client):
        entry = _make_entry()
        resp = admin_client.post(f"/api/essay/admin/dlq/{entry.id}/resolve/", {}, format="json")
        assert resp.status_code == 400

    def test_resolving_an_already_resolved_entry_is_a_safe_noop(self, admin_client):
        entry = _make_entry(resolved_at=timezone.now() - timedelta(hours=1))
        original_resolved_at = entry.resolved_at

        resp = admin_client.post(
            f"/api/essay/admin/dlq/{entry.id}/resolve/", {"reason": "x"}, format="json",
        )
        assert resp.status_code == 200
        entry.refresh_from_db()
        assert entry.resolved_at == original_resolved_at  # untouched, not re-stamped

    def test_double_click_only_one_resolve_logs_an_event(self, admin_client):
        submission = _make_submission()
        entry = _make_entry(task_name="evaluate_essay", args=[str(submission.id)])

        first = admin_client.post(f"/api/essay/admin/dlq/{entry.id}/resolve/", {"reason": "first"}, format="json")
        second = admin_client.post(f"/api/essay/admin/dlq/{entry.id}/resolve/", {"reason": "second"}, format="json")

        assert first.status_code == 200
        assert second.status_code == 200
        assert EssaySubmissionEvent.objects.filter(
            submission=submission, event_type=SUBMISSION_EVENT_ADMIN_OVERRIDE,
        ).count() == 1

    def test_student_role_rejected(self, student_client):
        entry = _make_entry()
        resp = student_client.post(f"/api/essay/admin/dlq/{entry.id}/resolve/", {"reason": "x"}, format="json")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestDLQBulkRetry:
    def test_dry_run_is_the_default_and_retries_nothing(self, admin_client):
        _make_entry(args=["a"])
        _make_entry(args=["b"])

        with patch("essays.tasks.retry_dlq_entry") as mock_retry:
            resp = admin_client.post("/api/essay/admin/dlq/bulk-retry/", {}, format="json")
        assert resp.status_code == 200
        assert resp.data["data"]["dry_run"] is True
        assert resp.data["data"]["would_dispatch_count"] == 2
        mock_retry.assert_not_called()

    def test_dry_run_false_retries_and_resolves_every_matching_entry(self, admin_client):
        e1 = _make_entry(args=["a"])
        e2 = _make_entry(args=["b"])

        with patch("essays.tasks.retry_dlq_entry") as mock_retry:
            resp = admin_client.post(
                "/api/essay/admin/dlq/bulk-retry/", {"dry_run": False, "reason": "root cause fixed"}, format="json",
            )
        assert resp.status_code == 200
        assert resp.data["data"]["dispatched_count"] == 2
        assert mock_retry.call_count == 2
        e1.refresh_from_db()
        e2.refresh_from_db()
        assert e1.resolved_at is not None
        assert e2.resolved_at is not None

    def test_dry_run_false_requires_a_reason(self, admin_client):
        _make_entry(args=["a"])
        resp = admin_client.post("/api/essay/admin/dlq/bulk-retry/", {"dry_run": False}, format="json")
        assert resp.status_code == 400

    def test_only_targets_unresolved_entries(self, admin_client):
        _make_entry(args=["a"], resolved_at=timezone.now())
        unresolved = _make_entry(args=["b"])

        with patch("essays.tasks.retry_dlq_entry") as mock_retry:
            resp = admin_client.post(
                "/api/essay/admin/dlq/bulk-retry/", {"dry_run": False, "reason": "x"}, format="json",
            )
        assert resp.data["data"]["dispatched_count"] == 1
        assert mock_retry.call_args[0][0].id == unresolved.id

    def test_cap_enforced(self, admin_client):
        for i in range(DLQ_BULK_RETRY_CAP + 5):
            _make_entry(args=[str(i)])

        with patch("essays.tasks.retry_dlq_entry") as mock_retry:
            resp = admin_client.post("/api/essay/admin/dlq/bulk-retry/", {}, format="json")
        assert resp.data["data"]["would_dispatch_count"] == DLQ_BULK_RETRY_CAP
        assert resp.data["data"]["total_matching"] == DLQ_BULK_RETRY_CAP + 5
        assert resp.data["data"]["capped"] is True
        mock_retry.assert_not_called()

        with patch("essays.tasks.retry_dlq_entry") as mock_retry:
            resp = admin_client.post(
                "/api/essay/admin/dlq/bulk-retry/", {"dry_run": False, "reason": "x"}, format="json",
            )
        assert resp.data["data"]["dispatched_count"] == DLQ_BULK_RETRY_CAP
        assert mock_retry.call_count == DLQ_BULK_RETRY_CAP

    def test_an_unrecognized_task_name_is_skipped_not_a_batch_failure(self, admin_client):
        good = _make_entry(task_name="evaluate_essay", args=["a"])
        bad = _make_entry(task_name="essays.tasks.no_such_task", args=["b"])

        with patch("essays.tasks.evaluate_essay.delay") as mock_delay:
            resp = admin_client.post(
                "/api/essay/admin/dlq/bulk-retry/", {"dry_run": False, "reason": "x"}, format="json",
            )
        mock_delay.assert_called_once_with("a")
        assert resp.status_code == 200
        assert resp.data["data"]["dispatched_count"] == 1
        good.refresh_from_db()
        bad.refresh_from_db()
        assert good.resolved_at is not None
        assert bad.resolved_at is None

    def test_a_dispatch_failure_for_one_entry_does_not_fail_the_batch(self, admin_client):
        # A second robustness gap found alongside the race-condition fix
        # above: the original loop only caught ValueError (unrecognized
        # task_name) — any OTHER exception (e.g. a broker outage
        # mid-batch) propagated uncaught, 500ing the whole request with
        # no clear response and some entries already claimed but never
        # actually retried. Fixed: any dispatch failure for one entry
        # rolls that one entry back to unresolved and continues the batch.
        good = _make_entry(task_name="evaluate_essay", args=["a"])
        bad = _make_entry(task_name="essays.tasks.generate_essay_report", args=["b"])

        def _side_effect(entry):
            if entry.id == bad.id:
                raise RuntimeError("broker down")

        with patch("essays.tasks.retry_dlq_entry", side_effect=_side_effect) as mock_retry:
            resp = admin_client.post(
                "/api/essay/admin/dlq/bulk-retry/", {"dry_run": False, "reason": "x"}, format="json",
            )
        assert resp.status_code == 200
        assert resp.data["data"]["dispatched_count"] == 1
        assert mock_retry.call_count == 2
        good.refresh_from_db()
        bad.refresh_from_db()
        assert good.resolved_at is not None
        assert bad.resolved_at is None

    def test_student_role_rejected(self, student_client):
        resp = student_client.post("/api/essay/admin/dlq/bulk-retry/", {}, format="json")
        assert resp.status_code == 403
