import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, Question, BatchAssignment, AssessmentSession,
    ResultSummary, ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_CLOSED,
    ASSIGNMENT_STATUS_SCHEDULED, SESSION_STATUS_IN_PROGRESS,
    SESSION_STATUS_AUTO_SUBMITTED, SESSION_STATUS_SUBMITTED,
)
from assessments.tasks import sweep_expired_assignments, sweep_expired_sessions

from .conftest import INSTITUTION_A, ADMIN_USER_ID


@pytest.fixture
def paper_with_set(db):
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Sweep Test Paper",
        created_by=ADMIN_USER_ID, is_published=True,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    Question.objects.create(set=qset, question_text="Q1", marks=1)
    return paper, qset


def _assignment(paper, **overrides):
    defaults = dict(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID,
        status=ASSIGNMENT_STATUS_LIVE,
    )
    defaults.update(overrides)
    return BatchAssignment.objects.create(**defaults)


class TestSweepExpiredAssignments:
    def test_closes_expired_live_assignment(self, paper_with_set):
        paper, _ = paper_with_set
        assignment = _assignment(paper, global_expire_time=timezone.now() - timedelta(minutes=1))

        result = sweep_expired_assignments()

        assert result["closed"] == 1
        assignment.refresh_from_db()
        assert assignment.status == ASSIGNMENT_STATUS_CLOSED

    def test_does_not_touch_not_yet_expired_assignment(self, paper_with_set):
        paper, _ = paper_with_set
        assignment = _assignment(paper, global_expire_time=timezone.now() + timedelta(hours=1))

        sweep_expired_assignments()

        assignment.refresh_from_db()
        assert assignment.status == ASSIGNMENT_STATUS_LIVE

    def test_does_not_touch_scheduled_assignment_even_if_expire_time_passed(self, paper_with_set):
        # SCHEDULED -> LIVE only ever happens via the admin's manual start/
        # action (ADR 001) — the sweep must never auto-start an assignment.
        paper, _ = paper_with_set
        assignment = _assignment(
            paper, status=ASSIGNMENT_STATUS_SCHEDULED,
            global_expire_time=timezone.now() - timedelta(minutes=1),
        )

        sweep_expired_assignments()

        assignment.refresh_from_db()
        assert assignment.status == ASSIGNMENT_STATUS_SCHEDULED

    def test_idempotent_second_sweep_is_noop(self, paper_with_set):
        paper, _ = paper_with_set
        _assignment(paper, global_expire_time=timezone.now() - timedelta(minutes=1))

        first = sweep_expired_assignments()
        second = sweep_expired_assignments()

        assert first["closed"] == 1
        assert second["closed"] == 0


class TestSweepExpiredSessions:
    def test_auto_submits_expired_session(self, paper_with_set):
        paper, qset = paper_with_set
        assignment = _assignment(paper)
        session = AssessmentSession.objects.create(
            assignment=assignment, student_id=uuid.uuid4(), set=qset,
            ends_at=timezone.now() - timedelta(seconds=1),
            status=SESSION_STATUS_IN_PROGRESS,
        )

        result = sweep_expired_sessions()

        assert result["auto_submitted"] == 1
        session.refresh_from_db()
        assert session.status == SESSION_STATUS_AUTO_SUBMITTED
        assert ResultSummary.objects.filter(session=session).exists()

    def test_does_not_touch_session_not_yet_expired(self, paper_with_set):
        paper, qset = paper_with_set
        assignment = _assignment(paper)
        session = AssessmentSession.objects.create(
            assignment=assignment, student_id=uuid.uuid4(), set=qset,
            ends_at=timezone.now() + timedelta(hours=1),
            status=SESSION_STATUS_IN_PROGRESS,
        )

        sweep_expired_sessions()

        session.refresh_from_db()
        assert session.status == SESSION_STATUS_IN_PROGRESS

    def test_redelivered_sweep_no_duplicate_scoring(self, paper_with_set):
        paper, qset = paper_with_set
        assignment = _assignment(paper)
        session = AssessmentSession.objects.create(
            assignment=assignment, student_id=uuid.uuid4(), set=qset,
            ends_at=timezone.now() - timedelta(seconds=1),
            status=SESSION_STATUS_IN_PROGRESS,
        )

        first = sweep_expired_sessions()
        second = sweep_expired_sessions()  # simulated Celery redelivery

        assert first["auto_submitted"] == 1
        assert second["auto_submitted"] == 0
        assert ResultSummary.objects.filter(session=session).count() == 1

    def test_manual_submit_arriving_before_sweep_wins(self, paper_with_set):
        # Simulated manual submit (Task 5.2 doesn't exist yet — call the
        # same primitive the sweep uses, targeting SUBMITTED instead).
        from assessments.scoring import finalize_sessions

        paper, qset = paper_with_set
        assignment = _assignment(paper)
        session = AssessmentSession.objects.create(
            assignment=assignment, student_id=uuid.uuid4(), set=qset,
            ends_at=timezone.now() - timedelta(seconds=1),
            status=SESSION_STATUS_IN_PROGRESS,
        )

        finalize_sessions(AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_SUBMITTED)
        result = sweep_expired_sessions()

        assert result["auto_submitted"] == 0
        session.refresh_from_db()
        assert session.status == SESSION_STATUS_SUBMITTED

    def test_load_5000_sessions_one_sweep_cycle(self, paper_with_set):
        import time

        paper, qset = paper_with_set
        assignment = _assignment(paper)
        now = timezone.now()
        AssessmentSession.objects.bulk_create([
            AssessmentSession(
                assignment=assignment, student_id=uuid.uuid4(), set=qset,
                ends_at=now - timedelta(seconds=1), status=SESSION_STATUS_IN_PROGRESS,
                started_at=now - timedelta(minutes=30),
            )
            for _ in range(5000)
        ])

        start = time.monotonic()
        result = sweep_expired_sessions()
        elapsed = time.monotonic() - start

        assert result["auto_submitted"] == 5000
        assert ResultSummary.objects.filter(assignment=assignment).count() == 5000
        # One sweep cycle is 20s (core/settings.py CELERY_BEAT_SCHEDULE) —
        # the sweep itself must complete well within that on a single pass.
        assert elapsed < 20, f"sweep took {elapsed:.1f}s, exceeds one 20s cycle"


