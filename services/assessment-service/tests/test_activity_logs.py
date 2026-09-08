import uuid
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, Question, BatchAssignment, AssessmentSession,
    AssessmentResponse, ActivityLog, ResultSummary,
    ASSIGNMENT_STATUS_LIVE, SESSION_STATUS_IN_PROGRESS,
    ACTIVITY_EVENT_TAB_SWITCH, ACTIVITY_EVENT_FULLSCREEN_EXIT, ACTIVITY_EVENT_COPY,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def exam_setup(db):
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Activity Log Test Paper",
        created_by=ADMIN_USER_ID,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    Question.objects.create(set=qset, question_text="Q1", marks=1)

    assignment = BatchAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
    )
    session = AssessmentSession.objects.create(
        assignment=assignment, student_id=STUDENT_USER_ID, set=qset,
        ends_at=timezone.now() + timedelta(hours=1),
    )
    return {"session": session, "assignment": assignment, "qset": qset}


def _url(session_id):
    return f"/api/assessments/student/sessions/{session_id}/activity-logs/"


class TestActivityLogIngestion:
    def test_bulk_inserts_valid_events(self, student_client, exam_setup):
        session = exam_setup["session"]
        resp = student_client.post(_url(session.id), {
            "events": [
                {"event_type": "tab_switch"},
                {"event_type": "copy", "metadata": {"selection_length": 12}},
            ],
        }, format="json")

        assert resp.status_code == 201
        assert resp.json()["data"]["logged"] == 2
        assert ActivityLog.objects.filter(session=session).count() == 2

    def test_skips_malformed_events_without_failing_whole_batch(self, student_client, exam_setup):
        session = exam_setup["session"]
        resp = student_client.post(_url(session.id), {
            "events": [
                {"event_type": "tab_switch"},
                {"event_type": "not_a_real_type"},
                {"no_event_type_key": True},
            ],
        }, format="json")

        assert resp.status_code == 201
        assert resp.json()["data"]["logged"] == 1
        assert ActivityLog.objects.filter(session=session).count() == 1

    def test_empty_events_list_rejected(self, student_client, exam_setup):
        resp = student_client.post(_url(exam_setup["session"].id), {"events": []}, format="json")
        assert resp.status_code == 400

    def test_accepts_screenshot_attempt_and_connection_lost_event_types(self, student_client, exam_setup):
        # Added 2026-08-18 for the full-transparency activity timeline —
        # these two are client-detected (useActivityCapture.ts), unlike
        # question_answered/admin_extended_time which are server-authored
        # and never arrive through this ingestion endpoint at all.
        session = exam_setup["session"]
        resp = student_client.post(_url(session.id), {
            "events": [
                {"event_type": "screenshot_attempt"},
                {"event_type": "connection_lost", "metadata": {"duration_seconds": 42}},
            ],
        }, format="json")

        assert resp.status_code == 201
        assert resp.json()["data"]["logged"] == 2
        logged_types = set(ActivityLog.objects.filter(session=session).values_list("event_type", flat=True))
        assert logged_types == {"screenshot_attempt", "connection_lost"}

    def test_over_max_batch_size_rejected(self, student_client, exam_setup):
        events = [{"event_type": "tab_switch"} for _ in range(101)]
        resp = student_client.post(_url(exam_setup["session"].id), {"events": events}, format="json")
        assert resp.status_code == 400
        assert ActivityLog.objects.count() == 0

    def test_client_occurred_at_is_used_when_valid(self, student_client, exam_setup):
        session = exam_setup["session"]
        claimed = "2026-01-01T10:00:00Z"
        student_client.post(_url(session.id), {
            "events": [{"event_type": "tab_switch", "occurred_at": claimed}],
        }, format="json")
        log = ActivityLog.objects.get(session=session)
        assert log.occurred_at.year == 2026
        assert log.occurred_at.month == 1

    def test_missing_occurred_at_falls_back_to_server_now(self, student_client, exam_setup):
        session = exam_setup["session"]
        student_client.post(_url(session.id), {
            "events": [{"event_type": "tab_switch"}],
        }, format="json")
        log = ActivityLog.objects.get(session=session)
        assert abs((timezone.now() - log.occurred_at).total_seconds()) < 5

    def test_another_students_session_not_accessible(self, student_client, exam_setup):
        other_session = AssessmentSession.objects.create(
            assignment=exam_setup["assignment"], student_id=uuid.uuid4(), set=exam_setup["qset"],
            ends_at=timezone.now() + timedelta(hours=1),
        )
        resp = student_client.post(_url(other_session.id), {"events": [{"event_type": "tab_switch"}]}, format="json")
        assert resp.status_code == 404

    def test_admin_forbidden(self, admin_client, exam_setup):
        resp = admin_client.post(_url(exam_setup["session"].id), {"events": [{"event_type": "tab_switch"}]}, format="json")
        assert resp.status_code == 403

    def test_rejected_once_session_no_longer_in_progress(self, student_client, exam_setup):
        # Task 12.1's audit: this endpoint previously had no timer/status
        # revalidation at all, unlike every sibling mutating student
        # endpoint (answer autosave, submit).
        from assessments.models import SESSION_STATUS_SUBMITTED
        session = exam_setup["session"]
        session.status = SESSION_STATUS_SUBMITTED
        session.save(update_fields=["status"])
        resp = student_client.post(_url(session.id), {"events": [{"event_type": "tab_switch"}]}, format="json")
        assert resp.status_code == 403
        assert not ActivityLog.objects.filter(session=session).exists()

    def test_rejected_after_assignment_closed(self, student_client, exam_setup):
        from assessments.models import ASSIGNMENT_STATUS_CLOSED
        assignment = exam_setup["assignment"]
        assignment.status = ASSIGNMENT_STATUS_CLOSED
        assignment.save(update_fields=["status"])
        resp = student_client.post(_url(exam_setup["session"].id), {"events": [{"event_type": "tab_switch"}]}, format="json")
        assert resp.status_code == 403

    def test_rejected_after_ends_at(self, student_client, exam_setup):
        session = exam_setup["session"]
        session.ends_at = timezone.now() - timedelta(minutes=1)
        session.save(update_fields=["ends_at"])
        resp = student_client.post(_url(session.id), {"events": [{"event_type": "tab_switch"}]}, format="json")
        assert resp.status_code == 403

    def test_rate_limit_engages_after_threshold(self, student_client, exam_setup):
        session = exam_setup["session"]
        statuses = []
        for _ in range(25):
            resp = student_client.post(_url(session.id), {"events": [{"event_type": "tab_switch"}]}, format="json")
            statuses.append(resp.status_code)

        assert 429 in statuses
        # Requests before the limit engaged still succeeded — the whole
        # endpoint doesn't go dark, just gets capped.
        assert 201 in statuses

    def test_rate_limit_is_per_session_not_global(self, student_client, exam_setup):
        # A second session (same student, a different assignment/exam)
        # hitting its own endpoint must not be affected by the first
        # session's throttle state — the limit is keyed by session id.
        session_a = exam_setup["session"]
        paper_b = QuestionPaper.objects.create(
            institution_id=INSTITUTION_A, title="Second Paper", created_by=ADMIN_USER_ID,
        )
        qset_b = QuestionSet.objects.create(paper=paper_b, label="Set A", order=1)
        assignment_b = BatchAssignment.objects.create(
            paper=paper_b, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
        )
        session_b = AssessmentSession.objects.create(
            assignment=assignment_b, student_id=STUDENT_USER_ID, set=qset_b,
            ends_at=timezone.now() + timedelta(hours=1),
        )
        for _ in range(25):
            student_client.post(_url(session_a.id), {"events": [{"event_type": "tab_switch"}]}, format="json")

        # session_b's own throttle bucket is untouched by session_a's flood.
        resp = student_client.post(_url(session_b.id), {"events": [{"event_type": "tab_switch"}]}, format="json")
        assert resp.status_code == 201


