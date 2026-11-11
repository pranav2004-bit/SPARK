"""
test_submission_events.py — Phase 6, Task 6.1's own audit-trail
requirement: "full audit-log/event trail in chronological order (every
status transition, worker id, error detail)". EssaySubmissionEvent
(essays/models.py) is written from exactly two choke points in
essays/tasks.py — _transition_submission_status() and _record_dlq() — so
these tests exercise those two functions directly rather than the full
evaluate_essay pipeline, matching how test_dlq.py already tests
_record_dlq() in isolation.
"""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt, EssaySubmission,
    EssaySubmissionEvent, SUBMISSION_STATUS_PENDING, SUBMISSION_STATUS_LLM_PROCESSING,
    SUBMISSION_EVENT_STATUS_CHANGE, SUBMISSION_EVENT_DLQ_RECORDED,
)
from essays.tasks import _transition_submission_status, _record_dlq

from .conftest import INSTITUTION_A, ADMIN_USER_ID


@pytest.fixture
def submission(db):
    paper = EssayPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
    assignment = EssayAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
    )
    attempt = EssayAttempt.objects.create(
        assignment=assignment, student_id=uuid.uuid4(), set=eset,
        ends_at=timezone.now() + timedelta(hours=1), draft_response="An essay response.",
    )
    return EssaySubmission.objects.create(attempt=attempt)


class TestStatusChangeEvents:
    def test_successful_transition_logs_an_event(self, submission):
        _transition_submission_status(submission, SUBMISSION_STATUS_LLM_PROCESSING, expected_status=SUBMISSION_STATUS_PENDING)

        event = EssaySubmissionEvent.objects.get(submission=submission)
        assert event.event_type == SUBMISSION_EVENT_STATUS_CHANGE
        assert SUBMISSION_STATUS_PENDING in event.detail
        assert SUBMISSION_STATUS_LLM_PROCESSING in event.detail

    def test_cas_miss_does_not_log_a_phantom_event(self, submission):
        # submission starts PENDING — expecting LLM_PROCESSING (wrong) means
        # the conditional UPDATE matches zero rows: a real no-op, not a
        # transition, so nothing should be logged for it.
        updated = _transition_submission_status(
            submission, SUBMISSION_STATUS_LLM_PROCESSING, expected_status=SUBMISSION_STATUS_LLM_PROCESSING,
        )
        assert updated == 0
        assert EssaySubmissionEvent.objects.filter(submission=submission).count() == 0

    def test_events_ordered_chronologically(self, submission):
        _transition_submission_status(submission, SUBMISSION_STATUS_LLM_PROCESSING, expected_status=SUBMISSION_STATUS_PENDING)
        _transition_submission_status(submission, SUBMISSION_STATUS_PENDING, expected_status=SUBMISSION_STATUS_LLM_PROCESSING)

        events = list(EssaySubmissionEvent.objects.filter(submission=submission))
        assert len(events) == 2
        assert events[0].occurred_at <= events[1].occurred_at
        assert SUBMISSION_STATUS_LLM_PROCESSING in events[0].detail
        assert events[1].detail.startswith(SUBMISSION_STATUS_LLM_PROCESSING)

    def test_worker_context_empty_outside_a_real_celery_task(self, submission):
        # Called directly here (no Celery task context), matching how
        # every other direct-call test in this suite exercises
        # _transition_submission_status — celery.current_task is None.
        _transition_submission_status(submission, SUBMISSION_STATUS_LLM_PROCESSING, expected_status=SUBMISSION_STATUS_PENDING)
        event = EssaySubmissionEvent.objects.get(submission=submission)
        assert event.worker_hostname == ""
        assert event.task_id == ""


class TestDlqRecordedEvents:
    def test_evaluate_essay_dlq_write_logs_an_event_with_the_error(self, submission):
        _record_dlq("evaluate_essay", [str(submission.id)], {}, RuntimeError("permanent failure"), attempts=3)

        event = EssaySubmissionEvent.objects.get(submission=submission, event_type=SUBMISSION_EVENT_DLQ_RECORDED)
        assert "permanent failure" in event.detail

    def test_repeated_dlq_write_for_the_same_submission_logs_each_occurrence(self, submission):
        # _record_dlq itself dedupes the EssayFailedJob ROW (test_dlq.py's
        # own coverage), but the audit trail's whole point is showing every
        # occurrence, not collapsing them the same way.
        _record_dlq("evaluate_essay", [str(submission.id)], {}, RuntimeError("first"), attempts=0)
        _record_dlq("evaluate_essay", [str(submission.id)], {}, RuntimeError("second"), attempts=1)

        events = EssaySubmissionEvent.objects.filter(submission=submission, event_type=SUBMISSION_EVENT_DLQ_RECORDED)
        assert events.count() == 2

    def test_sweep_task_dlq_write_is_not_submission_scoped_so_logs_nothing(self, db):
        # sweep_expired_assignments/attempts operate on assignments/
        # attempts, not one submission — args[0] wouldn't even be a
        # submission id, so no EssaySubmissionEvent should be attempted.
        _record_dlq("sweep_expired_assignments", [], {}, RuntimeError("boom"), attempts=3)
        assert EssaySubmissionEvent.objects.count() == 0
