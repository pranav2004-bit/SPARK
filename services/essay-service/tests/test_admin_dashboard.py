"""
test_admin_dashboard.py — Phase 10, Task 10.1's own testing checklist:
"same cache/invalidation rigor as Task 9.1" — but Task 10's own Dashboard
genuinely uses explicit invalidation for real (unlike Phase 9's Analytics,
corrected to a plain TTL against the verified reference — see
AdminEssayAssignmentDashboardView's own module-header comment in
essays/views.py), so this file's own caching tests prove invalidation
actually fires from every one of the eleven write paths that can change a
dashboard KPI, plus hand-computed fixture verification and cross-
institution isolation.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayStudentSetAllocation, EssayAttempt,
    EssaySubmission, EssayScore, EssayFailedJob,
    ATTEMPT_STATUS_SUBMITTED, ATTEMPT_STATUS_IN_PROGRESS,
    SUBMISSION_STATUS_PENDING, SUBMISSION_STATUS_LLM_PROCESSING,
    SUBMISSION_STATUS_LLM_COMPLETE, SUBMISSION_STATUS_LLM_FAILED,
    ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_SCHEDULED, ASSIGNMENT_STATUS_CLOSED,
)
from essays.tasks import _transition_submission_status, _record_dlq, sweep_dlq_entries, DLQ_RETRY_CEILING

from essays.scoring import finalize_attempts

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


def _make_assignment(*, institution_id=INSTITUTION_A, status=ASSIGNMENT_STATUS_LIVE,
                       global_expire_time=None):
    paper = EssayPaper.objects.create(institution_id=institution_id, title="Dashboard Test Paper", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
    assignment = EssayAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=institution_id,
        global_expire_time=global_expire_time or timezone.now() + timedelta(hours=3),
        created_by=ADMIN_USER_ID, status=status,
    )
    return assignment, eset


def _allocate(assignment, eset, student_id=None):
    return EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=student_id or uuid.uuid4(), set=eset)


def _attempt(assignment, eset, student_id, *, status=ATTEMPT_STATUS_SUBMITTED):
    return EssayAttempt.objects.create(
        assignment=assignment, student_id=student_id, set=eset,
        ends_at=timezone.now() + timedelta(hours=1), status=status,
    )


def _submission(attempt, *, status=SUBMISSION_STATUS_PENDING):
    submission = EssaySubmission.objects.create(attempt=attempt)
    if status != SUBMISSION_STATUS_PENDING:
        EssaySubmission.objects.filter(pk=submission.pk).update(status=status)
        submission.refresh_from_db()
    return submission


def _scored_submission(assignment, eset, *, score=8, submission_status=SUBMISSION_STATUS_LLM_COMPLETE):
    student_id = uuid.uuid4()
    _allocate(assignment, eset, student_id)
    attempt = _attempt(assignment, eset, student_id)
    submission = _submission(attempt, status=submission_status)
    if score is not None:
        EssayScore.objects.create(submission=submission, score=score, feedback={"overall": "x"})
    return student_id, attempt, submission


@pytest.mark.django_db
class TestDashboardHandComputedFixture:
    def test_numbers_match_a_known_fixture(self, admin_client):
        assignment, eset = _make_assignment()
        # 2 not started, 1 in progress, 1 pending evaluation, 2 scored
        _allocate(assignment, eset)
        _allocate(assignment, eset)
        student_id = uuid.uuid4()
        _allocate(assignment, eset, student_id)
        _attempt(assignment, eset, student_id, status=ATTEMPT_STATUS_IN_PROGRESS)
        _scored_submission(assignment, eset, score=None, submission_status=SUBMISSION_STATUS_LLM_PROCESSING)
        _scored_submission(assignment, eset, score=6)
        _scored_submission(assignment, eset, score=10)

        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert resp.status_code == 200
        data = resp.data["data"]

        assert data["total_allocated"] == 6
        assert data["in_progress_count"] == 1
        assert data["total_submitted"] == 3  # the pending-evaluation one + the 2 scored ones
        assert data["completion_rate_percentage"] == 50.0  # 3 of 6
        assert data["total_scored"] == 2
        assert data["average_score"] == 8.0  # (6 + 10) / 2
        assert data["pending_evaluation_count"] == 1

    def test_dlq_backlog_scoped_to_this_assignment_only(self, admin_client):
        # A deliberately different question from Phase 6's own platform-
        # wide AdminSubmissionsPipelineHealthView: a DLQ entry for a
        # DIFFERENT assignment must never inflate THIS one's own backlog
        # count.
        assignment1, eset1 = _make_assignment()
        assignment2, eset2 = _make_assignment()
        _, _, sub1 = _scored_submission(assignment1, eset1, score=None, submission_status=SUBMISSION_STATUS_LLM_FAILED)
        _, _, sub2 = _scored_submission(assignment2, eset2, score=None, submission_status=SUBMISSION_STATUS_LLM_FAILED)
        _record_dlq("evaluate_essay", [str(sub1.id)], {}, RuntimeError("x"), attempts=3)
        _record_dlq("evaluate_essay", [str(sub2.id)], {}, RuntimeError("x"), attempts=3)

        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment1.id}/dashboard/")
        assert resp.data["data"]["dlq_backlog_count"] == 1

    def test_resolved_dlq_entries_excluded_from_backlog(self, admin_client):
        assignment, eset = _make_assignment()
        _, _, sub = _scored_submission(assignment, eset, score=None, submission_status=SUBMISSION_STATUS_LLM_FAILED)
        _record_dlq("evaluate_essay", [str(sub.id)], {}, RuntimeError("x"), attempts=3)
        EssayFailedJob.objects.filter(task_name="evaluate_essay", args=[str(sub.id)]).update(resolved_at=timezone.now())

        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert resp.data["data"]["dlq_backlog_count"] == 0

    def test_dlq_backlog_also_counts_a_stuck_report_generation(self, admin_client):
        # Phase 11's own final-audit round: dlq_backlog_count was
        # hardcoded to task_name="evaluate_essay" only, a real gap from
        # back when that was the only task ever DLQ'd against one
        # specific submission — generate_essay_report (Phase 11) is a
        # second one. A permanently-stuck report generation must still
        # move this KPI, using Celery's own real (dotted) task name for
        # that path — see _compute_essay_dashboard's own comment for why
        # the two task names differ in shape within this same table.
        assignment, eset = _make_assignment()
        _, _, sub = _scored_submission(assignment, eset, score=7)
        EssayFailedJob.objects.create(
            task_name="essays.tasks.generate_essay_report", task_id="", args=[str(sub.id)], kwargs={},
            error="report render bug", traceback="", attempts=3,
        )

        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert resp.data["data"]["dlq_backlog_count"] == 1

    def test_time_remaining_only_shown_while_live(self, admin_client):
        assignment, eset = _make_assignment(status=ASSIGNMENT_STATUS_SCHEDULED)
        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert resp.data["data"]["time_remaining_seconds"] is None

    def test_time_remaining_reflects_the_expire_time_while_live(self, admin_client):
        expire = timezone.now() + timedelta(minutes=10)
        assignment, eset = _make_assignment(status=ASSIGNMENT_STATUS_LIVE, global_expire_time=expire)
        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        remaining = resp.data["data"]["time_remaining_seconds"]
        assert remaining is not None
        assert 590 <= remaining <= 600  # ~10 minutes, allowing for test execution time

    def test_no_allocations_no_crash(self, admin_client):
        assignment, eset = _make_assignment()
        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        data = resp.data["data"]
        assert data["total_allocated"] == 0
        assert data["completion_rate_percentage"] == 0.0
        assert data["average_score"] is None

    def test_submission_throughput_has_six_buckets_summing_to_recent_submissions(self, admin_client):
        assignment, eset = _make_assignment()
        _scored_submission(assignment, eset, score=7)
        _scored_submission(assignment, eset, score=8)

        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        throughput = resp.data["data"]["submission_throughput"]
        assert len(throughput) == 6
        assert sum(b["count"] for b in throughput) == 2  # both just created, inside the 30-minute window


@pytest.mark.django_db
class TestDashboardCaching:
    # Eleven write paths in total invalidate this cache — see
    # AdminEssayAssignmentDashboardView's own module-header comment
    # (essays/views.py) for the full list. This class's own tests below
    # exercise each one directly.
    def test_second_request_within_ttl_serves_the_cached_value(self, admin_client):
        assignment, eset = _make_assignment()
        _scored_submission(assignment, eset, score=5)

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["total_scored"] == 1

        _scored_submission(assignment, eset, score=9)

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["total_scored"] == 1  # still stale — nothing invalidated the cache directly

    def test_status_transition_invalidates_the_cache(self, admin_client):
        # The core Phase 10 behavior: unlike Phase 9's Analytics, this
        # cache is NOT just a plain TTL — _transition_submission_status()
        # (the pipeline's own automatic choke point) must actually
        # invalidate it, so a live-watched dashboard reflects a real
        # pipeline event immediately, not up to 300s later.
        assignment, eset = _make_assignment()
        student_id = uuid.uuid4()
        _allocate(assignment, eset, student_id)
        attempt = _attempt(assignment, eset, student_id)
        submission = _submission(attempt, status=SUBMISSION_STATUS_LLM_PROCESSING)

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["pending_evaluation_count"] == 1

        _transition_submission_status(submission, SUBMISSION_STATUS_LLM_COMPLETE, expected_status=SUBMISSION_STATUS_LLM_PROCESSING)
        EssayScore.objects.create(submission=submission, score=7, feedback={"overall": "x"})

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["pending_evaluation_count"] == 0  # genuinely fresh, not stale
        assert second.data["data"]["total_scored"] == 1

    def test_a_new_submission_invalidates_the_cache(self, admin_client):
        # The single most important finding of this phase's own final-
        # audit round: finalize_attempts() (the shared primitive behind
        # a student's own manual submit, the beat sweep's auto-submit,
        # and an admin close/ cascade) used to create a brand-new
        # EssaySubmission — changing total_submitted/completion_rate_
        # percentage/in_progress_count, all dashboard KPIs — without
        # invalidating this cache at all. Exercises finalize_attempts()
        # directly (matching this suite's own established convention,
        # e.g. test_concurrency.py) rather than the full student HTTP
        # flow, since the fix lives in scoring.py, not the endpoint.
        assignment, eset = _make_assignment()
        student_id = uuid.uuid4()
        _allocate(assignment, eset, student_id)
        attempt = _attempt(assignment, eset, student_id, status=ATTEMPT_STATUS_IN_PROGRESS)

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["total_submitted"] == 0
        assert first.data["data"]["in_progress_count"] == 1

        # evaluate_essay/check_text_similarity are imported LOCALLY inside
        # _create_and_dispatch_submissions() (essays/scoring.py) — patch
        # their origin module (essays.tasks), not essays.scoring itself,
        # which never holds them as a module-level attribute at all.
        with patch("essays.tasks.evaluate_essay"), patch("essays.tasks.check_text_similarity"):
            finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_SUBMITTED)

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["total_submitted"] == 1  # genuinely fresh, not stale
        assert second.data["data"]["in_progress_count"] == 0
        assert second.data["data"]["completion_rate_percentage"] == 100.0

    def test_retrigger_invalidates_the_cache(self, admin_client):
        assignment, eset = _make_assignment()
        _, _, submission = _scored_submission(assignment, eset, score=None, submission_status=SUBMISSION_STATUS_LLM_FAILED)
        _record_dlq("evaluate_essay", [str(submission.id)], {}, RuntimeError("x"), attempts=3)

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["dlq_backlog_count"] == 1
        assert first.data["data"]["pending_evaluation_count"] == 0

        with patch("essays.tasks.evaluate_essay"):
            admin_client.post(
                f"/api/essay/admin/submissions/{submission.id}/retrigger/", {"reason": "x"}, format="json",
            )

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["pending_evaluation_count"] == 1  # now LLM_PROCESSING
        assert second.data["data"]["dlq_backlog_count"] == 0  # resolved by the retrigger

    def test_dlq_recovery_override_invalidates_the_cache(self, admin_client):
        assignment, eset = _make_assignment()
        _, _, submission = _scored_submission(assignment, eset, score=None, submission_status=SUBMISSION_STATUS_LLM_FAILED)

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["total_scored"] == 0

        admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/override-score/",
            {"score": 6, "feedback": {"overall": "x"}, "reason": "x"}, format="json",
        )

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["total_scored"] == 1
        assert second.data["data"]["average_score"] == 6.0

    def test_general_override_invalidates_the_cache(self, admin_client):
        # The one write path that changes a dashboard KPI (average_score)
        # WITHOUT any status transition alongside it — proves this view's
        # own dedicated invalidation call, not a side effect of #1 above.
        assignment, eset = _make_assignment()
        _, _, submission = _scored_submission(assignment, eset, score=3)

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["average_score"] == 3.0

        admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/general-override-score/",
            {"score": 9, "feedback": {"overall": "x"}, "reason": "x"}, format="json",
        )

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["average_score"] == 9.0

    def test_starting_an_assignment_invalidates_the_cache(self, admin_client):
        # Real gap found by this phase's own second final-audit round:
        # AdminEssayAssignmentStartView changes EssayAssignment.status
        # directly (SCHEDULED -> LIVE) — none of the original five hooks
        # touch EssayAssignment.status at all, so a dashboard cached
        # while still SCHEDULED (time_remaining_seconds: null) would
        # keep showing that stale shape after an admin clicks Start.
        assignment, eset = _make_assignment(status=ASSIGNMENT_STATUS_SCHEDULED)

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["assignment_status"] == "SCHEDULED"
        assert first.data["data"]["time_remaining_seconds"] is None

        admin_client.patch(f"/api/essay/admin/assignments/{assignment.id}/start/")

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["assignment_status"] == "LIVE"
        assert second.data["data"]["time_remaining_seconds"] is not None

    def test_closing_an_assignment_with_no_in_progress_attempts_still_invalidates_the_cache(self, admin_client):
        # Real gap found by this phase's own second final-audit round:
        # the cascade AdminEssayAssignmentCloseView already runs
        # (finalize_attempts()) only invalidates the cache when at least
        # one attempt actually gets auto-submitted — the common case of
        # closing an assignment with ZERO students still IN_PROGRESS
        # (nobody ever started, in this fixture) used to silently skip
        # invalidation entirely, leaving the dashboard claiming "LIVE"
        # after the exam had genuinely already ended.
        assignment, eset = _make_assignment(status=ASSIGNMENT_STATUS_LIVE)
        _allocate(assignment, eset)  # allocated, never started — nothing for finalize_attempts() to do

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["assignment_status"] == "LIVE"

        resp = admin_client.patch(f"/api/essay/admin/assignments/{assignment.id}/close/")
        assert resp.data["data"]["attempts_auto_submitted"] == 0  # confirms the cascade did nothing

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["assignment_status"] == "CLOSED"  # genuinely fresh, not stale

    def test_automatic_expiry_sweep_invalidates_the_cache(self, admin_client):
        # Real gap found by this phase's own THIRD final-audit round: the
        # AUTOMATIC, time-based path an exam most commonly actually ends
        # through (its own time simply running out, via the beat
        # schedule) — likely the majority case, not the exception,
        # against the two admin-initiated Start/Close gaps the second
        # round already found. sweep_expired_assignments() had zero
        # dashboard-cache invalidation of its own.
        from essays.tasks import sweep_expired_assignments

        assignment, eset = _make_assignment(
            status=ASSIGNMENT_STATUS_LIVE, global_expire_time=timezone.now() - timedelta(minutes=1),
        )

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["assignment_status"] == "LIVE"

        result = sweep_expired_assignments.apply().get()
        assert result["closed"] == 1

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["assignment_status"] == "CLOSED"  # genuinely fresh, not stale
        assert second.data["data"]["time_remaining_seconds"] is None

    def test_starting_an_attempt_invalidates_the_cache(self, admin_client, student_client):
        # Real gap found by this phase's own FOURTH final-audit round: a
        # brand-new attempt is the very FIRST event in the whole
        # pipeline, before any submission exists at all, and changes
        # in_progress_count on its own — none of the eight hooks already
        # built cover attempt CREATION, only later pipeline stages.
        assignment, eset = _make_assignment()
        _allocate(assignment, eset, STUDENT_USER_ID)

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["in_progress_count"] == 0

        resp = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        assert resp.status_code == 201

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["in_progress_count"] == 1  # genuinely fresh, not stale

    def test_roster_resync_invalidates_the_cache(self, admin_client):
        # Real gap found by this phase's own FOURTH final-audit round:
        # new EssayStudentSetAllocation rows change total_allocated,
        # which completion_rate_percentage is computed from.
        assignment, eset = _make_assignment()
        _allocate(assignment, eset)

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["total_allocated"] == 1

        new_student_id = uuid.uuid4()
        with patch(
            "essays.allocation.fetch_batch_roster",
            return_value=[{"user_id": str(new_student_id), "student_id": "R999", "department": "CSE"}],
        ):
            resp = admin_client.post(f"/api/essay/admin/assignments/{assignment.id}/resync-roster/")
        assert resp.status_code == 200
        assert resp.data["data"]["new_allocations"] == 1

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["total_allocated"] == 2  # genuinely fresh, not stale

    def test_dlq_sweep_self_heal_invalidates_the_cache(self, admin_client):
        # Real gap found by this phase's own FOURTH final-audit round:
        # the DLQ sweeper's own self-heal branch (an entry found already
        # scored by an earlier retry) resolves the EssayFailedJob entry,
        # reducing dlq_backlog_count, with zero invalidation of its own.
        assignment, eset = _make_assignment()
        _, _, submission = _scored_submission(assignment, eset, score=7)  # already scored
        _record_dlq("evaluate_essay", [str(submission.id)], {}, RuntimeError("x"), attempts=3)
        from essays.models import EssayFailedJob
        EssayFailedJob.objects.filter(task_name="evaluate_essay", args=[str(submission.id)]).update(
            created_at=timezone.now() - timedelta(minutes=30),
        )

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["dlq_backlog_count"] == 1

        with patch("essays.tasks.connection") as mock_connection:
            mock_connection.cursor.return_value.__enter__.return_value.fetchone.return_value = [True]
            result = sweep_dlq_entries.apply().get()
        assert result["self_healed"] == 1

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["dlq_backlog_count"] == 0  # genuinely fresh, not stale

    def test_dlq_sweep_circuit_breaker_invalidates_the_cache(self, admin_client):
        # Same finding as the self-heal test above, for the sweeper's
        # OTHER resolution path — the circuit-breaker bulk-update.
        from essays.models import EssayFailedJob
        assignment, eset = _make_assignment()
        _, _, submission = _scored_submission(assignment, eset, score=None, submission_status=SUBMISSION_STATUS_LLM_FAILED)
        entry = EssayFailedJob.objects.create(
            task_name="evaluate_essay", args=[str(submission.id)], error="x",
            attempts=3, dlq_retry_count=DLQ_RETRY_CEILING - 1,
        )
        EssayFailedJob.objects.filter(pk=entry.pk).update(created_at=timezone.now() - timedelta(minutes=30))

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert first.data["data"]["dlq_backlog_count"] == 1

        with patch("essays.tasks.connection") as mock_connection, patch("essays.tasks.evaluate_essay"):
            mock_connection.cursor.return_value.__enter__.return_value.fetchone.return_value = [True]
            result = sweep_dlq_entries.apply().get()
        assert result["circuit_broken"] == 1

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert second.data["data"]["dlq_backlog_count"] == 0  # genuinely fresh, not stale

    def test_different_assignments_have_independent_cache_entries(self, admin_client):
        assignment1, eset1 = _make_assignment()
        assignment2, eset2 = _make_assignment()
        _scored_submission(assignment1, eset1, score=2)
        _scored_submission(assignment2, eset2, score=8)

        resp1 = admin_client.get(f"/api/essay/admin/assignments/{assignment1.id}/dashboard/")
        resp2 = admin_client.get(f"/api/essay/admin/assignments/{assignment2.id}/dashboard/")
        assert resp1.data["data"]["average_score"] == 2.0
        assert resp2.data["data"]["average_score"] == 8.0


@pytest.mark.django_db
class TestDashboardPermissionsAndIsolation:
    def test_institution_isolated_404(self, admin_client, admin_b_client):
        assignment, eset = _make_assignment()
        resp = admin_b_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert resp.status_code == 404

    def test_unauthenticated_rejected(self, anon_client):
        assignment, eset = _make_assignment()
        resp = anon_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert resp.status_code == 401

    def test_student_role_rejected(self, student_client):
        assignment, eset = _make_assignment()
        resp = student_client.get(f"/api/essay/admin/assignments/{assignment.id}/dashboard/")
        assert resp.status_code == 403

    def test_nonexistent_assignment_404(self, admin_client):
        resp = admin_client.get(f"/api/essay/admin/assignments/{uuid.uuid4()}/dashboard/")
        assert resp.status_code == 404
