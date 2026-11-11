"""
test_admin_llm_controls.py — Phase 7, Task 7.1's own testing checklist:
retrigger happy path + audit-log correctness, trace view accuracy,
analytics numbers verified against a known fixture, manual-override
validation (score out of range rejected, missing reason rejected, DLQ
entry correctly marked resolved, submission status correctly advances).
"""
import time
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from django.db import connection
from django.db.utils import OperationalError
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt, EssaySubmission, EssayScore,
    EssayLLMTrace, EssayFailedJob, EssaySubmissionEvent, ATTEMPT_STATUS_SUBMITTED,
    SUBMISSION_STATUS_PENDING, SUBMISSION_STATUS_LLM_PROCESSING,
    SUBMISSION_STATUS_LLM_COMPLETE, SUBMISSION_STATUS_LLM_FAILED, SUBMISSION_STATUS_REPORT_READY,
    SUBMISSION_EVENT_ADMIN_RETRIGGER, SUBMISSION_EVENT_ADMIN_OVERRIDE,
    EVALUATED_BY_ADMIN, EVALUATED_BY_LLM,
)
from essays.tasks import _transition_submission_status, _record_dlq
from essays.views import AdminSubmissionScoreOverrideView, AdminSubmissionRetriggerView
from core.authentication import JWTUser

from .conftest import INSTITUTION_A, INSTITUTION_B, ADMIN_USER_ID, ADMIN_B_USER_ID


def _admin_jwt_user(user_id=ADMIN_USER_ID, institution_id=INSTITUTION_A):
    return JWTUser({
        "user_id": user_id, "role": "admin", "email": "admin@test.com",
        "institution_id": str(institution_id), "is_profile_completed": True,
    })


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


def _make_submission(
    *, institution_id=INSTITUTION_A, status=SUBMISSION_STATUS_PENDING,
    draft_response="An essay response about history.",
):
    paper = EssayPaper.objects.create(institution_id=institution_id, title="P", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
    assignment = EssayAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=institution_id,
        global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
    )
    attempt = EssayAttempt.objects.create(
        assignment=assignment, student_id=uuid.uuid4(), set=eset,
        ends_at=timezone.now() + timedelta(hours=1), draft_response=draft_response,
        status=ATTEMPT_STATUS_SUBMITTED,
    )
    submission = EssaySubmission.objects.create(attempt=attempt)
    if status != SUBMISSION_STATUS_PENDING:
        EssaySubmission.objects.filter(pk=submission.pk).update(status=status)
        submission.refresh_from_db()
    return submission


def _make_failed_submission():
    """A submission genuinely stuck in the DLQ — the exact precondition
    AdminSubmissionScoreOverrideView requires."""
    submission = _make_submission(status=SUBMISSION_STATUS_LLM_PROCESSING)
    _record_dlq("evaluate_essay", [str(submission.id)], {}, RuntimeError("content policy violation"), attempts=3)
    _transition_submission_status(submission, SUBMISSION_STATUS_LLM_FAILED, expected_status=SUBMISSION_STATUS_LLM_PROCESSING)
    submission.refresh_from_db()
    return submission


