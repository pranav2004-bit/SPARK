import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.db import connection
from django.db.utils import OperationalError
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayStudentSetAllocation, EssayAttempt,
    EssayMalpracticeEvent,
    ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_SCHEDULED, ASSIGNMENT_STATUS_CLOSED,
    ATTEMPT_STATUS_IN_PROGRESS, ATTEMPT_STATUS_SUBMITTED,
)
from essays.views import StudentEssayAttemptStartView
from core.authentication import JWTUser

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


def _make_live_assignment_with_allocation(word_limit=500, time_limit=30):
    paper = EssayPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(
        set=eset, question_text="Describe a challenge.", llm_rubric_prompt="Secret rubric — never leak.",
        word_limit=word_limit, time_limit_minutes=time_limit,
    )
    assignment = EssayAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        status=ASSIGNMENT_STATUS_LIVE, created_by=ADMIN_USER_ID,
    )
    EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=STUDENT_USER_ID, set=eset)
    return assignment, eset


@pytest.mark.django_db
class TestStudentEssayAssignmentList:
    def test_lists_allocated_assignment(self, student_client):
        assignment, _ = _make_live_assignment_with_allocation()
        resp = student_client.get("/api/essay/student/assignments/")
        assert resp.status_code == 200
        assert len(resp.data["data"]) == 1
        assert resp.data["data"][0]["assignment_id"] == str(assignment.id)
        assert resp.data["data"][0]["attempt_status"] is None

    def test_unallocated_student_sees_nothing(self, student_client):
        _make_live_assignment_with_allocation()
        # A different student, never allocated.
        from rest_framework_simplejwt.tokens import RefreshToken
        class FakeUser:
            pk = uuid.uuid4()
            id = pk
        refresh = RefreshToken.for_user(FakeUser())
        refresh["role"] = "student"
        refresh["institution_id"] = str(INSTITUTION_A)
        student_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        resp = student_client.get("/api/essay/student/assignments/")
        assert resp.status_code == 200
        assert resp.data["data"] == []