# ── Dead-letter queue (Task 13.1, AT12) ────────────────────────────────────
#
# Testing the *full* retry-loop-to-DLQ pipeline through pytest turned out to
# fight Celery's own test machinery more than it tested this project's code:
# a directly-called bound task's self.retry() doesn't loop at all (Celery
# re-raises immediately outside the real task-invocation path); .apply()
# does loop, but test_settings.py's CELERY_TASK_EAGER_PROPAGATES=True (the
# right default for every other test in this file, where an unexpected task
# exception should fail loudly) makes it re-raise the first Retry instead of
# exhausting the budget; passing throw=False explicitly only affects the
# outermost .apply() call — Celery 5.4's internal retry recursion
# (Task.apply() calling `retval.sig.apply(retries=retries + 1)`, confirmed
# by reading the installed library's own source) doesn't forward that
# override to the recursive calls, so it reverts to the app-config default
# on attempt 2 regardless. All of this was confirmed empirically (including
# a manage.py shell run under a non-test settings module, where the full
# loop-then-DLQ behavior in fact worked correctly end to end — 3 attempts,
# then a FailedJob row) before concluding it isn't reliably reproducible
# through pytest against test_settings.py without changing that file's
# CELERY_TASK_EAGER_PROPAGATES setting specifically to accommodate this one
# test class, which isn't worth doing for the rest of the suite.
#
# So: test the two things that actually matter, at a level that's reliable
# to automate. (1) DeadLetteringTask.on_failure() itself — the actual DLQ-
# recording logic — called directly. (2) that both sweep tasks are wired to
# use it with the expected max_retries. The real end-to-end retry loop is
# exercised by every other test in this file already (they all call the
# tasks and rely on Celery's real retry decorator existing), just not its
# failure path specifically.

class TestDeadLetteringTaskOnFailure:
    def test_on_failure_records_a_failed_job(self, db):
        from assessments.models import FailedJob
        from assessments.tasks import DeadLetteringTask

        task = DeadLetteringTask()
        task.name = "assessments.tasks.sweep_expired_assignments"
        exc = RuntimeError("simulated transient DB error")

        task.on_failure(exc, "task-id-123", [], {"foo": "bar"}, "traceback text")

        assert FailedJob.objects.count() == 1
        job = FailedJob.objects.first()
        assert job.task_name == "assessments.tasks.sweep_expired_assignments"
        assert job.task_id == "task-id-123"
        assert job.kwargs == {"foo": "bar"}
        assert "simulated transient DB error" in job.error
        assert job.traceback == "traceback text"
        assert job.attempts == 3
        assert job.resolved_at is None

    def test_on_failure_never_raises_even_if_recording_itself_fails(self, db):
        from unittest.mock import patch
        from assessments.tasks import DeadLetteringTask

        task = DeadLetteringTask()
        task.name = "assessments.tasks.sweep_expired_assignments"

        # If writing the FailedJob row itself blows up (e.g. DB is also
        # down), on_failure() must swallow that — it must never become a
        # second, unhandled exception inside Celery's own failure-handling
        # path on top of the original task failure.
        with patch("assessments.models.FailedJob.objects.create", side_effect=RuntimeError("DB also down")):
            task.on_failure(RuntimeError("original failure"), "tid", [], {}, "tb")  # must not raise

    def test_both_sweep_tasks_use_dead_lettering_base_with_matching_max_retries(self, db):
        from assessments.tasks import DeadLetteringTask, _MAX_RETRIES
        assert isinstance(sweep_expired_assignments, DeadLetteringTask)
        assert isinstance(sweep_expired_sessions, DeadLetteringTask)
        assert sweep_expired_assignments.max_retries == _MAX_RETRIES
        assert sweep_expired_sessions.max_retries == _MAX_RETRIES

    def test_successful_sweep_never_writes_to_dlq(self, paper_with_set):
        from assessments.models import FailedJob
        paper, _ = paper_with_set
        _assignment(paper, global_expire_time=timezone.now() - timedelta(minutes=1))

        sweep_expired_assignments()

        assert FailedJob.objects.count() == 0
