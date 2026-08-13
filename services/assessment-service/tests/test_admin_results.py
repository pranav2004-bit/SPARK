import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, Question, QuestionOption, BatchAssignment,
    AssessmentSession, AssessmentResponse, ActivityLog, ResultSummary,
    ASSIGNMENT_STATUS_LIVE, SESSION_STATUS_SUBMITTED, SESSION_STATUS_AUTO_SUBMITTED,
    ACTIVITY_EVENT_TAB_SWITCH,
)

from .conftest import INSTITUTION_A, INSTITUTION_B, ADMIN_USER_ID


def _roster_entry(user_id, student_id, fullname, department):
    return {"user_id": str(user_id), "student_id": student_id, "fullname": fullname, "department": department}


@pytest.fixture
def results_setup(db):
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Results Test Paper",
        created_by=ADMIN_USER_ID, is_published=True,
    )
    qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    q1 = Question.objects.create(set=qset, question_text="Q1", marks=5)
    opt_correct = QuestionOption.objects.create(question=q1, label="A", text="right", is_correct=True, order=1)
    opt_wrong = QuestionOption.objects.create(question=q1, label="B", text="wrong", order=2)

    batch_id = uuid.uuid4()
    assignment = BatchAssignment.objects.create(
        paper=paper, batch_id=batch_id, institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
    )

    student_a = uuid.uuid4()
    student_b = uuid.uuid4()

    session_a = AssessmentSession.objects.create(
        assignment=assignment, student_id=student_a, set=qset,
        ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_SUBMITTED,
        started_at=timezone.now() - timedelta(minutes=20),
    )
    AssessmentResponse.objects.create(
        session=session_a, question=q1, selected_option_ids=[str(opt_correct.id)],
        is_correct=True, marks_awarded=5,
    )
    result_a = ResultSummary.objects.create(
        session=session_a, assignment=assignment, student_id=student_a, institution_id=INSTITUTION_A,
        started_at=session_a.started_at, ended_at=timezone.now(), duration_seconds=1200,
        score=5, total_marks=5, status=SESSION_STATUS_SUBMITTED,
        malpractice_flag=False, malpractice_reasons=[],
    )

    session_b = AssessmentSession.objects.create(
        assignment=assignment, student_id=student_b, set=qset,
        ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_AUTO_SUBMITTED,
        started_at=timezone.now() - timedelta(minutes=10),
    )
    ActivityLog.objects.create(session=session_b, event_type=ACTIVITY_EVENT_TAB_SWITCH, occurred_at=timezone.now())
    result_b = ResultSummary.objects.create(
        session=session_b, assignment=assignment, student_id=student_b, institution_id=INSTITUTION_A,
        started_at=session_b.started_at, ended_at=timezone.now(), duration_seconds=600,
        score=0, total_marks=5, status=SESSION_STATUS_AUTO_SUBMITTED,
        malpractice_flag=True, malpractice_reasons=["tab_switch"],
    )

    roster = [
        _roster_entry(student_a, "ROLL-001", "Alice A", "CSE"),
        _roster_entry(student_b, "ROLL-002", "Bob B", "ECE"),
    ]

    return {
        "assignment": assignment, "qset": qset, "q1": q1,
        "result_a": result_a, "result_b": result_b,
        "session_a": session_a, "session_b": session_b,
        "roster": roster,
    }


# ── Task 7.1: results table ──────────────────────────────────────────────────