@pytest.mark.django_db
class TestStudentEssayAttemptStart:
    def test_start_creates_attempt_with_correct_ends_at(self, student_client):
        assignment, eset = _make_live_assignment_with_allocation(time_limit=30)
        resp = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        assert resp.status_code == 201, resp.data
        assert resp.data["data"]["status"] == ATTEMPT_STATUS_IN_PROGRESS

        attempt = EssayAttempt.objects.get(pk=resp.data["data"]["attempt_id"])
        # ends_at should be ~30 minutes out, capped by global_expire_time (3h away) — so ~30 min wins.
        delta = (attempt.ends_at - timezone.now()).total_seconds()
        assert 29 * 60 < delta < 31 * 60

    def test_start_is_idempotent_resume(self, student_client):
        assignment, _ = _make_live_assignment_with_allocation()
        first = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        second = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        assert first.status_code == 201
        assert second.status_code == 200
        assert first.data["data"]["attempt_id"] == second.data["data"]["attempt_id"]
        assert "resumed" in second.data["message"].lower()

    def test_start_rejected_when_not_allocated(self, student_client):
        paper = EssayPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
        eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
        EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
        assignment = EssayAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            status=ASSIGNMENT_STATUS_LIVE, created_by=ADMIN_USER_ID,
        )
        # No allocation created for this student.
        resp = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        assert resp.status_code == 404

    def test_start_rejected_when_not_live(self, student_client):
        paper = EssayPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
        eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
        EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
        assignment = EssayAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            status=ASSIGNMENT_STATUS_SCHEDULED, created_by=ADMIN_USER_ID,
        )
        EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=STUDENT_USER_ID, set=eset)
        resp = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        assert resp.status_code == 403

    def test_start_rejected_when_expired(self, student_client):
        paper = EssayPaper.objects.create(institution_id=INSTITUTION_A, title="P", created_by=ADMIN_USER_ID)
        eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
        EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
        assignment = EssayAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() - timedelta(minutes=1),
            status=ASSIGNMENT_STATUS_LIVE, created_by=ADMIN_USER_ID,
        )
        EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=STUDENT_USER_ID, set=eset)
        resp = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestStudentEssayAttemptDetail:
    def test_detail_never_leaks_rubric(self, student_client):
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]

        resp = student_client.get(f"/api/essay/student/attempts/{attempt_id}/")
        assert resp.status_code == 200
        assert "llm_rubric_prompt" not in resp.data["data"]["question"]
        assert resp.data["data"]["question"]["question_text"] == "Describe a challenge."

    def test_cross_student_detail_is_404(self, student_client):
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]

        from rest_framework_simplejwt.tokens import RefreshToken
        class FakeUser:
            pk = uuid.uuid4()
            id = pk
        refresh = RefreshToken.for_user(FakeUser())
        refresh["role"] = "student"
        refresh["institution_id"] = str(INSTITUTION_A)
        student_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        resp = student_client.get(f"/api/essay/student/attempts/{attempt_id}/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestStudentEssayAutosave:
    def _start(self, student_client, **kwargs):
        assignment, eset = _make_live_assignment_with_allocation(**kwargs)
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        return assignment, eset, start.data["data"]["attempt_id"]

    def test_autosave_saves_draft(self, student_client):
        _, _, attempt_id = self._start(student_client)
        resp = student_client.put(f"/api/essay/student/attempts/{attempt_id}/autosave/", {"draft_response": "My essay so far."}, format="json")
        assert resp.status_code == 200
        attempt = EssayAttempt.objects.get(pk=attempt_id)
        assert attempt.draft_response == "My essay so far."

    def test_autosave_rejects_over_word_limit(self, student_client):
        _, _, attempt_id = self._start(student_client, word_limit=5)
        resp = student_client.put(
            f"/api/essay/student/attempts/{attempt_id}/autosave/",
            {"draft_response": "one two three four five six seven"}, format="json",
        )
        assert resp.status_code == 400

    def test_autosave_rejected_after_submit(self, student_client):
        _, _, attempt_id = self._start(student_client)
        student_client.post(f"/api/essay/student/attempts/{attempt_id}/submit/")
        resp = student_client.put(f"/api/essay/student/attempts/{attempt_id}/autosave/", {"draft_response": "too late"}, format="json")
        assert resp.status_code == 403

    def test_autosave_rejected_when_assignment_closed(self, student_client):
        assignment, _, attempt_id = self._start(student_client)
        assignment.status = ASSIGNMENT_STATUS_CLOSED
        assignment.save(update_fields=["status"])
        resp = student_client.put(f"/api/essay/student/attempts/{attempt_id}/autosave/", {"draft_response": "x"}, format="json")
        assert resp.status_code == 403

    def test_autosave_rejected_past_real_deadline_even_with_forged_client_clock(self, student_client):
        # The exact "timer-spoofing" scenario named in LIVETRACKER3_V1.md
        # Task 4.1's own Testing checklist: the attempt is still
        # IN_PROGRESS (the beat sweep hasn't run yet), but its real ends_at
        # has already passed. A client-tampered clock can't matter here —
        # strip_client_timestamps() throws away any client-sent time field
        # before it ever reaches the server, so the server's own
        # attempt_is_writable() check (comparing timezone.now() to the
        # stored ends_at) is the only thing that decides this, and it must
        # reject the write regardless of what the client claims the time is.
        _, _, attempt_id = self._start(student_client)
        attempt = EssayAttempt.objects.get(pk=attempt_id)
        attempt.ends_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["ends_at"])

        resp = student_client.put(
            f"/api/essay/student/attempts/{attempt_id}/autosave/",
            {"draft_response": "too late", "timestamp": "2099-01-01T00:00:00Z"}, format="json",
        )
        assert resp.status_code == 403
        attempt.refresh_from_db()
        assert attempt.draft_response == ""  # the forged-clock write never landed
        assert attempt.status == ATTEMPT_STATUS_IN_PROGRESS  # still awaiting the sweep, not silently auto-finalized by this call

    def test_autosave_ignores_client_timestamp_fields(self, student_client):
        _, _, attempt_id = self._start(student_client)
        resp = student_client.put(
            f"/api/essay/student/attempts/{attempt_id}/autosave/",
            {"draft_response": "text", "ends_at": "2000-01-01T00:00:00Z"}, format="json",
        )
        assert resp.status_code == 200
        attempt = EssayAttempt.objects.get(pk=attempt_id)
        assert attempt.ends_at.year != 2000  # forged timestamp never applied


