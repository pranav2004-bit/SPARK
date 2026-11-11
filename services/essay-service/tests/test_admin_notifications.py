"""
test_admin_notifications.py — Phase 13's own testing checklist (Task
13.1): threshold-boundary tests (exactly at, just above, just below each
tier's cutoff), summary accuracy against a known fixture, no false P1s
under a normal/healthy pipeline state.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.test import override_settings
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt, EssaySubmission, EssayFailedJob,
    EssaySubmissionEvent,
    SUBMISSION_STATUS_PENDING, SUBMISSION_STATUS_LLM_PROCESSING, SUBMISSION_STATUS_LLM_COMPLETE,
    SUBMISSION_STATUS_LLM_FAILED, SUBMISSION_STATUS_REPORT_READY,
    SUBMISSION_EVENT_DLQ_RECORDED, SUBMISSION_EVENT_EMAIL_BOUNCED, SUBMISSION_EVENT_STATUS_CHANGE,
)
from essays.notifications import (
    compute_pipeline_health_summary, generate_pipeline_alerts, ALERT_TIER_P1, ALERT_TIER_P2,
)
from essays.tasks import send_pipeline_health_summary_email

from .conftest import INSTITUTION_A, ADMIN_USER_ID


def _make_assignment():
    paper = EssayPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
    assignment = EssayAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
    )
    return assignment, eset


def _make_submission(assignment, eset, *, status=SUBMISSION_STATUS_PENDING, age_hours=0):
    attempt = EssayAttempt.objects.create(
        assignment=assignment, student_id=uuid.uuid4(), set=eset,
        ends_at=timezone.now() + timedelta(hours=1), draft_response="x",
    )
    submission = EssaySubmission.objects.create(attempt=attempt)
    EssaySubmission.objects.filter(pk=submission.pk).update(
        status=status, created_at=timezone.now() - timedelta(hours=age_hours),
    )
    submission.refresh_from_db()
    return submission


def _make_event(submission, event_type, *, age_hours=0):
    event = EssaySubmissionEvent.objects.create(submission=submission, event_type=event_type, detail="x")
    EssaySubmissionEvent.objects.filter(pk=event.pk).update(occurred_at=timezone.now() - timedelta(hours=age_hours))
    return event


def _make_dlq_entry(*, age_minutes=0, resolved_at=None):
    entry = EssayFailedJob.objects.create(task_name="evaluate_essay", args=["sub-1"], error="x", attempts=3, resolved_at=resolved_at)
    EssayFailedJob.objects.filter(pk=entry.pk).update(created_at=timezone.now() - timedelta(minutes=age_minutes))
    entry.refresh_from_db()
    return entry


@pytest.mark.django_db
class TestComputePipelineHealthSummary:
    def test_counts_match_a_known_fixture_within_the_window(self):
        assignment, eset = _make_assignment()
        _make_submission(assignment, eset, status=SUBMISSION_STATUS_PENDING, age_hours=1)
        _make_submission(assignment, eset, status=SUBMISSION_STATUS_LLM_COMPLETE, age_hours=2)
        _make_submission(assignment, eset, status=SUBMISSION_STATUS_REPORT_READY, age_hours=3)
        _make_submission(assignment, eset, status=SUBMISSION_STATUS_LLM_FAILED, age_hours=4)
        # Outside the 24h window — must not be counted.
        _make_submission(assignment, eset, status=SUBMISSION_STATUS_LLM_COMPLETE, age_hours=48)

        summary = compute_pipeline_health_summary(window_hours=24)
        assert summary["total_submissions"] == 4
        assert summary["completed_submissions"] == 2  # LLM_COMPLETE + REPORT_READY
        assert summary["failed_submissions"] == 1

    def test_window_hours_actually_narrows_the_count(self):
        assignment, eset = _make_assignment()
        _make_submission(assignment, eset, status=SUBMISSION_STATUS_LLM_COMPLETE, age_hours=10)
        _make_submission(assignment, eset, status=SUBMISSION_STATUS_LLM_COMPLETE, age_hours=30)

        assert compute_pipeline_health_summary(window_hours=24)["total_submissions"] == 1
        assert compute_pipeline_health_summary(window_hours=48)["total_submissions"] == 2

    def test_unresolved_dlq_count_and_oldest_age(self):
        _make_dlq_entry(age_minutes=10)
        _make_dlq_entry(age_minutes=90)
        _make_dlq_entry(age_minutes=5, resolved_at=timezone.now())  # resolved — excluded

        summary = compute_pipeline_health_summary(window_hours=24)
        assert summary["unresolved_dlq_count"] == 2
        assert summary["oldest_unresolved_dlq_age_seconds"] >= 89 * 60

    def test_recent_failure_events_counts_only_failure_shaped_types_in_window(self):
        assignment, eset = _make_assignment()
        submission = _make_submission(assignment, eset)
        _make_event(submission, SUBMISSION_EVENT_DLQ_RECORDED, age_hours=1)
        _make_event(submission, SUBMISSION_EVENT_EMAIL_BOUNCED, age_hours=2)
        # Not failure-shaped — must not be counted.
        _make_event(submission, SUBMISSION_EVENT_STATUS_CHANGE, age_hours=1)
        # Failure-shaped but outside the window — must not be counted.
        _make_event(submission, SUBMISSION_EVENT_DLQ_RECORDED, age_hours=48)

        summary = compute_pipeline_health_summary(window_hours=24)
        assert summary["recent_failure_event_count"] == 2
        assert len(summary["recent_failure_events"]) == 2

    def test_empty_pipeline_reports_zeros_not_errors(self):
        summary = compute_pipeline_health_summary(window_hours=24)
        assert summary["total_submissions"] == 0
        assert summary["unresolved_dlq_count"] == 0
        assert summary["oldest_unresolved_dlq_age_seconds"] is None
        assert summary["undispatched_submission_count"] == 0
        assert summary["oldest_undispatched_submission_age_seconds"] is None
        assert summary["recent_failure_event_count"] == 0

    def test_undispatched_submission_count_and_oldest_age(self):
        assignment, eset = _make_assignment()
        # Genuinely stuck — past the 2-minute grace period.
        _make_submission(assignment, eset, status=SUBMISSION_STATUS_PENDING, age_hours=1)
        # Normal, healthy in-flight case — must NOT count as stuck.
        submission = EssaySubmission.objects.create(
            attempt=EssayAttempt.objects.create(
                assignment=assignment, student_id=uuid.uuid4(), set=eset,
                ends_at=timezone.now() + timedelta(hours=1), draft_response="x",
            ),
        )

        summary = compute_pipeline_health_summary(window_hours=24)
        assert summary["undispatched_submission_count"] == 1
        assert summary["oldest_undispatched_submission_age_seconds"] >= 3500


@pytest.mark.django_db
class TestGeneratePipelineAlerts:
    def _summary(self, **overrides):
        base = {
            "window_hours": 24, "generated_at": timezone.now().isoformat(),
            "total_submissions": 0, "completed_submissions": 0, "failed_submissions": 0,
            "unresolved_dlq_count": 0, "oldest_unresolved_dlq_age_seconds": None,
            "undispatched_submission_count": 0, "oldest_undispatched_submission_age_seconds": None,
            "recent_failure_event_count": 0, "recent_failure_events": [],
        }
        base.update(overrides)
        return base

    def test_healthy_pipeline_produces_no_alerts(self):
        # No false P1s (or P2s) under a normal/healthy state — Task
        # 13.1's own explicit testing requirement.
        assert generate_pipeline_alerts(self._summary()) == []

    def test_dlq_count_exactly_at_p2_threshold_is_not_an_alert(self):
        assert generate_pipeline_alerts(self._summary(unresolved_dlq_count=5)) == []

    def test_dlq_count_just_above_p2_threshold_is_a_p2_alert(self):
        alerts = generate_pipeline_alerts(self._summary(unresolved_dlq_count=6))
        assert len(alerts) == 1
        assert alerts[0]["tier"] == ALERT_TIER_P2
        assert alerts[0]["metric"] == "dlq_unresolved_count"

    def test_dlq_count_exactly_at_p1_threshold_is_still_only_p2(self):
        alerts = generate_pipeline_alerts(self._summary(unresolved_dlq_count=25))
        assert len(alerts) == 1
        assert alerts[0]["tier"] == ALERT_TIER_P2

    def test_dlq_count_just_above_p1_threshold_is_a_p1_alert_not_both(self):
        alerts = generate_pipeline_alerts(self._summary(unresolved_dlq_count=26))
        assert len(alerts) == 1  # only the higher tier, never both
        assert alerts[0]["tier"] == ALERT_TIER_P1

    def test_oldest_age_boundaries(self):
        assert generate_pipeline_alerts(self._summary(oldest_unresolved_dlq_age_seconds=45 * 60)) == []
        p2 = generate_pipeline_alerts(self._summary(oldest_unresolved_dlq_age_seconds=46 * 60))
        assert len(p2) == 1 and p2[0]["tier"] == ALERT_TIER_P2
        still_p2 = generate_pipeline_alerts(self._summary(oldest_unresolved_dlq_age_seconds=180 * 60))
        assert len(still_p2) == 1 and still_p2[0]["tier"] == ALERT_TIER_P2
        p1 = generate_pipeline_alerts(self._summary(oldest_unresolved_dlq_age_seconds=181 * 60))
        assert len(p1) == 1 and p1[0]["tier"] == ALERT_TIER_P1

    def test_failure_event_boundaries(self):
        assert generate_pipeline_alerts(self._summary(recent_failure_event_count=15)) == []
        alerts = generate_pipeline_alerts(self._summary(recent_failure_event_count=16))
        assert len(alerts) == 1
        assert alerts[0]["tier"] == ALERT_TIER_P2
        assert alerts[0]["metric"] == "recent_failure_events"

    def test_multiple_breached_metrics_each_produce_their_own_alert(self):
        alerts = generate_pipeline_alerts(self._summary(
            unresolved_dlq_count=30, oldest_unresolved_dlq_age_seconds=200 * 60, recent_failure_event_count=20,
        ))
        assert {a["metric"] for a in alerts} == {"dlq_unresolved_count", "dlq_oldest_unresolved_age", "recent_failure_events"}
        assert {a["tier"] for a in alerts} == {ALERT_TIER_P1, ALERT_TIER_P2}

    def test_undispatched_submission_age_boundaries(self):
        # Real gap found and fixed this round: generate_pipeline_alerts()
        # only ever checked DLQ/failure-event metrics, never this one.
        assert generate_pipeline_alerts(self._summary(oldest_undispatched_submission_age_seconds=10 * 60)) == []
        p2 = generate_pipeline_alerts(self._summary(oldest_undispatched_submission_age_seconds=11 * 60))
        assert len(p2) == 1 and p2[0]["tier"] == ALERT_TIER_P2 and p2[0]["metric"] == "undispatched_submission_oldest_age"
        still_p2 = generate_pipeline_alerts(self._summary(oldest_undispatched_submission_age_seconds=30 * 60))
        assert len(still_p2) == 1 and still_p2[0]["tier"] == ALERT_TIER_P2
        p1 = generate_pipeline_alerts(self._summary(oldest_undispatched_submission_age_seconds=31 * 60))
        assert len(p1) == 1 and p1[0]["tier"] == ALERT_TIER_P1

    def test_undispatched_submission_count_alone_never_alerts(self):
        # Deliberate design choice, not an oversight: a large count is
        # EXPECTED during a mass-simultaneous exam expiry overlapping a
        # brief outage (the round-2 circuit-breaker fix made this safe and
        # bounded) and self-drains within minutes — alerting on count
        # alone would false-alarm for exactly that expected case. Only
        # age (checked above) indicates a genuinely ongoing problem.
        assert generate_pipeline_alerts(self._summary(undispatched_submission_count=5000)) == []


@pytest.mark.django_db
class TestPipelineHealthSummaryView:
    def test_returns_summary_and_alerts(self, admin_client):
        _make_dlq_entry(age_minutes=10)
        resp = admin_client.get("/api/essay/admin/notifications/summary/")
        assert resp.status_code == 200
        data = resp.data["data"]
        assert data["unresolved_dlq_count"] == 1
        assert "alerts" in data

    def test_default_window_is_used_when_omitted(self, admin_client):
        resp = admin_client.get("/api/essay/admin/notifications/summary/")
        assert resp.data["data"]["window_hours"] == 24

    def test_custom_window_hours_respected(self, admin_client):
        resp = admin_client.get("/api/essay/admin/notifications/summary/", {"window_hours": "48"})
        assert resp.data["data"]["window_hours"] == 48

    def test_non_integer_window_hours_rejected(self, admin_client):
        resp = admin_client.get("/api/essay/admin/notifications/summary/", {"window_hours": "not-a-number"})
        assert resp.status_code == 400

    def test_zero_or_negative_window_hours_rejected(self, admin_client):
        resp = admin_client.get("/api/essay/admin/notifications/summary/", {"window_hours": "0"})
        assert resp.status_code == 400
        resp = admin_client.get("/api/essay/admin/notifications/summary/", {"window_hours": "-5"})
        assert resp.status_code == 400

    def test_excessively_large_window_hours_rejected_not_a_raw_500(self, admin_client):
        # Below PIPELINE_SUMMARY_MAX_WINDOW_HOURS's own int32-hours ceiling
        # a value this large reaches datetime.timedelta(hours=...) uncaught
        # and raises OverflowError — confirms the clean-400 path is hit
        # before that, not just that some 400 happens to come back.
        resp = admin_client.get("/api/essay/admin/notifications/summary/", {"window_hours": "10000000000000"})
        assert resp.status_code == 400
        assert "window_hours" in resp.data["message"]

    def test_window_hours_at_the_max_boundary_still_accepted(self, admin_client):
        from django.conf import settings
        resp = admin_client.get(
            "/api/essay/admin/notifications/summary/",
            {"window_hours": str(settings.PIPELINE_SUMMARY_MAX_WINDOW_HOURS)},
        )
        assert resp.status_code == 200

    def test_student_role_rejected(self, student_client):
        resp = student_client.get("/api/essay/admin/notifications/summary/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestSendDailySummaryView:
    def test_rejected_when_no_recipients_configured(self, admin_client):
        with override_settings(ALERT_EMAIL_RECIPIENTS=[]):
            resp = admin_client.post("/api/essay/admin/notifications/send-summary/")
        assert resp.status_code == 409

    def test_dispatches_when_recipients_configured(self, admin_client):
        with override_settings(ALERT_EMAIL_RECIPIENTS=["ops@example.com"]):
            with patch("essays.tasks.send_pipeline_health_summary_email.delay") as mock_delay:
                resp = admin_client.post("/api/essay/admin/notifications/send-summary/")
        assert resp.status_code == 200
        mock_delay.assert_called_once()

    def test_student_role_rejected(self, student_client):
        resp = student_client.post("/api/essay/admin/notifications/send-summary/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestSendPipelineHealthSummaryEmailTask:
    def test_noops_when_no_recipients_configured(self):
        with override_settings(ALERT_EMAIL_RECIPIENTS=[]):
            result = send_pipeline_health_summary_email.apply().result
        assert result["status"] == "skipped"
        assert len(mail.outbox) == 0

    def test_sends_to_configured_recipients_with_correct_tier_in_subject(self):
        _make_dlq_entry(age_minutes=200)  # breaches the P1 age threshold
        with override_settings(ALERT_EMAIL_RECIPIENTS=["ops@example.com", "cto@example.com"]):
            result = send_pipeline_health_summary_email.apply().result
        assert result["status"] == "ok"
        assert len(mail.outbox) == 1
        assert set(mail.outbox[0].to) == {"ops@example.com", "cto@example.com"}
        assert "P1" in mail.outbox[0].subject

    def test_healthy_pipeline_sends_an_ok_email_not_an_error(self):
        with override_settings(ALERT_EMAIL_RECIPIENTS=["ops@example.com"]):
            result = send_pipeline_health_summary_email.apply().result
        assert result["status"] == "ok"
        assert result["alert_count"] == 0
        assert "OK" in mail.outbox[0].subject

    def test_manual_trigger_and_automatic_task_are_the_same_code_path(self, admin_client):
        # AdminSendDailySummaryView dispatches this exact task rather than
        # duplicating its own send logic — proven here by actually
        # running it end-to-end via the real view.
        with override_settings(ALERT_EMAIL_RECIPIENTS=["ops@example.com"]):
            resp = admin_client.post("/api/essay/admin/notifications/send-summary/")
        assert resp.status_code == 200
        assert len(mail.outbox) == 1
