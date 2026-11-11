"""
test_admin_reports.py — Phase 11's own testing checklist (Tasks 11.1/11.2):
report content accuracy against the underlying score/feedback data,
regeneration idempotency (double-click doesn't double-dispatch),
rollback-on-dispatch-failure actually restores the prior state, bulk-ZIP
content correctness, search/filter correctness, delivery-status accuracy
against a real send + a real (directly-recorded) bounce/complaint event,
resend happy path, bulk-resend cap enforced and dry-run-by-default.

Automatic report generation itself (LLM_COMPLETE -> REPORT_GENERATING ->
REPORT_READY, dispatched from _transition_submission_status /
AdminSubmissionScoreOverrideView) is already covered by
test_evaluate_essay.py and test_admin_llm_controls.py's own updated
assertions — not duplicated here.
"""
import io
import uuid
import zipfile
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt, EssaySubmission, EssayScore,
    EssaySubmissionEvent, EssayFailedJob,
    SUBMISSION_STATUS_LLM_COMPLETE, SUBMISSION_STATUS_LLM_PROCESSING, SUBMISSION_STATUS_REPORT_GENERATING,
    SUBMISSION_STATUS_REPORT_READY,
    SUBMISSION_EVENT_EMAIL_BOUNCED, SUBMISSION_EVENT_EMAIL_COMPLAINT, SUBMISSION_EVENT_DLQ_RECORDED,
    EVALUATED_BY_LLM,
)
from essays.reports import render_report_html
from essays.tasks import send_essay_report_email

from .conftest import INSTITUTION_A, INSTITUTION_B, ADMIN_USER_ID, ADMIN_B_USER_ID

_ROSTER_PATCH_TARGET = "essays.views.fetch_batch_roster"