@pytest.mark.django_db
class TestStudentEssaySubmit:
    def test_submit_finalizes_attempt(self, student_client):
        assignment, eset = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]

        resp = student_client.post(f"/api/essay/student/attempts/{attempt_id}/submit/", {"draft_response": "Final answer."}, format="json")
        assert resp.status_code == 200
        assert resp.data["data"]["status"] == ATTEMPT_STATUS_SUBMITTED

        attempt = EssayAttempt.objects.get(pk=attempt_id)
        assert attempt.draft_response == "Final answer."
        assert attempt.status == ATTEMPT_STATUS_SUBMITTED

    def test_direct_api_bypass_near_instant_submit_flagged_cadence(self, student_client):
        # Task 15.2's own testing requirement: a direct-API-bypass
        # simulation (never loading the UI — the exact shape of a
        # scripted/automated submission, AT9) must be correctly flagged.
        # start-attempt and submit called back-to-back through the real
        # HTTP endpoints, no artificial delay — genuinely exercises the
        # cadence signal end-to-end (essays.scoring.CADENCE_THRESHOLD_
        # SECONDS = 3), not just the lower-level finalize_attempts() unit
        # tests in test_scoring.py.
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]

        resp = student_client.post(f"/api/essay/student/attempts/{attempt_id}/submit/", {"draft_response": "x"}, format="json")
        assert resp.status_code == 200

        attempt = EssayAttempt.objects.get(pk=attempt_id)
        assert attempt.malpractice_flag is True
        assert "cadence" in attempt.malpractice_reasons

    def test_double_submit_second_call_rejected(self, student_client):
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]

        first = student_client.post(f"/api/essay/student/attempts/{attempt_id}/submit/")
        second = student_client.post(f"/api/essay/student/attempts/{attempt_id}/submit/")
        assert first.status_code == 200
        assert second.status_code == 403

    def test_submit_rejected_on_redis_outage_fail_closed(self, student_client):
        # Task 5.1's own testing checklist: a Redis outage during
        # submission-creation must reject (fail CLOSED), not let an
        # unmetered request through — the deliberate exception to this
        # platform's usual fail-open throttle policy (ADR 003 Decision 8 /
        # ADR 004 Section 5, core/throttling_resilience.py's
        # FailClosedThrottleMixin). Simulated by making the underlying
        # cache raise RedisError, since the test settings' LocMemCache
        # backend never raises it for real.
        import redis.exceptions
        from unittest.mock import patch

        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]

        with patch("django.core.cache.cache.get", side_effect=redis.exceptions.RedisError("connection refused")):
            resp = student_client.post(f"/api/essay/student/attempts/{attempt_id}/submit/", {"draft_response": "x"}, format="json")

        assert resp.status_code == 429
        attempt = EssayAttempt.objects.get(pk=attempt_id)
        assert attempt.status == ATTEMPT_STATUS_IN_PROGRESS  # never finalized

    def test_repeated_rapid_submit_calls_eventually_throttled(self, student_client):
        # Task 15.2's own testing requirement, second half: a direct-API-
        # bypass simulation must be correctly throttled, not just flagged.
        # DRF's throttle check runs in dispatch(), before the view's own
        # business logic (the "already terminal" 403 an 11th call would
        # otherwise hit) — so hammering this endpoint past
        # DEFAULT_THROTTLE_RATES["essay_submit"] (10/min) genuinely returns
        # 429, exercising the real EssaySubmitRateThrottle, not a mock.
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]

        statuses = [
            student_client.post(f"/api/essay/student/attempts/{attempt_id}/submit/", {"draft_response": "x"}, format="json").status_code
            for _ in range(11)
        ]
        assert 429 in statuses
        assert statuses[-1] == 429  # the 11th call, past the 10/min ceiling

    def test_manual_submit_rejected_past_real_deadline_before_sweep_runs(self, student_client):
        # Same "timer-spoofing" scenario as autosave's equivalent test, but
        # for the manual-submit path: a student can't force a submit through
        # past the real deadline just because the beat sweep (every 20s)
        # hasn't gotten to this attempt yet. attempt_is_writable() gates
        # StudentEssaySubmitView exactly like it gates autosave — this
        # attempt must stay IN_PROGRESS, untouched, until the sweep (or
        # nothing, if it's already past) finalizes it as AUTO_SUBMITTED.
        assignment, eset = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]

        attempt = EssayAttempt.objects.get(pk=attempt_id)
        attempt.ends_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["ends_at"])

        resp = student_client.post(
            f"/api/essay/student/attempts/{attempt_id}/submit/",
            {"draft_response": "sneaking this in late"}, format="json",
        )
        assert resp.status_code == 403
        attempt.refresh_from_db()
        assert attempt.status == ATTEMPT_STATUS_IN_PROGRESS
        assert attempt.draft_response == ""