@pytest.mark.django_db
class TestRetrigger:
    def test_retrigger_happy_path(self, admin_client):
        submission = _make_failed_submission()
        with patch("essays.tasks.evaluate_essay") as mock_evaluate:
            resp = admin_client.post(
                f"/api/essay/admin/submissions/{submission.id}/retrigger/",
                {"reason": "OpenAI content-policy false positive, essay is legitimate."}, format="json",
            )
        assert resp.status_code == 200
        # Task 17.2 — correlation_id is the middleware's own per-request
        # generated id (a fresh UUID per test client call, not assertable
        # as a literal), so this checks the call shape, not the exact value.
        mock_evaluate.delay.assert_called_once()
        assert mock_evaluate.delay.call_args.args == (str(submission.id),)
        assert mock_evaluate.delay.call_args.kwargs.get("correlation_id")
        submission.refresh_from_db()
        assert submission.status == SUBMISSION_STATUS_LLM_PROCESSING

    def test_retrigger_deletes_existing_score_and_trace(self, admin_client):
        submission = _make_failed_submission()
        EssayScore.objects.create(submission=submission, score=2, feedback={"overall": "wrong"})
        EssayLLMTrace.objects.create(submission=submission, prompt_messages=[], raw_response="{}")

        with patch("essays.tasks.evaluate_essay"):
            admin_client.post(
                f"/api/essay/admin/submissions/{submission.id}/retrigger/",
                {"reason": "Score looks wrong, re-evaluating."}, format="json",
            )

        assert not EssayScore.objects.filter(submission=submission).exists()
        assert not EssayLLMTrace.objects.filter(submission=submission).exists()

    def test_retrigger_resolves_unresolved_dlq_entry(self, admin_client):
        submission = _make_failed_submission()
        with patch("essays.tasks.evaluate_essay"):
            admin_client.post(
                f"/api/essay/admin/submissions/{submission.id}/retrigger/",
                {"reason": "Retrying after quota was increased."}, format="json",
            )
        entry = EssayFailedJob.objects.get(task_name="evaluate_essay", args=[str(submission.id)])
        assert entry.resolved_at is not None

    def test_retrigger_writes_audit_log_with_admin_and_reason(self, admin_client):
        submission = _make_failed_submission()
        with patch("essays.tasks.evaluate_essay"):
            admin_client.post(
                f"/api/essay/admin/submissions/{submission.id}/retrigger/",
                {"reason": "Manual re-run per student appeal."}, format="json",
            )
        event = EssaySubmissionEvent.objects.get(submission=submission, event_type=SUBMISSION_EVENT_ADMIN_RETRIGGER)
        assert event.reason == "Manual re-run per student appeal."
        assert str(event.admin_user_id) == str(ADMIN_USER_ID)

    def test_missing_reason_rejected(self, admin_client):
        submission = _make_failed_submission()
        resp = admin_client.post(f"/api/essay/admin/submissions/{submission.id}/retrigger/", {}, format="json")
        assert resp.status_code == 400

    def test_rejected_while_already_processing(self, admin_client):
        # Real gap found by this phase's own final-audit round: retriggering
        # a submission that's already LLM_PROCESSING (a genuine in-flight
        # evaluation, not a stale/failed one) used to dispatch a second,
        # fully concurrent evaluate_essay run for the same submission — a
        # real, separately-billed duplicate OpenAI API call (ET11).
        submission = _make_submission(status=SUBMISSION_STATUS_LLM_PROCESSING)
        with patch("essays.tasks.evaluate_essay") as mock_evaluate:
            resp = admin_client.post(
                f"/api/essay/admin/submissions/{submission.id}/retrigger/",
                {"reason": "Trying to retrigger a mid-flight evaluation."}, format="json",
            )
        assert resp.status_code == 409
        mock_evaluate.delay.assert_not_called()
        submission.refresh_from_db()
        assert submission.status == SUBMISSION_STATUS_LLM_PROCESSING

    def test_allowed_while_pending(self, admin_client):
        # PENDING is deliberately still allowed through — nothing is
        # actually in flight yet, so no duplicate-call risk exists there,
        # unlike LLM_PROCESSING above.
        submission = _make_submission(status=SUBMISSION_STATUS_PENDING)
        with patch("essays.tasks.evaluate_essay") as mock_evaluate:
            resp = admin_client.post(
                f"/api/essay/admin/submissions/{submission.id}/retrigger/",
                {"reason": "Forcing an early dispatch."}, format="json",
            )
        assert resp.status_code == 200
        mock_evaluate.delay.assert_called_once()
        assert mock_evaluate.delay.call_args.args == (str(submission.id),)
        assert mock_evaluate.delay.call_args.kwargs.get("correlation_id")

    def test_two_concurrent_retriggers_of_the_same_submission_only_dispatch_once(self, transactional_db):
        # Real gap found by this phase's own second final-audit round: the
        # original fix above (`if submission.status == LLM_PROCESSING`)
        # is a read-then-write check, not an atomic compare-and-swap — it
        # closes "retrigger something already processing" but NOT two
        # admins retriggering the SAME LLM_FAILED submission at the exact
        # same instant, since both can read the pre-check status before
        # either commits. Only real, concurrently-executing threads
        # racing the same database expose this (a sequential double-call
        # can't reproduce it: the second call would just see the first
        # admin's already-committed LLM_PROCESSING status and correctly
        # 409 on the ordinary check). Fixed by making the status
        # transition itself the guard (a conditional UPDATE, the same CAS
        # pattern already used elsewhere in this module).
        submission = _make_submission(status=SUBMISSION_STATUS_LLM_FAILED)
        factory = APIRequestFactory()

        with patch("essays.tasks.evaluate_essay") as mock_evaluate:
            def worker(_):
                try:
                    def call():
                        request = factory.post(
                            f"/api/essay/admin/submissions/{submission.id}/retrigger/",
                            {"reason": "concurrent retrigger race test"}, format="json",
                        )
                        force_authenticate(request, user=_admin_jwt_user())
                        return AdminSubmissionRetriggerView.as_view()(request, pk=submission.id)
                    return _retry_on_sqlite_lock(call)
                finally:
                    connection.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(worker, range(2)))

            statuses = sorted(r.status_code for r in responses)
            assert statuses == [200, 409]
            assert mock_evaluate.delay.call_count == 1
            submission.refresh_from_db()
            assert submission.status == SUBMISSION_STATUS_LLM_PROCESSING

    def test_blank_reason_rejected(self, admin_client):
        submission = _make_failed_submission()
        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/retrigger/", {"reason": "   "}, format="json",
        )
        assert resp.status_code == 400

    def test_institution_isolated_404(self, admin_client, admin_b_client):
        submission = _make_failed_submission()
        resp = admin_b_client.post(
            f"/api/essay/admin/submissions/{submission.id}/retrigger/", {"reason": "x"}, format="json",
        )
        assert resp.status_code == 404

    def test_student_role_rejected(self, student_client):
        submission = _make_failed_submission()
        resp = student_client.post(
            f"/api/essay/admin/submissions/{submission.id}/retrigger/", {"reason": "x"}, format="json",
        )
        assert resp.status_code == 403


