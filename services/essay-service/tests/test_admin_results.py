"""
test_admin_results.py — Phase 8, Task 8.1's own testing checklist:
institution/batch isolation (ET8), correctness against a known fixture,
export correctness (CSV, UTF-8-BOM), and general-override validation
(out-of-range score rejected, missing reason rejected, concurrent-override
race test since two admins could click at once).
"""
import os
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
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayStudentSetAllocation, EssayAttempt,
    EssaySubmission, EssayScore, EssaySubmissionEvent,
    ATTEMPT_STATUS_IN_PROGRESS, ATTEMPT_STATUS_SUBMITTED,
    SUBMISSION_STATUS_PENDING, SUBMISSION_STATUS_LLM_PROCESSING,
    SUBMISSION_STATUS_LLM_COMPLETE, SUBMISSION_STATUS_LLM_FAILED,
    SUBMISSION_EVENT_ADMIN_OVERRIDE, EVALUATED_BY_ADMIN, EVALUATED_BY_LLM,
    MALPRACTICE_EVENT_TEXT_SIMILARITY,
)
from essays.views import AdminSubmissionGeneralScoreOverrideView
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


def _make_assignment(*, institution_id=INSTITUTION_A, batch_id=None):
    paper = EssayPaper.objects.create(institution_id=institution_id, title="Persuasive Writing", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(
        set=eset, question_text="Argue for or against remote work.", llm_rubric_prompt="R",
        word_limit=500, time_limit_minutes=30,
    )
    assignment = EssayAssignment.objects.create(
        paper=paper, batch_id=batch_id or uuid.uuid4(), institution_id=institution_id,
        global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
    )
    return assignment, eset


def _allocate(assignment, eset, student_id=None):
    return EssayStudentSetAllocation.objects.create(
        assignment=assignment, student_id=student_id or uuid.uuid4(), set=eset,
    )


def _attempt(assignment, eset, student_id, *, status=ATTEMPT_STATUS_SUBMITTED,
             malpractice_flag=False, malpractice_reasons=None):
    return EssayAttempt.objects.create(
        assignment=assignment, student_id=student_id, set=eset,
        ends_at=timezone.now() + timedelta(hours=1), status=status,
        malpractice_flag=malpractice_flag, malpractice_reasons=malpractice_reasons or [],
    )


def _submission(attempt, *, status=SUBMISSION_STATUS_PENDING):
    submission = EssaySubmission.objects.create(attempt=attempt)
    if status != SUBMISSION_STATUS_PENDING:
        EssaySubmission.objects.filter(pk=submission.pk).update(status=status)
        submission.refresh_from_db()
    return submission


def _score(submission, *, score=8, feedback=None, evaluated_by=EVALUATED_BY_LLM):
    return EssayScore.objects.create(
        submission=submission, score=score,
        feedback=feedback or {"overall": "Solid response.", "breakdown": {}},
        evaluated_by=evaluated_by,
    )


def _fully_scored_student(assignment, eset, *, score=8, malpractice_reasons=None):
    """One allocated, submitted, scored student — the common "a real
    result exists" row shape most tests need."""
    student_id = uuid.uuid4()
    _allocate(assignment, eset, student_id)
    attempt = _attempt(
        assignment, eset, student_id,
        malpractice_flag=bool(malpractice_reasons), malpractice_reasons=malpractice_reasons,
    )
    submission = _submission(attempt, status=SUBMISSION_STATUS_LLM_COMPLETE)
    _score(submission, score=score)
    return student_id, attempt, submission


_ROSTER_PATCH_TARGET = "essays.views.fetch_batch_roster"


@pytest.mark.django_db
class TestResultsList:
    def test_shows_a_row_for_a_student_who_has_not_started_yet(self, admin_client):
        assignment, eset = _make_assignment()
        student_id = uuid.uuid4()
        _allocate(assignment, eset, student_id)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R001", "name": "A Student", "department": "CSE"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/")
        assert resp.status_code == 200
        results = resp.data["results"]
        assert len(results) == 1
        row = results[0]
        assert row["exam_status"] == "pending"
        assert row["score"] is None
        assert row["submission_id"] is None

    def test_writing_status_for_in_progress_attempt(self, admin_client):
        assignment, eset = _make_assignment()
        student_id = uuid.uuid4()
        _allocate(assignment, eset, student_id)
        _attempt(assignment, eset, student_id, status=ATTEMPT_STATUS_IN_PROGRESS)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R002", "name": "B Student", "department": "CSE"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/")
        assert resp.data["results"][0]["exam_status"] == "writing"

    def test_scored_row_matches_a_known_fixture(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, attempt, submission = _fully_scored_student(assignment, eset, score=7)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R003", "name": "C Student", "department": "ECE"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/")
        row = resp.data["results"][0]
        assert row["exam_status"] == "completed"
        assert row["score"] == 7
        assert row["feedback"]["overall"] == "Solid response."
        assert row["evaluated_by"] == "llm"
        assert row["student_roll_id"] == "R003"
        assert row["student_name"] == "C Student"
        assert row["department"] == "ECE"
        assert row["set_label"] == "Set A"
        assert row["question_text"] == "Argue for or against remote work."
        assert row["submission_id"] == str(submission.id)

    def test_failed_status_maps_to_failed_bucket(self, admin_client):
        assignment, eset = _make_assignment()
        student_id = uuid.uuid4()
        _allocate(assignment, eset, student_id)
        attempt = _attempt(assignment, eset, student_id)
        _submission(attempt, status=SUBMISSION_STATUS_LLM_FAILED)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R004", "name": "D Student", "department": "CSE"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/")
        assert resp.data["results"][0]["exam_status"] == "failed"
        assert resp.data["results"][0]["score"] is None

    def test_plagiarism_flag_derived_from_text_similarity_reason(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, _, _ = _fully_scored_student(
            assignment, eset, malpractice_reasons=[MALPRACTICE_EVENT_TEXT_SIMILARITY],
        )
        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R005", "name": "E Student", "department": "CSE"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/")
        row = resp.data["results"][0]
        assert row["malpractice_flag"] is True
        assert row["plagiarism_flag"] is True

    def test_malpractice_flag_true_without_plagiarism_reason_leaves_plagiarism_false(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, _, _ = _fully_scored_student(assignment, eset, malpractice_reasons=["tab_switch"])
        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R006", "name": "F Student", "department": "CSE"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/")
        row = resp.data["results"][0]
        assert row["malpractice_flag"] is True
        assert row["plagiarism_flag"] is False

    def test_department_filter(self, admin_client):
        assignment, eset = _make_assignment()
        cse_id, ece_id = uuid.uuid4(), uuid.uuid4()
        _allocate(assignment, eset, cse_id)
        _allocate(assignment, eset, ece_id)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(cse_id), "student_id": "R007", "name": "CSE Student", "department": "CSE"},
            {"user_id": str(ece_id), "student_id": "R008", "name": "ECE Student", "department": "ECE"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/", {"department": "cse"})
        results = resp.data["results"]
        assert len(results) == 1
        assert results[0]["student_user_id"] == str(cse_id)

    def test_student_search_filter(self, admin_client):
        assignment, eset = _make_assignment()
        target_id, other_id = uuid.uuid4(), uuid.uuid4()
        _allocate(assignment, eset, target_id)
        _allocate(assignment, eset, other_id)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(target_id), "student_id": "R2024001", "name": "Target Student", "department": "CSE"},
            {"user_id": str(other_id), "student_id": "R2024002", "name": "Other Student", "department": "CSE"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/", {"student_search": "2024001"})
        results = resp.data["results"]
        assert len(results) == 1
        assert results[0]["student_user_id"] == str(target_id)

    def test_flagged_filter(self, admin_client):
        assignment, eset = _make_assignment()
        flagged_id, _, _ = _fully_scored_student(assignment, eset, malpractice_reasons=["tab_switch"])
        clean_id, _, _ = _fully_scored_student(assignment, eset)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(flagged_id), "student_id": "R009", "name": "Flagged", "department": "CSE"},
            {"user_id": str(clean_id), "student_id": "R010", "name": "Clean", "department": "CSE"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/", {"flagged": "true"})
        results = resp.data["results"]
        assert len(results) == 1
        assert results[0]["student_user_id"] == str(flagged_id)

    def test_flagged_false_still_includes_a_student_who_has_not_started_yet(self, admin_client):
        # Real gap found by this phase's own final-audit round: a
        # not-yet-started student has no EssayAttempt row at all, so a
        # naive "student_id__in=[ids with malpractice_flag=False]" filter
        # for flagged=false would wrongly drop them — nothing has
        # happened for them, so "not flagged" is trivially correct. The
        # exact same false-branch pitfall assessment-service's own
        # _build_results_queryset explicitly documents fixing.
        assignment, eset = _make_assignment()
        flagged_id, _, _ = _fully_scored_student(assignment, eset, malpractice_reasons=["tab_switch"])
        not_started_id = uuid.uuid4()
        _allocate(assignment, eset, not_started_id)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(flagged_id), "student_id": "R014", "name": "Flagged", "department": "CSE"},
            {"user_id": str(not_started_id), "student_id": "R015", "name": "Not Started", "department": "CSE"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/", {"flagged": "false"})
        results = resp.data["results"]
        assert len(results) == 1
        assert results[0]["student_user_id"] == str(not_started_id)

    def test_roster_fetch_failure_returns_502(self, admin_client):
        assignment, eset = _make_assignment()
        _allocate(assignment, eset)
        with patch(_ROSTER_PATCH_TARGET, side_effect=RuntimeError("user-service unreachable")):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/")
        assert resp.status_code == 502

    def test_pagination_at_30_per_page(self, admin_client):
        assignment, eset = _make_assignment()
        roster = []
        for i in range(35):
            sid = uuid.uuid4()
            _allocate(assignment, eset, sid)
            roster.append({"user_id": str(sid), "student_id": f"R{i:03d}", "name": f"S{i}", "department": "CSE"})

        with patch(_ROSTER_PATCH_TARGET, return_value=roster):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/")
        assert resp.data["count"] == 35
        assert len(resp.data["results"]) == 30

    def test_institution_isolated_404(self, admin_client, admin_b_client):
        assignment, eset = _make_assignment()
        _allocate(assignment, eset)
        resp = admin_b_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/")
        assert resp.status_code == 404

    def test_unauthenticated_rejected(self, anon_client):
        assignment, eset = _make_assignment()
        resp = anon_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/")
        assert resp.status_code == 401

    def test_student_role_rejected(self, student_client):
        assignment, eset = _make_assignment()
        resp = student_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestResultsExport:
    def test_csv_has_bom_and_header(self, admin_client):
        assignment, eset = _make_assignment()
        _allocate(assignment, eset)
        with patch(_ROSTER_PATCH_TARGET, return_value=[]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/export/")
        assert resp.status_code == 200
        content = b"".join(resp.streaming_content).decode("utf-8")
        assert content.startswith("﻿")
        assert "Student Roll No" in content.splitlines()[0]

    def test_csv_row_values_match_a_known_fixture(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, _, _ = _fully_scored_student(assignment, eset, score=9)
        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R011", "name": "G Student", "department": "CSE"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/export/")
        content = b"".join(resp.streaming_content).decode("utf-8")
        lines = content.splitlines()
        assert "R011" in lines[1]
        assert "G Student" in lines[1]
        assert ",9," in lines[1]

    def test_export_respects_the_same_department_filter_as_the_table(self, admin_client):
        assignment, eset = _make_assignment()
        cse_id, ece_id = uuid.uuid4(), uuid.uuid4()
        _allocate(assignment, eset, cse_id)
        _allocate(assignment, eset, ece_id)
        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(cse_id), "student_id": "R012", "name": "CSE", "department": "CSE"},
            {"user_id": str(ece_id), "student_id": "R013", "name": "ECE", "department": "ECE"},
        ]):
            resp = admin_client.get(
                f"/api/essay/admin/assignments/{assignment.id}/results/export/", {"department": "ECE"},
            )
        content = b"".join(resp.streaming_content).decode("utf-8")
        assert "R013" in content
        assert "R012" not in content

    def test_content_disposition_filename(self, admin_client):
        assignment, eset = _make_assignment()
        with patch(_ROSTER_PATCH_TARGET, return_value=[]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/export/")
        assert f"essay_results_{assignment.id}.csv" in resp["Content-Disposition"]

    def test_student_role_rejected(self, student_client):
        assignment, eset = _make_assignment()
        resp = student_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/export/")
        assert resp.status_code == 403

    def test_institution_isolated_404(self, admin_client, admin_b_client):
        # Task 15.1's own audit: the sibling results/ (table) view has
        # this test; the export view — which streams the same student
        # data as a CSV — was missing it, a real coverage gap found by a
        # dedicated coverage-mapping pass. AdminEssayAssignmentResultsExportView
        # reads directly confirmed it already filters by
        # institution_id=institution_id (same helper the table view uses)
        # — closing a test gap, not a live vulnerability.
        assignment, eset = _make_assignment(institution_id=INSTITUTION_A)
        resp = admin_b_client.get(f"/api/essay/admin/assignments/{assignment.id}/results/export/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestGeneralScoreOverride:
    def test_override_happy_path(self, admin_client):
        assignment, eset = _make_assignment()
        _, _, submission = _fully_scored_student(assignment, eset, score=3)

        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/general-override-score/",
            {"score": 9, "feedback": {"overall": "Regraded after appeal."}, "reason": "Student appeal, ticket #42."},
            format="json",
        )
        assert resp.status_code == 200
        score = EssayScore.objects.get(submission=submission)
        assert score.score == 9
        assert score.evaluated_by == EVALUATED_BY_ADMIN

    def test_override_writes_audit_log_with_old_and_new_score(self, admin_client):
        assignment, eset = _make_assignment()
        _, _, submission = _fully_scored_student(assignment, eset, score=3)

        admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/general-override-score/",
            {"score": 9, "feedback": {"overall": "Regraded."}, "reason": "Appeal."}, format="json",
        )
        event = EssaySubmissionEvent.objects.get(submission=submission, event_type=SUBMISSION_EVENT_ADMIN_OVERRIDE)
        assert "3/10 -> 9/10" in event.detail
        assert event.reason == "Appeal."
        assert str(event.admin_user_id) == str(ADMIN_USER_ID)

    def test_override_clears_a_stale_is_no_submission_flag(self, admin_client):
        # Real gap found by this phase's own final-audit round: an
        # admin-entered correction always represents a real, deliberate
        # judgment call — a score that started as the no-submission
        # guard's auto-zero (is_no_submission=True) must not silently
        # keep reading as "never wrote anything" after an admin has
        # manually corrected it to a real score, or a future Analytics
        # consumer of that flag (its own model docstring names this
        # exact use) would misreport this student.
        assignment, eset = _make_assignment()
        student_id = uuid.uuid4()
        _allocate(assignment, eset, student_id)
        attempt = _attempt(assignment, eset, student_id)
        submission = _submission(attempt, status=SUBMISSION_STATUS_LLM_COMPLETE)
        score = EssayScore.objects.create(
            submission=submission, score=0,
            feedback={"overall": "No submission received.", "breakdown": {}},
            is_no_submission=True,
        )

        admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/general-override-score/",
            {"score": 6, "feedback": {"overall": "Accepted on appeal."}, "reason": "Late submission accepted."},
            format="json",
        )
        score.refresh_from_db()
        assert score.score == 6
        assert score.is_no_submission is False

    def test_rejects_when_no_score_exists_yet(self, admin_client):
        assignment, eset = _make_assignment()
        student_id = uuid.uuid4()
        _allocate(assignment, eset, student_id)
        attempt = _attempt(assignment, eset, student_id)
        submission = _submission(attempt, status=SUBMISSION_STATUS_LLM_FAILED)

        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/general-override-score/",
            {"score": 5, "feedback": {"overall": "x"}, "reason": "x"}, format="json",
        )
        assert resp.status_code == 400
        assert not EssayScore.objects.filter(submission=submission).exists()

    @pytest.mark.parametrize("bad_score", [-1, 11, "not-a-number", None])
    def test_out_of_range_or_invalid_score_rejected(self, admin_client, bad_score):
        assignment, eset = _make_assignment()
        _, _, submission = _fully_scored_student(assignment, eset, score=5)
        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/general-override-score/",
            {"score": bad_score, "feedback": {"overall": "x"}, "reason": "x"}, format="json",
        )
        assert resp.status_code == 400
        assert EssayScore.objects.get(submission=submission).score == 5  # unchanged

    def test_missing_reason_rejected(self, admin_client):
        assignment, eset = _make_assignment()
        _, _, submission = _fully_scored_student(assignment, eset, score=5)
        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/general-override-score/",
            {"score": 8, "feedback": {"overall": "x"}}, format="json",
        )
        assert resp.status_code == 400
        assert EssayScore.objects.get(submission=submission).score == 5

    def test_reason_over_500_chars_rejected(self, admin_client):
        assignment, eset = _make_assignment()
        _, _, submission = _fully_scored_student(assignment, eset, score=5)
        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/general-override-score/",
            {"score": 8, "feedback": {"overall": "x"}, "reason": "x" * 501}, format="json",
        )
        assert resp.status_code == 400
        assert EssayScore.objects.get(submission=submission).score == 5

    def test_missing_feedback_overall_rejected(self, admin_client):
        assignment, eset = _make_assignment()
        _, _, submission = _fully_scored_student(assignment, eset, score=5)
        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/general-override-score/",
            {"score": 8, "feedback": {}, "reason": "x"}, format="json",
        )
        assert resp.status_code == 400
        assert EssayScore.objects.get(submission=submission).score == 5

    def test_institution_isolated_404(self, admin_client, admin_b_client):
        assignment, eset = _make_assignment()
        _, _, submission = _fully_scored_student(assignment, eset, score=5)
        resp = admin_b_client.post(
            f"/api/essay/admin/submissions/{submission.id}/general-override-score/",
            {"score": 8, "feedback": {"overall": "x"}, "reason": "x"}, format="json",
        )
        assert resp.status_code == 404

    def test_student_role_rejected(self, student_client):
        assignment, eset = _make_assignment()
        _, _, submission = _fully_scored_student(assignment, eset, score=5)
        resp = student_client.post(
            f"/api/essay/admin/submissions/{submission.id}/general-override-score/",
            {"score": 8, "feedback": {"overall": "x"}, "reason": "x"}, format="json",
        )
        assert resp.status_code == 403

    @pytest.mark.skipif(
        not os.environ.get("TEST_USE_POSTGRES"),
        reason="Needs real row-level locking (select_for_update). SQLite cannot test this; run with TEST_USE_POSTGRES=1.",
    )
    def test_two_concurrent_overrides_never_lose_an_update(self, transactional_db):
        # Real hazard this view's own docstring names: a lost-update race
        # between two admins independently correcting an ALREADY-EXISTING
        # score — select_for_update() must serialize the two writes so
        # the second racer reads the FIRST racer's already-committed value
        # as its own "old score" (a correct, chained audit trail), not a
        # stale pre-race value (which would silently mis-describe what
        # actually happened). Real OS threads, not a sequential
        # simulation — matches Task 5.1's own established concurrency-
        # testing standard, mirrored from test_concurrency.py.
        assignment, eset = _make_assignment()
        _, _, submission = _fully_scored_student(assignment, eset, score=3)
        factory = APIRequestFactory()

        def worker(new_score):
            try:
                def call():
                    request = factory.post(
                        f"/api/essay/admin/submissions/{submission.id}/general-override-score/",
                        {"score": new_score, "feedback": {"overall": f"race to {new_score}"}, "reason": "race test"},
                        format="json",
                    )
                    force_authenticate(request, user=_admin_jwt_user())
                    return AdminSubmissionGeneralScoreOverrideView.as_view()(request, pk=submission.id)
                return _retry_on_sqlite_lock(call)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(worker, [7, 9]))

        assert all(r.status_code == 200 for r in responses)
        # Exactly one EssayScore row, no crash, no silently-lost write —
        # the final value is whichever racer committed last (either 7 or
        # 9 is a correct outcome; what matters is neither write vanished
        # without ever being applied, and no 500 occurred).
        assert EssayScore.objects.filter(submission=submission).count() == 1
        final_score = EssayScore.objects.get(submission=submission).score
        assert final_score in (7, 9)

        # Both admin actions must appear in the audit trail — two
        # ADMIN_OVERRIDE events, not one silently dropped.
        events = list(EssaySubmissionEvent.objects.filter(
            submission=submission, event_type=SUBMISSION_EVENT_ADMIN_OVERRIDE,
        ).order_by("occurred_at"))
        assert len(events) == 2
        # The second event's own "old score" must reflect the FIRST
        # event's new score, not the original pre-race value of 3 — this
        # is the actual lost-update hazard select_for_update() exists to
        # close, verified directly against the audit trail's own text,
        # not just the final DB state (which alone can't distinguish a
        # correctly-serialized race from a lucky lost update).
        def _old_new(detail):
            body = detail.split(": ", 1)[1]  # strip the "General score override: " prefix
            old_part, new_part = body.split(" -> ")
            return int(old_part.split("/")[0]), int(new_part.split("/")[0])

        first_old, first_new = _old_new(events[0].detail)
        second_old, second_new = _old_new(events[1].detail)
        assert first_old == 3  # the true pre-race value
        assert second_old == first_new