@pytest.mark.django_db
class TestStudentEssayMalpracticeEvents:
    def test_bulk_create_logs_events(self, student_client):
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]

        resp = student_client.post(f"/api/essay/student/attempts/{attempt_id}/malpractice-events/", {
            "events": [
                {"event_type": "tab_switch", "occurred_at": timezone.now().isoformat()},
                {"event_type": "paste_attempt", "occurred_at": timezone.now().isoformat()},
            ]
        }, format="json")
        assert resp.status_code == 201
        assert resp.data["data"]["logged"] == 2
        assert EssayMalpracticeEvent.objects.filter(attempt_id=attempt_id).count() == 2

    def test_unknown_event_type_skipped_not_fatal(self, student_client):
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]

        resp = student_client.post(f"/api/essay/student/attempts/{attempt_id}/malpractice-events/", {
            "events": [{"event_type": "not_a_real_type", "occurred_at": timezone.now().isoformat()}]
        }, format="json")
        assert resp.status_code == 201
        assert resp.data["data"]["logged"] == 0

    def test_empty_events_list_rejected(self, student_client):
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]
        resp = student_client.post(f"/api/essay/student/attempts/{attempt_id}/malpractice-events/", {"events": []}, format="json")
        assert resp.status_code == 400


@pytest.mark.django_db
class TestStudentEssayServerTime:
    def test_returns_server_time_and_active_attempt(self, student_client):
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]

        resp = student_client.get("/api/essay/student/server-time/")
        assert resp.status_code == 200
        assert "server_time" in resp.data["data"]
        assert resp.data["data"]["attempt_id"] == attempt_id

    def test_no_active_attempt_omits_attempt_fields(self, student_client):
        resp = student_client.get("/api/essay/student/server-time/")
        assert resp.status_code == 200
        assert "attempt_id" not in resp.data["data"]


def _swap_to_a_different_student(client):
    """Re-credentials an already-authenticated student_client as a
    brand-new, unrelated student — same inline pattern already
    established by test_cross_student_detail_is_404, factored out since
    Task 15.1's own audit round needs it repeated across autosave/submit/
    malpractice-events."""
    from rest_framework_simplejwt.tokens import RefreshToken
    class FakeUser:
        pk = uuid.uuid4()
        id = pk
    refresh = RefreshToken.for_user(FakeUser())
    refresh["role"] = "student"
    refresh["institution_id"] = str(INSTITUTION_A)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


@pytest.mark.django_db
class TestStudentEndpointsSecurityIsolation:
    """Task 15.1's own IDOR & Cross-Institution Audit: a coverage-mapping
    pass found autosave/submit/malpractice-events had zero cross-student
    or wrong-role tests at all, and server-time/assignments-list/
    start-attempt/attempt-detail had no wrong-role test. Every view was
    read directly first — all already filter by
    student_id=request.user.id (get_object_or_404(EssayAttempt...,
    student_id=request.user.id)) — this closes a test-coverage gap, not
    a live vulnerability."""

    def test_server_time_rejects_wrong_role(self, admin_client, anon_client):
        assert admin_client.get("/api/essay/student/server-time/").status_code == 403
        assert anon_client.get("/api/essay/student/server-time/").status_code in (401, 403)

    def test_assignment_list_rejects_wrong_role(self, admin_client, anon_client):
        assert admin_client.get("/api/essay/student/assignments/").status_code == 403
        assert anon_client.get("/api/essay/student/assignments/").status_code in (401, 403)

    def test_start_attempt_rejects_wrong_role(self, admin_client, anon_client):
        assignment, _ = _make_live_assignment_with_allocation()
        url = f"/api/essay/student/assignments/{assignment.id}/start-attempt/"
        assert admin_client.post(url).status_code == 403
        assert anon_client.post(url).status_code in (401, 403)

    def test_attempt_detail_rejects_wrong_role(self, student_client, admin_client, anon_client):
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        url = f"/api/essay/student/attempts/{start.data['data']['attempt_id']}/"
        assert admin_client.get(url).status_code == 403
        assert anon_client.get(url).status_code in (401, 403)

    def test_autosave_rejects_cross_student_and_wrong_role(self, student_client, admin_client, anon_client):
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]
        url = f"/api/essay/student/attempts/{attempt_id}/autosave/"

        other = _swap_to_a_different_student(student_client)
        resp = other.put(url, {"draft_response": "hijacked"}, format="json")
        assert resp.status_code == 404
        assert EssayAttempt.objects.get(pk=attempt_id).draft_response != "hijacked"

        assert admin_client.put(url, {"draft_response": "x"}, format="json").status_code == 403
        assert anon_client.put(url, {"draft_response": "x"}, format="json").status_code in (401, 403)

    def test_submit_rejects_cross_student_and_wrong_role(self, student_client, admin_client, anon_client):
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]
        url = f"/api/essay/student/attempts/{attempt_id}/submit/"

        other = _swap_to_a_different_student(student_client)
        resp = other.post(url)
        assert resp.status_code == 404
        assert EssayAttempt.objects.get(pk=attempt_id).status == ATTEMPT_STATUS_IN_PROGRESS

        assert admin_client.post(url).status_code == 403
        assert anon_client.post(url).status_code in (401, 403)

    def test_malpractice_events_rejects_cross_student_and_wrong_role(self, student_client, admin_client, anon_client):
        assignment, _ = _make_live_assignment_with_allocation()
        start = student_client.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
        attempt_id = start.data["data"]["attempt_id"]
        url = f"/api/essay/student/attempts/{attempt_id}/malpractice-events/"
        payload = {"events": [{"event_type": "tab_switch"}]}

        other = _swap_to_a_different_student(student_client)
        resp = other.post(url, payload, format="json")
        assert resp.status_code == 404
        assert not EssayAttempt.objects.get(pk=attempt_id).malpractice_events.exists()

        assert admin_client.post(url, payload, format="json").status_code == 403
        assert anon_client.post(url, payload, format="json").status_code in (401, 403)