def _make_assignment(*, institution_id=INSTITUTION_A, batch_id=None):
    paper = EssayPaper.objects.create(institution_id=institution_id, title="Report Writing", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(
        set=eset, question_text="Discuss the causes of X.", llm_rubric_prompt="Score on clarity and evidence.",
        word_limit=500, time_limit_minutes=30,
    )
    assignment = EssayAssignment.objects.create(
        paper=paper, batch_id=batch_id or uuid.uuid4(), institution_id=institution_id,
        global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
    )
    return assignment, eset


def _attempt(assignment, eset, student_id=None, *, draft_response="A thoughtful essay response."):
    return EssayAttempt.objects.create(
        assignment=assignment, student_id=student_id or uuid.uuid4(), set=eset,
        ends_at=timezone.now() + timedelta(hours=1), draft_response=draft_response,
    )


def _submission(attempt, *, status=SUBMISSION_STATUS_LLM_COMPLETE, report_html=None, email_sent_at=None):
    submission = EssaySubmission.objects.create(attempt=attempt)
    EssaySubmission.objects.filter(pk=submission.pk).update(
        status=status, report_html=report_html, email_sent_at=email_sent_at,
    )
    submission.refresh_from_db()
    return submission


def _score(submission, *, score=8, feedback=None):
    return EssayScore.objects.create(
        submission=submission, score=score,
        feedback=feedback or {"overall": "Solid response.", "breakdown": {
            "clarity": {"score": 4, "maxScore": 5, "feedback": "Mostly clear."},
        }},
        evaluated_by=EVALUATED_BY_LLM,
    )


def _ready_submission(assignment, eset, *, student_id=None, score=8, report_html="<html>DUMMY REPORT</html>"):
    """A submission already past generation — REPORT_READY with a
    (deliberately simple, non-rendered) report_html, the common fixture
    shape most view-level tests need without depending on
    render_report_html's own exact output."""
    student_id = student_id or uuid.uuid4()
    attempt = _attempt(assignment, eset, student_id)
    submission = _submission(attempt, status=SUBMISSION_STATUS_REPORT_READY, report_html=report_html)
    _score(submission, score=score)
    return student_id, attempt, submission


@pytest.mark.django_db
class TestReportRendering:
    def test_report_contains_score_feedback_and_question(self):
        assignment, eset = _make_assignment()
        attempt = _attempt(assignment, eset, draft_response="My essay about the topic.")
        submission = _submission(attempt, status=SUBMISSION_STATUS_LLM_COMPLETE)
        _score(submission, score=7, feedback={"overall": "Good structure.", "breakdown": {
            "clarity": {"score": 3, "maxScore": 5, "feedback": "Needs more examples."},
        }})
        submission = EssaySubmission.objects.select_related(
            "attempt__assignment__paper", "attempt__set__question", "score",
        ).get(pk=submission.pk)

        html = render_report_html(submission)
        assert "7 / 10" in html
        assert "Good structure." in html
        assert "Needs more examples." in html
        assert "My essay about the topic." in html
        assert "Discuss the causes of X." in html

    def test_report_escapes_html_in_student_response(self):
        assignment, eset = _make_assignment()
        attempt = _attempt(assignment, eset, draft_response="<script>alert(1)</script>")
        submission = _submission(attempt, status=SUBMISSION_STATUS_LLM_COMPLETE)
        _score(submission, score=5)
        submission = EssaySubmission.objects.select_related(
            "attempt__assignment__paper", "attempt__set__question", "score",
        ).get(pk=submission.pk)

        html = render_report_html(submission)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_unscored_submission_renders_not_yet_scored(self):
        assignment, eset = _make_assignment()
        attempt = _attempt(assignment, eset)
        submission = _submission(attempt, status=SUBMISSION_STATUS_LLM_COMPLETE)
        submission = EssaySubmission.objects.select_related(
            "attempt__assignment__paper", "attempt__set__question", "score",
        ).get(pk=submission.pk)

        html = render_report_html(submission)
        assert "Not yet scored." in html


@pytest.mark.django_db
class TestReportList:
    def test_lists_a_report_row_with_delivery_status(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, _, submission = _ready_submission(assignment, eset, score=9)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R001", "name": "A Student",
             "department": "CSE", "email": "a.student@example.com"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/reports/")
        assert resp.status_code == 200
        results = resp.data["results"]
        assert len(results) == 1
        row = results[0]
        assert row["submission_id"] == str(submission.id)
        assert row["student_email"] == "a.student@example.com"
        assert row["has_report"] is True
        assert row["score"] == 9
        assert row["delivery_status"] == "pending"

    def test_status_filter_excludes_non_matching_submissions(self, admin_client):
        assignment, eset = _make_assignment()
        _ready_submission(assignment, eset)
        pending_attempt = _attempt(assignment, eset)
        _submission(pending_attempt, status=SUBMISSION_STATUS_LLM_PROCESSING)

        with patch(_ROSTER_PATCH_TARGET, return_value=[]):
            resp = admin_client.get(
                f"/api/essay/admin/assignments/{assignment.id}/reports/", {"status": "processing"},
            )
        assert resp.status_code == 200
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["status"] == SUBMISSION_STATUS_LLM_PROCESSING

    def test_unknown_status_filter_returns_400(self, admin_client):
        assignment, _ = _make_assignment()
        with patch(_ROSTER_PATCH_TARGET, return_value=[]):
            resp = admin_client.get(
                f"/api/essay/admin/assignments/{assignment.id}/reports/", {"status": "not-a-bucket"},
            )
        assert resp.status_code == 400

    def test_student_search_matches_email(self, admin_client):
        assignment, eset = _make_assignment()
        target_id, _, _ = _ready_submission(assignment, eset)
        other_id, _, _ = _ready_submission(assignment, eset)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(target_id), "student_id": "R001", "name": "Target", "email": "target@example.com"},
            {"user_id": str(other_id), "student_id": "R002", "name": "Other", "email": "other@example.com"},
        ]):
            resp = admin_client.get(
                f"/api/essay/admin/assignments/{assignment.id}/reports/", {"student_search": "target@"},
            )
        assert resp.status_code == 200
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["submission_id"] == str(target_id) or \
            resp.data["results"][0]["student_email"] == "target@example.com"

    def test_delivery_status_sent_when_email_sent_at_set(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, _, submission = _ready_submission(assignment, eset)
        EssaySubmission.objects.filter(pk=submission.pk).update(email_sent_at=timezone.now())

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R001", "name": "S", "email": "s@example.com"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/reports/")
        assert resp.data["results"][0]["delivery_status"] == "sent"

    def test_delivery_status_bounced_overrides_sent(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, _, submission = _ready_submission(assignment, eset)
        EssaySubmission.objects.filter(pk=submission.pk).update(email_sent_at=timezone.now())
        EssaySubmissionEvent.objects.create(submission=submission, event_type=SUBMISSION_EVENT_EMAIL_BOUNCED, detail="hard bounce")

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R001", "name": "S", "email": "s@example.com"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/reports/")
        assert resp.data["results"][0]["delivery_status"] == "bounced"

    def test_delivery_status_complaint_outranks_bounced(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, _, submission = _ready_submission(assignment, eset)
        EssaySubmissionEvent.objects.create(submission=submission, event_type=SUBMISSION_EVENT_EMAIL_BOUNCED, detail="x")
        EssaySubmissionEvent.objects.create(submission=submission, event_type=SUBMISSION_EVENT_EMAIL_COMPLAINT, detail="y")

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R001", "name": "S", "email": "s@example.com"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/reports/")
        assert resp.data["results"][0]["delivery_status"] == "complaint"

    def test_institution_isolation(self, admin_b_client):
        assignment, _ = _make_assignment(institution_id=INSTITUTION_A)
        resp = admin_b_client.get(f"/api/essay/admin/assignments/{assignment.id}/reports/")
        assert resp.status_code == 404

    def test_student_role_rejected(self, student_client):
        assignment, _ = _make_assignment()
        resp = student_client.get(f"/api/essay/admin/assignments/{assignment.id}/reports/")
        assert resp.status_code == 403

    def test_roster_fetch_failure_returns_502(self, admin_client):
        assignment, _ = _make_assignment()
        with patch(_ROSTER_PATCH_TARGET, side_effect=RuntimeError("user-service unreachable")):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/reports/")
        assert resp.status_code == 502


