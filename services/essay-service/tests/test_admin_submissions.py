"""
test_admin_submissions.py — Phase 6, Task 6.1's own testing checklist:
filtering correctness, institution isolation (ET8), pagination at
realistic volume, and health-widget accuracy against real Redis/Celery
state (mocked here per this project's own established convention —
test_quota_tracker.py's own docstring — rather than a real Redis/Celery
connection).
"""
import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt, EssaySubmission, EssayScore,
    EssayFailedJob, ATTEMPT_STATUS_SUBMITTED,
    SUBMISSION_STATUS_PENDING, SUBMISSION_STATUS_LLM_PROCESSING,
    SUBMISSION_STATUS_LLM_COMPLETE, SUBMISSION_STATUS_LLM_FAILED,
    SUBMISSION_STATUS_REPORT_GENERATING, SUBMISSION_STATUS_REPORT_READY,
)
from essays.tasks import _transition_submission_status, _record_dlq

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


def _make_submission(
    *, institution_id=INSTITUTION_A, batch_id=None, student_id=None,
    status=SUBMISSION_STATUS_PENDING, draft_response="An essay response about history.",
):
    paper = EssayPaper.objects.create(institution_id=institution_id, title="P", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
    assignment = EssayAssignment.objects.create(
        paper=paper, batch_id=batch_id or uuid.uuid4(), institution_id=institution_id,
        global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
    )
    attempt = EssayAttempt.objects.create(
        assignment=assignment, student_id=student_id or uuid.uuid4(), set=eset,
        ends_at=timezone.now() + timedelta(hours=1), draft_response=draft_response,
        status=ATTEMPT_STATUS_SUBMITTED,
    )
    submission = EssaySubmission.objects.create(attempt=attempt)
    if status != SUBMISSION_STATUS_PENDING:
        EssaySubmission.objects.filter(pk=submission.pk).update(status=status)
        submission.refresh_from_db()
    return submission


@pytest.mark.django_db
class TestOverview:
    def test_counts_bucketed_correctly(self, admin_client):
        _make_submission(status=SUBMISSION_STATUS_PENDING)
        _make_submission(status=SUBMISSION_STATUS_LLM_PROCESSING)
        # Phase 11's own final-audit round: REPORT_GENERATING must roll up
        # into "processing" (matching CLAP's own reference, which
        # collapses LLM_PROCESSING + REPORT_GENERATING + EMAIL_SENDING
        # into "processing" too) — the fix itself (essays/views.py's own
        # _SUBMISSION_STATUS_BUCKETS) predates this test; this is a real
        # gap this audit round found: nothing had actually exercised it
        # end-to-end through the real API before now. Without the fix, a
        # submission in this state matched no bucket at all and silently
        # vanished from "total" too.
        _make_submission(status=SUBMISSION_STATUS_REPORT_GENERATING)
        _make_submission(status=SUBMISSION_STATUS_LLM_COMPLETE)
        _make_submission(status=SUBMISSION_STATUS_REPORT_READY)
        _make_submission(status=SUBMISSION_STATUS_LLM_FAILED)

        resp = admin_client.get("/api/essay/admin/submissions/overview/")
        assert resp.status_code == 200
        data = resp.data["data"]
        assert data["pending"] == 1
        assert data["processing"] == 2  # LLM_PROCESSING + REPORT_GENERATING rolled up
        assert data["completed"] == 2  # LLM_COMPLETE + REPORT_READY rolled up
        assert data["failed"] == 1
        assert data["total"] == 6

    def test_institution_isolated(self, admin_client, admin_b_client):
        _make_submission(status=SUBMISSION_STATUS_PENDING)
        resp = admin_b_client.get("/api/essay/admin/submissions/overview/")
        assert resp.data["data"]["total"] == 0


@pytest.mark.django_db
class TestList:
    def test_filters_by_status_bucket(self, admin_client):
        _make_submission(status=SUBMISSION_STATUS_PENDING)
        _make_submission(status=SUBMISSION_STATUS_LLM_FAILED)

        resp = admin_client.get("/api/essay/admin/submissions/", {"status": "failed"})
        assert resp.status_code == 200
        results = resp.data["results"]
        assert len(results) == 1
        assert results[0]["status"] == SUBMISSION_STATUS_LLM_FAILED

    def test_unknown_status_bucket_rejected(self, admin_client):
        resp = admin_client.get("/api/essay/admin/submissions/", {"status": "not_a_bucket"})
        assert resp.status_code == 400

    def test_filters_by_student_id(self, admin_client):
        target = _make_submission(student_id=STUDENT_USER_ID)
        _make_submission()

        resp = admin_client.get("/api/essay/admin/submissions/", {"student_id": str(STUDENT_USER_ID)})
        results = resp.data["results"]
        assert len(results) == 1
        assert results[0]["id"] == str(target.id)

    def test_malformed_student_id_rejected(self, admin_client):
        resp = admin_client.get("/api/essay/admin/submissions/", {"student_id": "not-a-uuid"})
        assert resp.status_code == 400

    def test_filters_by_batch_id(self, admin_client):
        batch = uuid.uuid4()
        target = _make_submission(batch_id=batch)
        _make_submission()

        resp = admin_client.get("/api/essay/admin/submissions/", {"batch_id": str(batch)})
        results = resp.data["results"]
        assert len(results) == 1
        assert results[0]["id"] == str(target.id)

    def test_filters_by_date_range(self, admin_client):
        submission = _make_submission()
        today = timezone.now().date().isoformat()
        tomorrow = (timezone.now() + timedelta(days=1)).date().isoformat()
        yesterday = (timezone.now() - timedelta(days=1)).date().isoformat()

        in_range = admin_client.get("/api/essay/admin/submissions/", {"date_from": today, "date_to": tomorrow})
        assert len(in_range.data["results"]) == 1

        out_of_range = admin_client.get("/api/essay/admin/submissions/", {"date_from": yesterday, "date_to": yesterday})
        assert len(out_of_range.data["results"]) == 0

    def test_malformed_date_from_rejected_not_500(self, admin_client):
        # Real bug found by this phase's own final-audit round: unlike
        # student_id/batch_id, a malformed date string doesn't raise at
        # .filter() call time — Django defers a date-lookup's value
        # validation to query evaluation (inside paginate_queryset()),
        # which crashed this endpoint with a raw 500 before this was fixed.
        resp = admin_client.get("/api/essay/admin/submissions/", {"date_from": "not-a-date"})
        assert resp.status_code == 400

    def test_malformed_date_to_rejected_not_500(self, admin_client):
        resp = admin_client.get("/api/essay/admin/submissions/", {"date_to": "also-not-a-date"})
        assert resp.status_code == 400

    def test_pagination_defaults_to_30_per_page(self, admin_client):
        for _ in range(35):
            _make_submission()

        resp = admin_client.get("/api/essay/admin/submissions/")
        data = resp.data
        assert data["count"] == 35
        assert len(data["results"]) == 30
        assert data["next"] is not None

    def test_institution_isolated(self, admin_client, admin_b_client):
        _make_submission()
        resp = admin_b_client.get("/api/essay/admin/submissions/")
        assert resp.data["count"] == 0

    def test_score_included_when_scored(self, admin_client):
        submission = _make_submission(status=SUBMISSION_STATUS_LLM_COMPLETE)
        EssayScore.objects.create(submission=submission, score=8, feedback={"overall": "Good."})

        resp = admin_client.get("/api/essay/admin/submissions/")
        results = resp.data["results"]
        assert results[0]["score"] == 8

    def test_department_filter_degrades_gracefully_on_roster_failure(self, admin_client):
        _make_submission()
        with patch("essays.views.fetch_batch_roster", side_effect=RuntimeError("user-service unreachable")):
            resp = admin_client.get("/api/essay/admin/submissions/", {"department": "CSE"})
        # Roster fetch failed for the one batch involved — degrades to "no
        # match" for that batch rather than a 500, matching this view's own
        # documented best-effort reasoning.
        assert resp.status_code == 200
        assert resp.data["count"] == 0

    def test_department_filter_matches_roster(self, admin_client):
        batch = uuid.uuid4()
        target = _make_submission(batch_id=batch, student_id=STUDENT_USER_ID)
        with patch("essays.views.fetch_batch_roster", return_value=[
            {"user_id": str(STUDENT_USER_ID), "student_id": "R001", "department": "CSE"},
        ]):
            resp = admin_client.get("/api/essay/admin/submissions/", {"department": "cse"})
        results = resp.data["results"]
        assert len(results) == 1
        assert results[0]["id"] == str(target.id)


@pytest.mark.django_db
class TestDetail:
    def test_detail_shape(self, admin_client):
        submission = _make_submission()  # starts PENDING, so the CAS below actually fires
        _transition_submission_status(submission, SUBMISSION_STATUS_LLM_PROCESSING, expected_status=SUBMISSION_STATUS_PENDING)
        _transition_submission_status(submission, SUBMISSION_STATUS_LLM_COMPLETE, expected_status=SUBMISSION_STATUS_LLM_PROCESSING)
        EssayScore.objects.create(submission=submission, score=7, feedback={"overall": "Solid effort."})

        resp = admin_client.get(f"/api/essay/admin/submissions/{submission.id}/")
        assert resp.status_code == 200
        data = resp.data["data"]
        assert data["id"] == str(submission.id)
        assert data["draft_response"] == "An essay response about history."
        assert data["score"] == 7
        assert data["feedback"]["overall"] == "Solid effort."
        assert isinstance(data["events"], list)
        assert len(data["events"]) >= 1

    def test_events_trail_captures_dlq_write(self, admin_client):
        submission = _make_submission()
        _record_dlq("evaluate_essay", [str(submission.id)], {}, RuntimeError("provider rejected"), attempts=3)

        resp = admin_client.get(f"/api/essay/admin/submissions/{submission.id}/")
        events = resp.data["data"]["events"]
        assert any("provider rejected" in e["detail"] for e in events)

    def test_institution_isolated_404(self, admin_client, admin_b_client):
        submission = _make_submission()
        resp = admin_b_client.get(f"/api/essay/admin/submissions/{submission.id}/")
        assert resp.status_code == 404

    def test_unauthenticated_rejected(self, anon_client):
        submission_id = uuid.uuid4()
        resp = anon_client.get(f"/api/essay/admin/submissions/{submission_id}/")
        assert resp.status_code in (401, 403)


@pytest.mark.django_db
class TestPermissions:
    """Real, previously-untested gap found by this phase's own second
    final-audit round: every sibling admin view test file in this service
    (e.g. test_admin_papers.py) pairs `test_unauthenticated_rejected` with
    `test_student_role_rejected` for each endpoint — this file only ever
    covered the unauthenticated case, and only on the detail view. Manually
    verified live first (a real student JWT and a bare, unauthenticated
    request against all four endpoints through the real gateway, all
    correctly rejected) before locking it in here, matching this session's
    own "verify before reporting" discipline — not a bug, IsAdminOrSuperAdmin
    is shared, already-proven-correct code, but the coverage gap itself was
    real."""

    def test_overview_rejects_student_and_anon(self, student_client, anon_client):
        assert student_client.get("/api/essay/admin/submissions/overview/").status_code == 403
        assert anon_client.get("/api/essay/admin/submissions/overview/").status_code in (401, 403)

    def test_list_rejects_student_and_anon(self, student_client, anon_client):
        assert student_client.get("/api/essay/admin/submissions/").status_code == 403
        assert anon_client.get("/api/essay/admin/submissions/").status_code in (401, 403)

    def test_detail_rejects_student(self, student_client):
        submission = _make_submission()
        resp = student_client.get(f"/api/essay/admin/submissions/{submission.id}/")
        assert resp.status_code == 403

    def test_pipeline_health_rejects_student_and_anon(self, student_client, anon_client):
        assert student_client.get("/api/essay/admin/submissions/pipeline-health/").status_code == 403
        assert anon_client.get("/api/essay/admin/submissions/pipeline-health/").status_code in (401, 403)


@pytest.mark.django_db
class TestPipelineHealth:
    def test_reports_dlq_backlog_and_oldest_age(self, admin_client):
        submission = _make_submission()
        _record_dlq("evaluate_essay", [str(submission.id)], {}, RuntimeError("x"), attempts=3)
        EssayFailedJob.objects.filter(task_name="evaluate_essay").update(
            created_at=timezone.now() - timedelta(minutes=15),
        )

        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.llen.return_value = 4
        with patch("redis.from_url", return_value=mock_redis_instance), \
             patch("core.celery.app.control.ping", return_value=[{"worker@host": "pong"}]):
            resp = admin_client.get("/api/essay/admin/submissions/pipeline-health/")

        assert resp.status_code == 200
        data = resp.data["data"]
        assert data["redis_ok"] is True
        assert data["queue_depth"] == 4
        assert data["celery_workers_online"] == 1
        assert data["unresolved_dlq_count"] == 1
        assert data["oldest_unresolved_dlq_age_seconds"] >= 900

    def test_reports_undispatched_submissions_and_oldest_age(self, admin_client):
        # Real gap found auditing this view: a submission whose dispatch
        # never even reached the broker (e.g. Redis unreachable at the
        # exact moment of submit) never gets an EssayFailedJob row either
        # (only evaluate_essay's own exception handling writes one) — a
        # genuinely different failure mode from the DLQ backlog above,
        # invisible in this tile until this fix.
        stuck = _make_submission(status=SUBMISSION_STATUS_PENDING)
        EssaySubmission.objects.filter(pk=stuck.pk).update(
            created_at=timezone.now() - timedelta(minutes=10),
        )
        # A submission still well within the grace period must NOT count
        # as "stuck" — it's just normally waiting for a worker to pick it
        # up, the ordinary case, not an incident.
        _make_submission(status=SUBMISSION_STATUS_PENDING)

        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.llen.return_value = 0
        with patch("redis.from_url", return_value=mock_redis_instance), \
             patch("core.celery.app.control.ping", return_value=[{"worker@host": "pong"}]):
            resp = admin_client.get("/api/essay/admin/submissions/pipeline-health/")

        assert resp.status_code == 200
        data = resp.data["data"]
        assert data["undispatched_submission_count"] == 1
        assert data["oldest_undispatched_submission_age_seconds"] >= 600

    def test_degrades_gracefully_on_redis_outage(self, admin_client):
        import redis as redis_module
        with patch("redis.from_url", side_effect=redis_module.exceptions.RedisError("down")), \
             patch("core.celery.app.control.ping", return_value=[]):
            resp = admin_client.get("/api/essay/admin/submissions/pipeline-health/")

        assert resp.status_code == 200
        data = resp.data["data"]
        assert data["redis_ok"] is False
        assert data["queue_depth"] is None
        assert data["celery_workers_online"] == 0

    def test_reports_zero_workers_when_none_respond(self, admin_client):
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.llen.return_value = 0
        with patch("redis.from_url", return_value=mock_redis_instance), \
             patch("core.celery.app.control.ping", return_value=[]):
            resp = admin_client.get("/api/essay/admin/submissions/pipeline-health/")
        assert resp.data["data"]["celery_workers_online"] == 0

    def test_not_institution_scoped_but_still_requires_admin(self, admin_b_client):
        # Platform-wide infra health, gated behind admin auth only (see
        # AdminSubmissionsPipelineHealthView's own docstring for why this
        # one deliberately isn't per-institution) — a DIFFERENT
        # institution's admin still gets a 200, not a 403/404.
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.llen.return_value = 0
        with patch("redis.from_url", return_value=mock_redis_instance), \
             patch("core.celery.app.control.ping", return_value=[]):
            resp = admin_b_client.get("/api/essay/admin/submissions/pipeline-health/")
        assert resp.status_code == 200