class TestResultsTable:
    @patch("assessments.views.fetch_batch_roster")
    def test_returns_all_required_fields(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/")

        assert resp.status_code == 200
        rows = resp.json()["results"]
        assert len(rows) == 2
        row = next(r for r in rows if r["student_roll_id"] == "ROLL-001")
        assert row["student_name"] == "Alice A"
        assert row["department"] == "CSE"
        assert row["score"] == 5
        assert row["total_marks"] == 5
        assert row["percentage"] == 100.0

    @patch("assessments.views.fetch_batch_roster")
    def test_department_filter(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?department=ECE")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["student_roll_id"] == "ROLL-002"

    @patch("assessments.views.fetch_batch_roster")
    def test_flagged_only_filter(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?flagged_only=true")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["malpractice_flag"] is True

    @patch("assessments.views.fetch_batch_roster")
    def test_percentage_range_filter(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?min_percentage=50")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["percentage"] == 100.0

    @patch("assessments.views.fetch_batch_roster")
    def test_sort_by_percentage_ascending(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?sort=percentage")
        rows = resp.json()["results"]
        assert [r["percentage"] for r in rows] == [0.0, 100.0]

    @patch("assessments.views.fetch_batch_roster")
    def test_invalid_sort_falls_back_to_default(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]
        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?sort=student_name;DROP")
        assert resp.status_code == 200  # falls back cleanly, doesn't error

    @patch("assessments.views.fetch_batch_roster")
    def test_roster_fetched_once_not_per_row(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]
        admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/")
        assert mock_roster.call_count == 1

    def test_cross_institution_403(self, admin_b_client, results_setup):
        assignment = results_setup["assignment"]
        resp = admin_b_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/")
        assert resp.status_code == 404

    @patch("assessments.views.fetch_batch_roster")
    def test_empty_assignment_no_error(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = []
        paper = results_setup["assignment"].paper
        empty_assignment = BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
        )
        resp = admin_client.get(f"/api/assessments/admin/assignments/{empty_assignment.id}/results/")
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    @patch("assessments.views.fetch_batch_roster")
    def test_roster_failure_returns_502(self, mock_roster, admin_client, results_setup):
        mock_roster.side_effect = RuntimeError("user-service unreachable")
        assignment = results_setup["assignment"]
        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/")
        assert resp.status_code == 502

    def test_student_forbidden(self, student_client, results_setup):
        resp = student_client.get(f"/api/assessments/admin/assignments/{results_setup['assignment'].id}/results/")
        assert resp.status_code == 403


# ── Task 7.2: responses & logs ───────────────────────────────────────────────

class TestResultResponses:
    def test_shows_answer_vs_correct_per_question(self, admin_client, results_setup):
        result_a = results_setup["result_a"]
        resp = admin_client.get(f"/api/assessments/admin/results/{result_a.id}/responses/")

        assert resp.status_code == 200
        questions = resp.json()["data"]["questions"]
        assert len(questions) == 1
        q = questions[0]
        assert q["is_correct"] is True
        assert q["marks_awarded"] == 5
        assert q["answered"] is True
        correct_ids = [o["id"] for o in q["options"] if o["is_correct"]]
        assert q["selected_option_ids"] == correct_ids

    def test_unanswered_question_shown_clearly(self, admin_client, results_setup):
        # result_b's session never answered q1 at all.
        result_b = results_setup["result_b"]
        resp = admin_client.get(f"/api/assessments/admin/results/{result_b.id}/responses/")
        q = resp.json()["data"]["questions"][0]
        assert q["answered"] is False
        assert q["selected_option_ids"] == []
        assert q["is_correct"] is False

    def test_cross_institution_403(self, admin_b_client, results_setup):
        resp = admin_b_client.get(f"/api/assessments/admin/results/{results_setup['result_a'].id}/responses/")
        assert resp.status_code == 404

    def test_student_forbidden(self, student_client, results_setup):
        resp = student_client.get(f"/api/assessments/admin/results/{results_setup['result_a'].id}/responses/")
        assert resp.status_code == 403


class TestResultLogs:
    def test_shows_full_trace_with_reasons(self, admin_client, results_setup):
        result_b = results_setup["result_b"]
        resp = admin_client.get(f"/api/assessments/admin/results/{result_b.id}/logs/")

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["malpractice_flag"] is True
        assert body["malpractice_reasons"] == ["tab_switch"]
        assert len(body["logs"]) == 1
        assert body["logs"][0]["event_type"] == "tab_switch"

    def test_unflagged_session_empty_reasons(self, admin_client, results_setup):
        result_a = results_setup["result_a"]
        resp = admin_client.get(f"/api/assessments/admin/results/{result_a.id}/logs/")
        body = resp.json()["data"]
        assert body["malpractice_flag"] is False
        assert body["logs"] == []

    def test_cross_institution_403(self, admin_b_client, results_setup):
        resp = admin_b_client.get(f"/api/assessments/admin/results/{results_setup['result_b'].id}/logs/")
        assert resp.status_code == 404

    def test_paginated_not_unbounded(self, admin_client, results_setup):
        # Task 11.1's pagination audit: this endpoint was previously an
        # unbounded query — a single session sitting at the throttle
        # ceiling for a whole exam window could return everything in one
        # response. "copy" doesn't trip any malpractice threshold, so this
        # purely exercises pagination without touching result_a's existing
        # unflagged-session assertions elsewhere in this fixture.
        session_a = results_setup["session_a"]
        ActivityLog.objects.bulk_create([
            ActivityLog(session=session_a, event_type="copy", occurred_at=timezone.now())
            for _ in range(65)
        ])
        resp = admin_client.get(f"/api/assessments/admin/results/{results_setup['result_a'].id}/logs/")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["count"] == 65
        assert len(body["logs"]) == 50  # StandardResultsPagination's default page_size
        assert body["total_pages"] == 2
        assert body["current_page"] == 1

        resp_page2 = admin_client.get(f"/api/assessments/admin/results/{results_setup['result_a'].id}/logs/?page=2")
        body2 = resp_page2.json()["data"]
        assert len(body2["logs"]) == 15
        assert body2["current_page"] == 2


# ── Task 7.3: CSV export ─────────────────────────────────────────────────────

class TestResultsExport:
    @patch("assessments.views.fetch_batch_roster")
    def test_export_contains_bom_header_and_rows(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/export/")
        content = b"".join(resp.streaming_content).decode("utf-8")

        assert resp.status_code == 200
        assert content.startswith("﻿")
        assert "Student Roll No" in content
        assert "ROLL-001" in content
        assert "ROLL-002" in content

    @patch("assessments.views.fetch_batch_roster")
    def test_export_respects_same_filters_as_table(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/export/?department=ECE")
        content = b"".join(resp.streaming_content).decode("utf-8")

        assert "ROLL-002" in content
        assert "ROLL-001" not in content

    def test_cross_institution_403(self, admin_b_client, results_setup):
        assignment = results_setup["assignment"]
        resp = admin_b_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/export/")
        assert resp.status_code == 404

    @patch("assessments.views.fetch_batch_roster")
    def test_load_5000_rows_streams(self, mock_roster, admin_client, results_setup):
        import time

        assignment, qset = results_setup["assignment"], results_setup["qset"]
        roster = list(results_setup["roster"])
        extra_sessions = []
        for i in range(5000):
            sid = uuid.uuid4()
            s = AssessmentSession(
                assignment=assignment, student_id=sid, set=qset,
                ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_SUBMITTED,
                started_at=timezone.now() - timedelta(minutes=15),
            )
            extra_sessions.append(s)
            roster.append(_roster_entry(sid, f"ROLL-BULK-{i:05d}", f"Student {i}", "CSE"))
        AssessmentSession.objects.bulk_create(extra_sessions)
        ResultSummary.objects.bulk_create([
            ResultSummary(
                session=s, assignment=assignment, student_id=s.student_id, institution_id=INSTITUTION_A,
                started_at=s.started_at, ended_at=timezone.now(), duration_seconds=900,
                score=3, total_marks=5, status=SESSION_STATUS_SUBMITTED,
            )
            for s in extra_sessions
        ])
        mock_roster.return_value = roster

        start = time.monotonic()
        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/export/")
        content = b"".join(resp.streaming_content).decode("utf-8")
        elapsed = time.monotonic() - start

        # header + BOM-prefixed header + 5002 data rows (2 original + 5000 bulk)
        assert content.count("\n") >= 5002
        assert elapsed < 30, f"export of ~5000 rows took {elapsed:.1f}s"
