import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, BatchAssignment, AssessmentSession,
    ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_CLOSED,
    SESSION_STATUS_IN_PROGRESS, SESSION_STATUS_SUBMITTED,
)
from assessments.enforcement import session_is_writable, strip_client_timestamps

from .conftest import INSTITUTION_A, ADMIN_USER_ID


@pytest.fixture
def live_assignment(db):
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Enforcement Test Paper",
        created_by=ADMIN_USER_ID, is_published=True,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    return BatchAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID,
        status=ASSIGNMENT_STATUS_LIVE,
    ), qset


def _session(assignment, qset, **overrides):
    defaults = dict(
        assignment=assignment, student_id=uuid.uuid4(), set=qset,
        ends_at=timezone.now() + timedelta(hours=1),
        status=SESSION_STATUS_IN_PROGRESS,
    )
    defaults.update(overrides)
    return AssessmentSession.objects.create(**defaults)


class TestSessionIsWritable:
    def test_in_progress_session_before_deadline_is_writable(self, live_assignment):
        assignment, qset = live_assignment
        session = _session(assignment, qset)

        ok, reason = session_is_writable(session)

        assert ok is True
        assert reason is None

    def test_expired_session_not_writable(self, live_assignment):
        assignment, qset = live_assignment
        session = _session(assignment, qset, ends_at=timezone.now() - timedelta(seconds=1))

        ok, reason = session_is_writable(session)

        assert ok is False
        assert "expired" in reason.lower()

    def test_expired_by_two_seconds_not_writable(self, live_assignment):
        # Mirrors the exact Task 4.2 test-suite row: "submit sent 2 seconds
        # after ends_at" — rejected regardless of what the client claims.
        assignment, qset = live_assignment
        session = _session(assignment, qset, ends_at=timezone.now() - timedelta(seconds=2))

        ok, _ = session_is_writable(session)
        assert ok is False

    def test_already_submitted_session_not_writable(self, live_assignment):
        assignment, qset = live_assignment
        session = _session(assignment, qset, status=SESSION_STATUS_SUBMITTED)

        ok, reason = session_is_writable(session)

        assert ok is False
        assert "not in progress" in reason.lower() or "SUBMITTED" in reason

    def test_closed_assignment_not_writable_even_if_session_still_in_progress(self, live_assignment):
        # Defense in depth (ADR 001): assignment.status != 'CLOSED' is
        # checked independently of session.status — catches a cascade
        # bug/lag where the sweep hasn't yet flipped this specific session.
        assignment, qset = live_assignment
        session = _session(assignment, qset)
        BatchAssignment.objects.filter(pk=assignment.pk).update(status=ASSIGNMENT_STATUS_CLOSED)
        assignment.refresh_from_db()

        ok, reason = session_is_writable(session, assignment)

        assert ok is False
        assert "closed" in reason.lower()

    def test_uses_session_assignment_when_not_explicitly_passed(self, live_assignment):
        assignment, qset = live_assignment
        session = _session(assignment, qset)
        BatchAssignment.objects.filter(pk=assignment.pk).update(status=ASSIGNMENT_STATUS_CLOSED)

        # Re-fetch fresh from the DB — session.assignment would otherwise
        # return Django's cached (pre-update) related-object instance from
        # when this session was created, not what a real request-scoped
        # get_object_or_404() lookup would see.
        fresh_session = AssessmentSession.objects.get(pk=session.pk)
        ok, reason = session_is_writable(fresh_session)  # no assignment arg — must look it up via session.assignment

        assert ok is False
        assert "closed" in reason.lower()

    def test_exactly_at_deadline_is_not_writable(self, live_assignment):
        # now() >= ends_at is the sweep's own boundary condition (Task
        # 4.1) — this check must use the same >= semantics, not >, so a
        # request landing in the exact same instant as the sweep never
        # succeeds where the sweep would also claim the session.
        assignment, qset = live_assignment
        session = _session(assignment, qset, ends_at=timezone.now())

        ok, _ = session_is_writable(session)
        assert ok is False


class TestStripClientTimestamps:
    def test_strips_all_known_timestamp_fields(self):
        data = {
            "submitted_at": "2020-01-01T00:00:00Z",
            "answered_at": "2020-01-01T00:00:00Z",
            "started_at": "2020-01-01T00:00:00Z",
            "ends_at": "2099-01-01T00:00:00Z",
            "timestamp": "2020-01-01T00:00:00Z",
            "selected_option_ids": ["a", "b"],
        }
        result = strip_client_timestamps(data)
        assert result == {"selected_option_ids": ["a", "b"]}

    def test_does_not_mutate_input(self):
        data = {"submitted_at": "forged", "answer": "x"}
        strip_client_timestamps(data)
        assert "submitted_at" in data  # original untouched

    def test_empty_dict_returns_empty(self):
        assert strip_client_timestamps({}) == {}

    def test_no_timestamp_fields_passes_through_unchanged(self):
        data = {"question_id": "q1", "selected_option_ids": ["a"]}
        assert strip_client_timestamps(data) == data