def _retry_on_sqlite_lock(fn, retries=400, delay=0.05):
    """Same SQLite-vs-Postgres locking-granularity accommodation as
    test_concurrency.py's own identical helper — real Postgres (this
    service's actual dev/prod DB) doesn't serialize writes to different
    rows this way; this only works around the test DB's coarser locking
    getting in the way of observing the real invariant."""
    last_exc = None
    for _ in range(retries):
        try:
            return fn()
        except OperationalError as exc:
            if "locked" not in str(exc):
                raise
            last_exc = exc
            connection.close()
            time.sleep(delay)
    raise last_exc


def _student_jwt_user(user_id=STUDENT_USER_ID, institution_id=INSTITUTION_A):
    return JWTUser({
        "user_id": user_id, "role": "student", "student_id": str(user_id),
        "institution_id": str(institution_id), "is_profile_completed": True,
    })


@pytest.mark.django_db
class TestStartAttemptGenuineConcurrency:
    """Task 15.1's own re-verification subtask: every idempotency
    guarantee re-checked under real OS-thread concurrency, not just
    sequential simulation — the exact discipline that found a real bug
    in assessment-service's own Task 12.1 audit. StudentEssayAttemptStartView
    has never been concurrency-tested before this round: its own
    unique_together=[("assignment", "student_id")] + IntegrityError
    catch-and-resume was only ever exercised sequentially (
    test_start_is_idempotent_resume calls it twice on one thread/
    connection, which proves idempotency, not safety under genuine
    concurrent execution — the same distinction this task's own
    reference methodology draws). The real hazard: a double-tap or a
    flaky-network client auto-retry sending two genuinely simultaneous
    start-attempt requests must still produce exactly one EssayAttempt,
    never two, never a 500."""

    def test_ten_concurrent_start_attempt_calls_produce_exactly_one_attempt(self, transactional_db):
        assignment, _ = _make_live_assignment_with_allocation()
        factory = APIRequestFactory()

        def worker(_):
            try:
                def call():
                    request = factory.post(f"/api/essay/student/assignments/{assignment.id}/start-attempt/")
                    force_authenticate(request, user=_student_jwt_user())
                    return StudentEssayAttemptStartView.as_view()(request, pk=assignment.id)
                return _retry_on_sqlite_lock(call)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(worker, range(10)))

        # Every response must be a genuine success (201 the one genuine
        # creator, 200 every resumer) — never a 500 from an uncaught
        # IntegrityError racing past the existing catch.
        assert all(r.status_code in (200, 201) for r in responses), [r.status_code for r in responses]
        assert EssayAttempt.objects.filter(assignment=assignment, student_id=STUDENT_USER_ID).count() == 1
        attempt_ids = {r.data["data"]["attempt_id"] for r in responses}
        assert len(attempt_ids) == 1  # every racer agrees on the same single attempt