@pytest.mark.django_db
class TestTraceView:
    def test_returns_the_recorded_trace(self, admin_client):
        submission = _make_submission(status=SUBMISSION_STATUS_LLM_COMPLETE)
        EssayScore.objects.create(submission=submission, score=8, feedback={"overall": "Good."})
        EssayLLMTrace.objects.create(
            submission=submission,
            prompt_messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            raw_response='{"score": 8, "feedback": {"overall": "Good."}}',
            request_id="chatcmpl-abc", model_used="gpt-4o-mini",
        )

        resp = admin_client.get(f"/api/essay/admin/submissions/{submission.id}/trace/")
        assert resp.status_code == 200
        data = resp.data["data"]
        assert data["request_id"] == "chatcmpl-abc"
        assert data["model_used"] == "gpt-4o-mini"
        assert data["raw_response"] == '{"score": 8, "feedback": {"overall": "Good."}}'
        assert len(data["prompt_messages"]) == 2

    def test_no_trace_recorded_returns_null_not_error(self, admin_client):
        # success_response(data=None, ...) omits the "data" key entirely
        # by this platform's own established convention (core/responses.py)
        # — not present-but-null.
        submission = _make_submission(status=SUBMISSION_STATUS_LLM_FAILED)
        resp = admin_client.get(f"/api/essay/admin/submissions/{submission.id}/trace/")
        assert resp.status_code == 200
        assert "data" not in resp.data
        assert "No LLM trace" in resp.data["message"]

    def test_institution_isolated_404(self, admin_client, admin_b_client):
        submission = _make_submission()
        resp = admin_b_client.get(f"/api/essay/admin/submissions/{submission.id}/trace/")
        assert resp.status_code == 404

    def test_student_role_rejected(self, student_client):
        # Task 15.1's audit: this view's sibling endpoints
        # (retrigger/override-score) already had this test; trace/ was
        # missing it — a coverage gap, AdminSubmissionTraceView already
        # uses the shared IsAdminOrSuperAdmin permission class unchanged.
        submission = _make_submission()
        resp = student_client.get(f"/api/essay/admin/submissions/{submission.id}/trace/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestLLMAnalytics:
    def test_numbers_match_a_known_fixture(self, admin_client, settings):
        settings.OPENAI_MODEL = "gpt-4o-mini"
        s1 = _make_submission(status=SUBMISSION_STATUS_LLM_COMPLETE)
        EssayScore.objects.create(submission=s1, score=8, feedback={"overall": "x"})
        s2 = _make_submission(status=SUBMISSION_STATUS_LLM_COMPLETE)
        EssayScore.objects.create(submission=s2, score=6, feedback={"overall": "x"})
        s3 = _make_submission(status=SUBMISSION_STATUS_LLM_COMPLETE)
        EssayScore.objects.create(submission=s3, score=4, feedback={"overall": "x"})

        # One malformed-response DLQ entry (matched by error signature)...
        s4 = _make_submission(status=SUBMISSION_STATUS_LLM_FAILED)
        _record_dlq("evaluate_essay", [str(s4.id)], {}, Exception("Unexpected response shape: {}"), attempts=3)
        # ...and one permanent-error DLQ entry, which must NOT be counted
        # as a malformed-response failure.
        s5 = _make_submission(status=SUBMISSION_STATUS_LLM_FAILED)
        _record_dlq("evaluate_essay", [str(s5.id)], {}, Exception("content policy violation"), attempts=0)

        # Retriggering s4/s5 (not s1/s2/s3) — retrigger deletes any
        # existing score as part of clearing state for re-evaluation, so
        # retriggering a submission this fixture also wants counted in
        # evaluation_count/average_score would undermine that same
        # assertion; s4/s5 have no score to lose.
        with patch("essays.tasks.evaluate_essay"):
            admin_client.post(f"/api/essay/admin/submissions/{s4.id}/retrigger/", {"reason": "r1"}, format="json")
            admin_client.post(f"/api/essay/admin/submissions/{s5.id}/retrigger/", {"reason": "r2"}, format="json")

        resp = admin_client.get("/api/essay/admin/llm-controls/analytics/")
        assert resp.status_code == 200
        data = resp.data["data"]
        assert data["provider"] == "OpenAI"
        assert data["model"] == "gpt-4o-mini"
        assert data["evaluation_count"] == 3
        assert data["average_score"] == 6.0  # (8 + 6 + 4) / 3
        assert data["malformed_response_dlq_count"] == 1
        assert data["retrigger_count"] == 2

    def test_zero_evaluations_reports_null_average_not_error(self, admin_client):
        resp = admin_client.get("/api/essay/admin/llm-controls/analytics/")
        assert resp.status_code == 200
        assert resp.data["data"]["evaluation_count"] == 0
        assert resp.data["data"]["average_score"] is None

    def test_evaluation_count_is_institution_scoped(self, admin_client, admin_b_client):
        s1 = _make_submission(status=SUBMISSION_STATUS_LLM_COMPLETE, institution_id=INSTITUTION_A)
        EssayScore.objects.create(submission=s1, score=9, feedback={"overall": "x"})

        resp = admin_b_client.get("/api/essay/admin/llm-controls/analytics/")
        assert resp.data["data"]["evaluation_count"] == 0

    def test_student_role_rejected(self, student_client):
        resp = student_client.get("/api/essay/admin/llm-controls/analytics/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestScoreOverride:
    def test_override_happy_path(self, admin_client):
        submission = _make_failed_submission()
        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/override-score/",
            {"score": 7, "feedback": {"overall": "Solid, scored manually after repeated LLM failures."}, "reason": "LLM rejected content 3x, essay is legitimate."},
            format="json",
        )
        assert resp.status_code == 200
        score = EssayScore.objects.get(submission=submission)
        assert score.score == 7
        assert score.evaluated_by == EVALUATED_BY_ADMIN
        submission.refresh_from_db()
        # Phase 11: this view now auto-dispatches generate_essay_report
        # once it reaches LLM_COMPLETE (a real gap Phase 11's own audit
        # found — see AdminSubmissionScoreOverrideView's own comment on
        # this exact dispatch call, essays/views.py) — under
        # CELERY_TASK_ALWAYS_EAGER (test_settings.py) that runs
        # synchronously, so the terminal status here is REPORT_READY.
        assert submission.status == SUBMISSION_STATUS_REPORT_READY
        assert submission.report_html

    def test_override_resolves_dlq_entry(self, admin_client):
        submission = _make_failed_submission()
        admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/override-score/",
            {"score": 5, "feedback": {"overall": "ok"}, "reason": "manual recovery"}, format="json",
        )
        entry = EssayFailedJob.objects.get(task_name="evaluate_essay", args=[str(submission.id)])
        assert entry.resolved_at is not None

    def test_override_writes_audit_log(self, admin_client):
        submission = _make_failed_submission()
        admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/override-score/",
            {"score": 5, "feedback": {"overall": "ok"}, "reason": "manual recovery, see ticket #123"}, format="json",
        )
        event = EssaySubmissionEvent.objects.get(submission=submission, event_type=SUBMISSION_EVENT_ADMIN_OVERRIDE)
        assert event.reason == "manual recovery, see ticket #123"
        assert str(event.admin_user_id) == str(ADMIN_USER_ID)

    def test_rejects_when_submission_not_llm_failed(self, admin_client):
        submission = _make_submission(status=SUBMISSION_STATUS_LLM_PROCESSING)
        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/override-score/",
            {"score": 5, "feedback": {"overall": "ok"}, "reason": "x"}, format="json",
        )
        assert resp.status_code == 400
        assert not EssayScore.objects.filter(submission=submission).exists()

    @pytest.mark.parametrize("bad_score", [-1, 11, "not-a-number", None])
    def test_out_of_range_or_invalid_score_rejected(self, admin_client, bad_score):
        submission = _make_failed_submission()
        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/override-score/",
            {"score": bad_score, "feedback": {"overall": "ok"}, "reason": "x"}, format="json",
        )
        assert resp.status_code == 400
        assert not EssayScore.objects.filter(submission=submission).exists()

    def test_missing_reason_rejected(self, admin_client):
        submission = _make_failed_submission()
        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/override-score/",
            {"score": 5, "feedback": {"overall": "ok"}}, format="json",
        )
        assert resp.status_code == 400
        assert not EssayScore.objects.filter(submission=submission).exists()

    def test_missing_feedback_overall_rejected(self, admin_client):
        submission = _make_failed_submission()
        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/override-score/",
            {"score": 5, "feedback": {}, "reason": "x"}, format="json",
        )
        assert resp.status_code == 400
        assert not EssayScore.objects.filter(submission=submission).exists()

    def test_replaces_an_existing_wrong_score(self, admin_client):
        submission = _make_failed_submission()
        EssayScore.objects.create(submission=submission, score=1, feedback={"overall": "stale"}, evaluated_by=EVALUATED_BY_LLM)
        admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/override-score/",
            {"score": 9, "feedback": {"overall": "corrected"}, "reason": "manual correction"}, format="json",
        )
        assert EssayScore.objects.filter(submission=submission).count() == 1
        score = EssayScore.objects.get(submission=submission)
        assert score.score == 9
        assert score.evaluated_by == EVALUATED_BY_ADMIN

    def test_institution_isolated_404(self, admin_client, admin_b_client):
        submission = _make_failed_submission()
        resp = admin_b_client.post(
            f"/api/essay/admin/submissions/{submission.id}/override-score/",
            {"score": 5, "feedback": {"overall": "ok"}, "reason": "x"}, format="json",
        )
        assert resp.status_code == 404

    def test_student_role_rejected(self, student_client):
        submission = _make_failed_submission()
        resp = student_client.post(
            f"/api/essay/admin/submissions/{submission.id}/override-score/",
            {"score": 5, "feedback": {"overall": "ok"}, "reason": "x"}, format="json",
        )
        assert resp.status_code == 403

    def test_two_concurrent_overrides_on_the_same_submission_never_500(self, transactional_db):
        # Real gap found by this phase's own final-audit round: the status
        # precondition check and EssayScore.objects.create() are not
        # atomic with each other across two concurrent requests, and
        # EssayScore.submission is a genuine DB-level unique constraint
        # (OneToOneField) — two admins racing to override the SAME
        # submission could both read LLM_FAILED before either commits,
        # and the loser's create() used to raise an unhandled
        # IntegrityError straight through as a raw 500. Uses real OS
        # threads (Task 5.1's own "genuine OS-thread concurrency, not
        # sequential simulation" standard, mirrored from
        # test_concurrency.py), not a sequential double-call, since a
        # sequential call can never actually reproduce this interleaving
        # (the second call would simply see the first admin's already-
        # committed score and correctly 400 on the status check).
        submission = _make_failed_submission()
        factory = APIRequestFactory()

        def worker(_):
            try:
                def call():
                    request = factory.post(
                        f"/api/essay/admin/submissions/{submission.id}/override-score/",
                        {"score": 6, "feedback": {"overall": "concurrent override"}, "reason": "race test"},
                        format="json",
                    )
                    force_authenticate(request, user=_admin_jwt_user())
                    return AdminSubmissionScoreOverrideView.as_view()(request, pk=submission.id)
                return _retry_on_sqlite_lock(call)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(worker, range(2)))

        statuses = sorted(r.status_code for r in responses)
        # Exactly one request wins outright (200); the other either loses
        # the create() race cleanly (409, this fix's own new branch) or,
        # depending on thread interleaving, sees the winner's already-
        # committed status and is rejected by the ordinary precondition
        # check (400) — either way, NEVER an unhandled 500.
        assert statuses[0] == 200
        assert statuses[1] in (400, 409)
        assert 500 not in statuses
        assert EssayScore.objects.filter(submission=submission).count() == 1

    def test_override_isolated_by_institution_even_under_same_pk_race(self, transactional_db):
        # Sanity check the concurrency fix isn't accidentally too broad:
        # a different institution's admin racing against the real owner
        # must still get a clean 404, never absorbed into the 400/409
        # branch above.
        submission = _make_failed_submission()
        factory = APIRequestFactory()

        def call_as(user):
            request = factory.post(
                f"/api/essay/admin/submissions/{submission.id}/override-score/",
                {"score": 6, "feedback": {"overall": "x"}, "reason": "x"}, format="json",
            )
            force_authenticate(request, user=user)
            try:
                return _retry_on_sqlite_lock(
                    lambda: AdminSubmissionScoreOverrideView.as_view()(request, pk=submission.id)
                )
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(call_as, [
                _admin_jwt_user(ADMIN_USER_ID, INSTITUTION_A),
                _admin_jwt_user(ADMIN_B_USER_ID, INSTITUTION_B),
            ]))

        statuses = sorted(r.status_code for r in responses)
        assert 404 in statuses
        assert 500 not in statuses