@pytest.mark.django_db
class TestReportRegenerate:
    def test_regenerate_happy_path_dispatches_generation(self, admin_client):
        assignment, eset = _make_assignment()
        _, _, submission = _ready_submission(assignment, eset, score=6)
        EssaySubmission.objects.filter(pk=submission.pk).update(email_sent_at=timezone.now())

        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/regenerate-report/",
            {"reason": "Score was corrected, report is stale."}, format="json",
        )
        assert resp.status_code == 200
        submission.refresh_from_db()
        # generate_essay_report ran synchronously (CELERY_TASK_ALWAYS_EAGER)
        # and rendered a fresh report, ending back at REPORT_READY with a
        # freshly-rendered (not the old dummy) report, and email_sent_at
        # cleared so the corrected report actually gets redelivered.
        assert submission.status == SUBMISSION_STATUS_REPORT_READY
        assert submission.report_html != "<html>DUMMY REPORT</html>"
        assert submission.email_sent_at is None

    def test_regenerate_requires_a_reason(self, admin_client):
        assignment, eset = _make_assignment()
        _, _, submission = _ready_submission(assignment, eset)
        resp = admin_client.post(f"/api/essay/admin/submissions/{submission.id}/regenerate-report/", {}, format="json")
        assert resp.status_code == 400

    def test_regenerate_rejected_when_not_report_ready(self, admin_client):
        assignment, eset = _make_assignment()
        attempt = _attempt(assignment, eset)
        submission = _submission(attempt, status=SUBMISSION_STATUS_LLM_COMPLETE)
        resp = admin_client.post(
            f"/api/essay/admin/submissions/{submission.id}/regenerate-report/",
            {"reason": "test"}, format="json",
        )
        assert resp.status_code == 409

    def test_institution_isolation(self, admin_b_client):
        assignment, eset = _make_assignment(institution_id=INSTITUTION_A)
        _, _, submission = _ready_submission(assignment, eset)
        resp = admin_b_client.post(
            f"/api/essay/admin/submissions/{submission.id}/regenerate-report/",
            {"reason": "test"}, format="json",
        )
        assert resp.status_code == 404

    def test_student_role_rejected(self, student_client):
        assignment, eset = _make_assignment()
        _, _, submission = _ready_submission(assignment, eset)
        resp = student_client.post(
            f"/api/essay/admin/submissions/{submission.id}/regenerate-report/",
            {"reason": "test"}, format="json",
        )
        assert resp.status_code == 403

    def test_double_click_only_one_regeneration_dispatched(self, admin_client):
        """Idempotency: the CAS update is the lock — two identical
        requests against the same REPORT_READY submission must not both
        succeed (mirrors AdminSubmissionRetriggerView's own already-tested
        double-click guard, Phase 7)."""
        assignment, eset = _make_assignment()
        _, _, submission = _ready_submission(assignment, eset)

        with patch("essays.tasks.generate_essay_report.delay") as mock_dispatch:
            first = admin_client.post(
                f"/api/essay/admin/submissions/{submission.id}/regenerate-report/",
                {"reason": "first"}, format="json",
            )
            second = admin_client.post(
                f"/api/essay/admin/submissions/{submission.id}/regenerate-report/",
                {"reason": "second"}, format="json",
            )
        assert first.status_code == 200
        assert second.status_code == 409
        mock_dispatch.assert_called_once()

    def test_dispatch_failure_rolls_back_to_prior_state(self, admin_client):
        assignment, eset = _make_assignment()
        _, _, submission = _ready_submission(assignment, eset, report_html="<html>ORIGINAL</html>")
        EssaySubmission.objects.filter(pk=submission.pk).update(email_sent_at=timezone.now())

        with patch("essays.tasks.generate_essay_report.delay", side_effect=RuntimeError("broker down")):
            resp = admin_client.post(
                f"/api/essay/admin/submissions/{submission.id}/regenerate-report/",
                {"reason": "test"}, format="json",
            )
        assert resp.status_code == 502
        submission.refresh_from_db()
        assert submission.status == SUBMISSION_STATUS_REPORT_READY
        assert submission.report_html == "<html>ORIGINAL</html>"
        assert submission.email_sent_at is not None