class TestMalpracticeFlagging:
    def _finalize(self, session):
        from assessments.scoring import finalize_sessions
        from assessments.models import SESSION_STATUS_SUBMITTED
        finalize_sessions(AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_SUBMITTED)
        return ResultSummary.objects.get(session=session)

    def test_excessive_tab_switches_flags_session(self, exam_setup):
        session = exam_setup["session"]
        for _ in range(6):  # threshold is > 5
            ActivityLog.objects.create(session=session, event_type=ACTIVITY_EVENT_TAB_SWITCH, occurred_at=timezone.now())

        result = self._finalize(session)
        assert result.malpractice_flag is True
        assert "tab_switch" in result.malpractice_reasons

    def test_tab_switches_at_threshold_does_not_flag(self, exam_setup):
        session = exam_setup["session"]
        for _ in range(5):  # exactly at threshold, not over
            ActivityLog.objects.create(session=session, event_type=ACTIVITY_EVENT_TAB_SWITCH, occurred_at=timezone.now())

        result = self._finalize(session)
        assert "tab_switch" not in result.malpractice_reasons

    def test_excessive_fullscreen_exits_flags_session(self, exam_setup):
        session = exam_setup["session"]
        for _ in range(4):  # threshold is > 3
            ActivityLog.objects.create(session=session, event_type=ACTIVITY_EVENT_FULLSCREEN_EXIT, occurred_at=timezone.now())

        result = self._finalize(session)
        assert result.malpractice_flag is True
        assert "fullscreen_exit" in result.malpractice_reasons

    def test_fast_cadence_flags_session(self, exam_setup):
        session = exam_setup["session"]
        question = exam_setup["qset"].questions.first()
        AssessmentResponse.objects.create(session=session, question=question, selected_option_ids=[])
        # started_at is auto_now_add — backdate it to simulate a 1-second exam.
        AssessmentSession.objects.filter(pk=session.pk).update(started_at=timezone.now() - timedelta(seconds=1))

        result = self._finalize(session)
        assert result.malpractice_flag is True
        assert "cadence" in result.malpractice_reasons

    def test_normal_session_not_flagged(self, exam_setup):
        session = exam_setup["session"]
        question = exam_setup["qset"].questions.first()
        AssessmentResponse.objects.create(session=session, question=question, selected_option_ids=[])
        ActivityLog.objects.create(session=session, event_type=ACTIVITY_EVENT_COPY, occurred_at=timezone.now())
        # A realistic exam duration — without this, the session finalizes
        # within milliseconds of the fixture creating it, which itself
        # would trip the cadence threshold (a false positive of the test,
        # not of the flagging logic — see test_fast_cadence_flags_session
        # for the deliberate version of this same backdating).
        AssessmentSession.objects.filter(pk=session.pk).update(started_at=timezone.now() - timedelta(minutes=5))

        result = self._finalize(session)
        assert result.malpractice_flag is False
        assert result.malpractice_reasons == []

    def test_multiple_thresholds_all_reasons_listed(self, exam_setup):
        session = exam_setup["session"]
        for _ in range(6):
            ActivityLog.objects.create(session=session, event_type=ACTIVITY_EVENT_TAB_SWITCH, occurred_at=timezone.now())
        for _ in range(4):
            ActivityLog.objects.create(session=session, event_type=ACTIVITY_EVENT_FULLSCREEN_EXIT, occurred_at=timezone.now())

        result = self._finalize(session)
        assert set(result.malpractice_reasons) == {"tab_switch", "fullscreen_exit"}

    def test_unanswered_session_cadence_not_evaluated(self, exam_setup):
        # No AssessmentResponse rows at all — cadence can't be computed
        # (division by zero avoided), and must not spuriously flag.
        session = exam_setup["session"]
        result = self._finalize(session)
        assert "cadence" not in result.malpractice_reasons

    def test_new_transparency_event_types_never_count_toward_flagging(self, exam_setup):
        # question_answered/changed, screenshot_attempt, connection_lost,
        # and admin_extended_time (2026-08-18) are visibility-only —
        # _compute_malpractice only ever counts tab_switch/fullscreen_exit
        # rows specifically, so a session with many of these new event
        # types (even more than the tab_switch/fullscreen_exit thresholds)
        # must still come back clean.
        session = exam_setup["session"]
        question = exam_setup["qset"].questions.first()
        AssessmentResponse.objects.create(session=session, question=question, selected_option_ids=[])
        AssessmentSession.objects.filter(pk=session.pk).update(started_at=timezone.now() - timedelta(minutes=5))
        for event_type, metadata in [
            ("question_answered", {"question_number": 1}),
            ("question_answer_changed", {"question_number": 1}),
            ("screenshot_attempt", {}),
            ("connection_lost", {"duration_seconds": 30}),
            ("admin_extended_time", {"added_minutes": 15}),
        ]:
            for _ in range(6):  # deliberately over both real thresholds
                ActivityLog.objects.create(session=session, event_type=event_type, occurred_at=timezone.now(), metadata=metadata)

        result = self._finalize(session)
        assert result.malpractice_flag is False
        assert result.malpractice_reasons == []