@pytest.mark.django_db
class TestReportResend:
    def test_send_essay_report_email_sets_sent_at_and_uses_outbox(self):
        assignment, eset = _make_assignment()
        _, _, submission = _ready_submission(assignment, eset, report_html="<html>hi</html>")

        send_essay_report_email.apply(args=[str(submission.id), "student@example.com"])

        submission.refresh_from_db()
        assert submission.email_sent_at is not None
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["student@example.com"]
        assert mail.outbox[0].alternatives or mail.outbox[0].body  # html_message attached

    def test_sends_from_default_from_email_not_server_email(self):
        # Real gap found by this phase's own final-audit round: the first
        # version of this task sent from SERVER_EMAIL (Django's own
        # mail_admins()-alert convention) instead of DEFAULT_FROM_EMAIL —
        # the wrong identity for a genuine student-facing email. Uses
        # override_settings with two deliberately DIFFERENT values so a
        # regression back to SERVER_EMAIL would actually fail this test,
        # not pass by coincidence (both settings share the same fallback
        # default otherwise).
        from django.test import override_settings
        assignment, eset = _make_assignment()
        _, _, submission = _ready_submission(assignment, eset, report_html="<html>hi</html>")

        with override_settings(SERVER_EMAIL="server-alerts@spark.local", DEFAULT_FROM_EMAIL="reports@spark.local"):
            send_essay_report_email.apply(args=[str(submission.id), "student@example.com"])

        assert mail.outbox[0].from_email == "reports@spark.local"

    def test_resend_view_dispatches_with_roster_email(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, _, submission = _ready_submission(assignment, eset)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R001", "name": "S", "email": "s@example.com"},
        ]):
            resp = admin_client.post(f"/api/essay/admin/submissions/{submission.id}/resend-report/")
        assert resp.status_code == 200
        submission.refresh_from_db()
        assert submission.email_sent_at is not None
        assert mail.outbox[0].to == ["s@example.com"]

    def test_resend_rejected_when_no_report_yet(self, admin_client):
        assignment, eset = _make_assignment()
        attempt = _attempt(assignment, eset)
        submission = _submission(attempt, status=SUBMISSION_STATUS_LLM_COMPLETE)
        resp = admin_client.post(f"/api/essay/admin/submissions/{submission.id}/resend-report/")
        assert resp.status_code == 409

    def test_resend_rejected_when_no_email_on_file(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, _, submission = _ready_submission(assignment, eset)
        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R001", "name": "S"},
        ]):
            resp = admin_client.post(f"/api/essay/admin/submissions/{submission.id}/resend-report/")
        assert resp.status_code == 422

    def test_institution_isolation(self, admin_b_client):
        assignment, eset = _make_assignment(institution_id=INSTITUTION_A)
        _, _, submission = _ready_submission(assignment, eset)
        resp = admin_b_client.post(f"/api/essay/admin/submissions/{submission.id}/resend-report/")
        assert resp.status_code == 404

    def test_student_role_rejected(self, student_client):
        assignment, eset = _make_assignment()
        _, _, submission = _ready_submission(assignment, eset)
        resp = student_client.post(f"/api/essay/admin/submissions/{submission.id}/resend-report/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestBulkResend:
    def test_dry_run_is_the_default_and_sends_nothing(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, _, _ = _ready_submission(assignment, eset)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R001", "name": "S", "email": "s@example.com"},
        ]):
            resp = admin_client.post(f"/api/essay/admin/assignments/{assignment.id}/reports/bulk-resend/", {}, format="json")
        assert resp.status_code == 200
        assert resp.data["data"]["dry_run"] is True
        assert resp.data["data"]["would_dispatch_count"] == 1
        assert len(mail.outbox) == 0

    def test_dry_run_false_actually_dispatches(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, _, _ = _ready_submission(assignment, eset)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R001", "name": "S", "email": "s@example.com"},
        ]):
            resp = admin_client.post(
                f"/api/essay/admin/assignments/{assignment.id}/reports/bulk-resend/",
                {"dry_run": False}, format="json",
            )
        assert resp.status_code == 200
        assert resp.data["data"]["dry_run"] is False
        assert resp.data["data"]["dispatched_count"] == 1
        assert len(mail.outbox) == 1

    def test_bulk_resend_cap_enforced(self, admin_client):
        from essays.views import BULK_RESEND_CAP
        assignment, eset = _make_assignment()
        roster = []
        for i in range(BULK_RESEND_CAP + 5):
            student_id, _, _ = _ready_submission(assignment, eset)
            roster.append({"user_id": str(student_id), "student_id": f"R{i}", "name": f"S{i}", "email": f"s{i}@example.com"})

        with patch(_ROSTER_PATCH_TARGET, return_value=roster):
            resp = admin_client.post(f"/api/essay/admin/assignments/{assignment.id}/reports/bulk-resend/", {}, format="json")
        assert resp.status_code == 200
        assert resp.data["data"]["would_dispatch_count"] == BULK_RESEND_CAP
        assert resp.data["data"]["total_matching"] == BULK_RESEND_CAP + 5
        assert resp.data["data"]["capped"] is True

    def test_bulk_resend_only_targets_submissions_with_a_report(self, admin_client):
        assignment, eset = _make_assignment()
        student_id, _, _ = _ready_submission(assignment, eset)
        no_report_attempt = _attempt(assignment, eset)
        _submission(no_report_attempt, status=SUBMISSION_STATUS_LLM_COMPLETE)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(student_id), "student_id": "R001", "name": "S", "email": "s@example.com"},
        ]):
            resp = admin_client.post(f"/api/essay/admin/assignments/{assignment.id}/reports/bulk-resend/", {}, format="json")
        assert resp.data["data"]["total_matching"] == 1

    def test_bulk_resend_respects_the_department_filter(self, admin_client):
        # Real gap found by this phase's own final-audit round: bulk-resend
        # and bulk-download share _build_essay_reports_queryset with the
        # report list (their own docstrings both claim this), but nothing
        # actually proved a filter narrows THEIR OWN target set too, not
        # just the "has a report" exclusion every one of the tests above
        # already covers.
        assignment, eset = _make_assignment()
        cse_id, _, _ = _ready_submission(assignment, eset)
        ece_id, _, _ = _ready_submission(assignment, eset)

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(cse_id), "student_id": "R001", "name": "CSE Student", "department": "CSE", "email": "cse@example.com"},
            {"user_id": str(ece_id), "student_id": "R002", "name": "ECE Student", "department": "ECE", "email": "ece@example.com"},
        ]):
            resp = admin_client.post(
                f"/api/essay/admin/assignments/{assignment.id}/reports/bulk-resend/?department=CSE", {}, format="json",
            )
        assert resp.data["data"]["total_matching"] == 1
        assert resp.data["data"]["sample"][0]["student_email"] == "cse@example.com"

    def test_institution_isolation(self, admin_b_client):
        assignment, _ = _make_assignment(institution_id=INSTITUTION_A)
        resp = admin_b_client.post(f"/api/essay/admin/assignments/{assignment.id}/reports/bulk-resend/", {}, format="json")
        assert resp.status_code == 404

    def test_student_role_rejected(self, student_client):
        assignment, _ = _make_assignment()
        resp = student_client.post(f"/api/essay/admin/assignments/{assignment.id}/reports/bulk-resend/", {}, format="json")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestBulkDownload:
    def test_zip_contains_one_html_per_report_and_a_manifest(self, admin_client):
        assignment, eset = _make_assignment()
        s1_id, _, sub1 = _ready_submission(assignment, eset, report_html="<html>ONE</html>")
        s2_id, _, sub2 = _ready_submission(assignment, eset, report_html="<html>TWO</html>")

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(s1_id), "student_id": "R001", "name": "One", "email": "one@example.com"},
            {"user_id": str(s2_id), "student_id": "R002", "name": "Two", "email": "two@example.com"},
        ]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/reports/bulk-download/")
        assert resp.status_code == 200
        assert resp["Content-Disposition"].endswith(f'essay_reports_{assignment.id}.zip"')

        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = set(zf.namelist())
        assert f"{sub1.id}.html" in names
        assert f"{sub2.id}.html" in names
        assert "manifest.csv" in names
        assert zf.read(f"{sub1.id}.html").decode() == "<html>ONE</html>"

        manifest = zf.read("manifest.csv").decode()
        assert "Submission ID,Student Email,Report Reference" in manifest
        assert "one@example.com" in manifest
        assert "two@example.com" in manifest

    def test_bulk_download_excludes_submissions_without_a_report(self, admin_client):
        assignment, eset = _make_assignment()
        _, _, with_report = _ready_submission(assignment, eset)
        no_report_attempt = _attempt(assignment, eset)
        without_report = _submission(no_report_attempt, status=SUBMISSION_STATUS_LLM_COMPLETE)

        with patch(_ROSTER_PATCH_TARGET, return_value=[]):
            resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/reports/bulk-download/")
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = set(zf.namelist())
        assert f"{with_report.id}.html" in names
        assert f"{without_report.id}.html" not in names

    def test_bulk_download_respects_the_student_search_filter(self, admin_client):
        # Same gap class as bulk-resend's own equivalent test above —
        # this view's own docstring claims "same filters as the report
        # list" too.
        assignment, eset = _make_assignment()
        target_id, _, target_sub = _ready_submission(assignment, eset, report_html="<html>TARGET</html>")
        other_id, _, other_sub = _ready_submission(assignment, eset, report_html="<html>OTHER</html>")

        with patch(_ROSTER_PATCH_TARGET, return_value=[
            {"user_id": str(target_id), "student_id": "R001", "name": "Target", "email": "target@example.com"},
            {"user_id": str(other_id), "student_id": "R002", "name": "Other", "email": "other@example.com"},
        ]):
            resp = admin_client.get(
                f"/api/essay/admin/assignments/{assignment.id}/reports/bulk-download/?student_search=target@",
            )
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = set(zf.namelist())
        assert f"{target_sub.id}.html" in names
        assert f"{other_sub.id}.html" not in names

    def test_institution_isolation(self, admin_b_client):
        assignment, _ = _make_assignment(institution_id=INSTITUTION_A)
        resp = admin_b_client.get(f"/api/essay/admin/assignments/{assignment.id}/reports/bulk-download/")
        assert resp.status_code == 404

    def test_student_role_rejected(self, student_client):
        assignment, _ = _make_assignment()
        resp = student_client.get(f"/api/essay/admin/assignments/{assignment.id}/reports/bulk-download/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestDeadLetteringTaskSubmissionAudit:
    """Phase 11's own final-audit round: a permanently-DLQ'd
    generate_essay_report failure previously left NO trace on the
    affected submission's own EssaySubmissionEvent audit trail (Task
    6.1's "full audit-log/event trail" promise) — DeadLetteringTask.
    on_failure() wrote the EssayFailedJob row but never logged a
    SUBMISSION_EVENT_DLQ_RECORDED event the way evaluate_essay's own
    manual _record_dlq() path already does. Fixed by gating a new
    _log_submission_event() call on _SUBMISSION_SCOPED_TASK_NAMES.

    Calls on_failure() directly on the REAL, already-registered task
    instances (generate_essay_report / sweep_expired_assignments), via
    push_request()/pop_request() for a controlled fake retries count —
    not a bare SimpleNamespace fake self (on_failure's own `super()` call
    requires a genuine Task instance; a plain fake object fails Python's
    own isinstance check there) — matching test_evaluate_essay.py's own
    TestRetryCeilingHelper precedent of calling the real production
    function/method directly rather than re-driving Celery's full retry
    loop, which its own docstring explains can't reliably reach a
    ceiling-exceeded state in a single eager-mode test invocation."""

    def test_generate_essay_report_failure_logs_a_submission_event(self):
        from essays.tasks import generate_essay_report
        assignment, eset = _make_assignment()
        _, _, submission = _ready_submission(assignment, eset)

        generate_essay_report.push_request(retries=3)
        try:
            generate_essay_report.on_failure(
                RuntimeError("template bug"), "task-id-1", [str(submission.id)], {}, None,
            )
        finally:
            generate_essay_report.pop_request()

        assert EssayFailedJob.objects.filter(
            task_name="essays.tasks.generate_essay_report", args=[str(submission.id)],
        ).exists()
        event = EssaySubmissionEvent.objects.get(submission=submission, event_type=SUBMISSION_EVENT_DLQ_RECORDED)
        assert "template bug" in event.detail

    def test_send_essay_report_email_failure_logs_a_submission_event(self):
        # Same gap, same fix, found during Phase 13's own audit:
        # send_essay_report_email has the identical shape to
        # generate_essay_report (submission-scoped, DeadLetteringTask)
        # but was missing from _SUBMISSION_SCOPED_TASK_NAMES.
        assignment, eset = _make_assignment()
        _, _, submission = _ready_submission(assignment, eset)

        send_essay_report_email.push_request(retries=3)
        try:
            send_essay_report_email.on_failure(
                RuntimeError("smtp down"), "task-id-3", [str(submission.id), "student@example.com"], {}, None,
            )
        finally:
            send_essay_report_email.pop_request()

        assert EssayFailedJob.objects.filter(
            task_name="essays.tasks.send_essay_report_email", args=[str(submission.id), "student@example.com"],
        ).exists()
        event = EssaySubmissionEvent.objects.get(submission=submission, event_type=SUBMISSION_EVENT_DLQ_RECORDED)
        assert "smtp down" in event.detail

    def test_sweep_task_failure_does_not_touch_any_submission_event(self):
        # The two sweep tasks also use DeadLetteringTask but aren't
        # submission-scoped (their own `args` isn't a submission id at
        # all) — must not crash or write a bogus event.
        from essays.tasks import sweep_expired_assignments
        assignment, eset = _make_assignment()
        _, _, submission = _ready_submission(assignment, eset)
        before = EssaySubmissionEvent.objects.filter(submission=submission).count()

        sweep_expired_assignments.push_request(retries=3)
        try:
            sweep_expired_assignments.on_failure(RuntimeError("x"), "task-id-2", [], {}, None)
        finally:
            sweep_expired_assignments.pop_request()

        assert EssaySubmissionEvent.objects.filter(submission=submission).count() == before