class TestActivityLogLoad:
    def test_1000_sessions_20_events_each_sustains_ingestion(self, db, exam_setup):
        # Matches the DB write path every real ingestion call goes through
        # (ActivityLog.objects.bulk_create in the view) at the volume the
        # spec describes: 1,000 concurrent exam-takers each generating
        # ~20 anti-cheat events over the exam.
        import time

        assignment, qset = exam_setup["assignment"], exam_setup["qset"]
        sessions = AssessmentSession.objects.bulk_create([
            AssessmentSession(
                assignment=assignment, student_id=uuid.uuid4(), set=qset,
                ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_IN_PROGRESS,
            )
            for _ in range(1000)
        ])

        events = [
            ActivityLog(session=s, event_type=ACTIVITY_EVENT_COPY, occurred_at=timezone.now())
            for s in sessions for _ in range(20)
        ]

        start = time.monotonic()
        ActivityLog.objects.bulk_create(events)
        elapsed = time.monotonic() - start

        assert ActivityLog.objects.filter(session__assignment=assignment).count() == 20000
        assert elapsed < 30, f"bulk ingestion of 20,000 events took {elapsed:.1f}s"

    def test_endpoint_handles_repeated_real_requests_without_degrading(self, student_client, exam_setup):
        # A smaller-scale check of the actual HTTP endpoint itself (not
        # just the bulk_create path) — confirms the view stays correct
        # across many sequential real calls, not just fast in aggregate.
        session = exam_setup["session"]
        for _ in range(15):  # under the 20/min throttle so none are rejected
            resp = student_client.post(_url(session.id), {
                "events": [{"event_type": "copy"} for _ in range(20)],
            }, format="json")
            assert resp.status_code == 201
            assert resp.json()["data"]["logged"] == 20

        assert ActivityLog.objects.filter(session=session).count() == 300
