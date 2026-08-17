import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, Question, QuestionOption, BatchAssignment,
    AssessmentSession, AssessmentResponse, ActivityLog, ResultSummary, StudentSetAllocation,
    ASSIGNMENT_STATUS_LIVE, SESSION_STATUS_SUBMITTED, SESSION_STATUS_AUTO_SUBMITTED,
    SESSION_STATUS_IN_PROGRESS, ACTIVITY_EVENT_TAB_SWITCH,
)

from .conftest import INSTITUTION_A, INSTITUTION_B, ADMIN_USER_ID


def _roster_entry(user_id, student_id, fullname, department):
    return {"user_id": str(user_id), "student_id": student_id, "fullname": fullname, "department": department}


@pytest.fixture
def results_setup(db):
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Results Test Paper",
        created_by=ADMIN_USER_ID,
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
    student_c = uuid.uuid4()  # allocated, never started — "pending"
    student_d = uuid.uuid4()  # allocated, session in progress — "writing"

    # The roster snapshot every allocated student gets at assignment-creation
    # time (Task 3.1) — this is what makes them show up in the results table
    # at all, even before they've started. Real code path: snapshot_roster_
    # and_allocate(); constructed directly here since these tests only exercise
    # the read side.
    for student_id in (student_a, student_b, student_c, student_d):
        StudentSetAllocation.objects.create(assignment=assignment, student_id=student_id, set=qset)

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

    # student_c: allocated only, no session at all — pending.
    # student_d: session exists, still in progress — writing. No ResultSummary
    # for either — that's only ever written at finalize time.
    session_d = AssessmentSession.objects.create(
        assignment=assignment, student_id=student_d, set=qset,
        ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_IN_PROGRESS,
        started_at=timezone.now() - timedelta(minutes=5),
    )

    roster = [
        _roster_entry(student_a, "ROLL-001", "Alice A", "CSE"),
        _roster_entry(student_b, "ROLL-002", "Bob B", "ECE"),
        _roster_entry(student_c, "ROLL-003", "Carol C", "CSE"),
        _roster_entry(student_d, "ROLL-004", "Dave D", "CSE"),
    ]

    return {
        "assignment": assignment, "qset": qset, "q1": q1,
        "result_a": result_a, "result_b": result_b,
        "session_a": session_a, "session_b": session_b, "session_d": session_d,
        "student_c": student_c, "student_d": student_d,
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
        # 4 allocated students total, not just the 2 who've submitted — the
        # whole point of this endpoint now being roster-based (Live bug
        # report, 2026-08-14): "No results yet" used to hide every student
        # who hadn't finished, including ones still writing.
        assert len(rows) == 4
        row = next(r for r in rows if r["student_roll_id"] == "ROLL-001")
        assert row["student_name"] == "Alice A"
        assert row["department"] == "CSE"
        assert row["set_label"] == "Set A"
        assert row["exam_status"] == "submitted"
        assert row["score"] == 5
        assert row["total_marks"] == 5
        assert row["percentage"] == 100.0

    @patch("assessments.views.fetch_batch_roster")
    def test_pending_and_writing_students_visible_with_no_score(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/")
        rows = {r["student_roll_id"]: r for r in resp.json()["results"]}

        pending = rows["ROLL-003"]
        assert pending["exam_status"] == "pending"
        assert pending["result_id"] is None
        assert pending["score"] is None
        assert pending["percentage"] is None

        writing = rows["ROLL-004"]
        assert writing["exam_status"] == "writing"
        assert writing["result_id"] is None
        assert writing["score"] is None

    @patch("assessments.views.fetch_batch_roster")
    def test_department_filter(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?department=ECE")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["student_roll_id"] == "ROLL-002"

    @patch("assessments.views.fetch_batch_roster")
    def test_roll_id_search_exact_match(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?student_roll_id=ROLL-001")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["student_roll_id"] == "ROLL-001"

    @patch("assessments.views.fetch_batch_roster")
    def test_roll_id_search_partial_substring_match(self, mock_roster, admin_client, results_setup):
        # "001" is a substring in the middle of "ROLL-001" — not just a
        # prefix match — matching how admins actually search (they rarely
        # remember the full roll number).
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?student_roll_id=001")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["student_roll_id"] == "ROLL-001"

    @patch("assessments.views.fetch_batch_roster")
    def test_roll_id_search_case_insensitive(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?student_roll_id=roll-002")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["student_roll_id"] == "ROLL-002"

    @patch("assessments.views.fetch_batch_roster")
    def test_roll_id_search_no_match_returns_empty(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?student_roll_id=ZZZZZ")
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    @patch("assessments.views.fetch_batch_roster")
    def test_roll_id_search_blank_or_whitespace_ignored(self, mock_roster, admin_client, results_setup):
        # Empty string and whitespace-only both mean "no search applied" —
        # neither should filter out every row.
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp_empty = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?student_roll_id=")
        assert len(resp_empty.json()["results"]) == 4

        resp_ws = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?student_roll_id=%20%20")
        assert len(resp_ws.json()["results"]) == 4

    @patch("assessments.views.fetch_batch_roster")
    def test_roll_id_search_composes_with_department_filter(self, mock_roster, admin_client, results_setup):
        # Both filters must AND together, not one silently overwriting the
        # other — ROLL-002 also contains "00" but is ECE, not CSE.
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(
            f"/api/assessments/admin/assignments/{assignment.id}/results/?department=CSE&student_roll_id=00"
        )
        rolls = {r["student_roll_id"] for r in resp.json()["results"]}
        assert rolls == {"ROLL-001", "ROLL-003", "ROLL-004"}

    @patch("assessments.views.fetch_batch_roster")
    def test_flagged_only_filter(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?flagged_only=true")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["malpractice_flag"] is True

    @patch("assessments.views.fetch_batch_roster")
    def test_flagged_false_filter_includes_pending_and_writing(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?flagged=false")
        rolls = {r["student_roll_id"] for r in resp.json()["results"]}
        # ROLL-002 (Bob) is the only flagged student — everyone else,
        # including the pending/writing students who have no malpractice_flag
        # yet at all (NULL, not False), counts as "not flagged".
        assert rolls == {"ROLL-001", "ROLL-003", "ROLL-004"}

    @patch("assessments.views.fetch_batch_roster")
    def test_passed_true_filter(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]  # default 40% cutoff

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?passed=true")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["student_roll_id"] == "ROLL-001"  # 100% >= 40%

    @patch("assessments.views.fetch_batch_roster")
    def test_passed_false_filter_excludes_pending_and_writing(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?passed=false")
        rows = resp.json()["results"]
        # ROLL-002 scored 0% (< 40% cutoff) and has actually submitted —
        # ROLL-003/ROLL-004 (pending/writing, no percentage yet) must NOT
        # be counted as "failed" just because they haven't passed.
        assert len(rows) == 1
        assert rows[0]["student_roll_id"] == "ROLL-002"

    @patch("assessments.views.fetch_batch_roster")
    def test_exam_status_filter_pending(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?exam_status=pending")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["student_roll_id"] == "ROLL-003"

    @patch("assessments.views.fetch_batch_roster")
    def test_exam_status_filter_writing(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?exam_status=writing")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["student_roll_id"] == "ROLL-004"

    @patch("assessments.views.fetch_batch_roster")
    def test_exam_status_filter_submitted(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?exam_status=submitted")
        rolls = {r["student_roll_id"] for r in resp.json()["results"]}
        assert rolls == {"ROLL-001", "ROLL-002"}

    @patch("assessments.views.fetch_batch_roster")
    def test_exam_status_invalid_value_ignored(self, mock_roster, admin_client, results_setup):
        # An unrecognised value silently falls back to no filter, same
        # defense-in-depth convention as the sort= param's allowlist below.
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?exam_status=bogus")
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 4

    @patch("assessments.views.fetch_batch_roster")
    def test_percentage_range_filter(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?min_percentage=50")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["percentage"] == 100.0

    @patch("assessments.views.fetch_batch_roster")
    def test_min_percentage_boundary_is_exclusive(self, mock_roster, admin_client, results_setup):
        # "above x%" — a student scoring exactly x% must NOT be included.
        # student_b scored exactly 0%.
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?min_percentage=0")
        rows = resp.json()["results"]
        assert len(rows) == 1
        assert rows[0]["student_roll_id"] == "ROLL-001"

    @patch("assessments.views.fetch_batch_roster")
    def test_max_percentage_boundary_is_inclusive(self, mock_roster, admin_client, results_setup):
        # "below y%" — a student scoring exactly y% MUST be included.
        # student_a scored exactly 100%.
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?max_percentage=100")
        rolls = {r["student_roll_id"] for r in resp.json()["results"]}
        assert rolls == {"ROLL-001", "ROLL-002"}

    @patch("assessments.views.fetch_batch_roster")
    def test_percentage_between_range_excludes_lower_includes_upper(self, mock_roster, admin_client, results_setup):
        # "between 0 and 0" — combining an exclusive lower bound with an
        # inclusive upper bound at the same value must match nobody, proving
        # the two params compose correctly rather than each being evaluated
        # in isolation.
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(
            f"/api/assessments/admin/assignments/{assignment.id}/results/?min_percentage=0&max_percentage=0"
        )
        assert resp.json()["results"] == []

    @patch("assessments.views.fetch_batch_roster")
    def test_sort_by_percentage_ascending(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?sort=percentage")
        rows = resp.json()["results"]
        percentages = [r["percentage"] for r in rows]
        # The 2 submitted students sort first (lowest score first), the 2
        # pending/writing students (no percentage yet) come after — NULLS
        # LAST is Postgres's default for ascending order.
        assert percentages[:2] == [0.0, 100.0]
        assert percentages[2:] == [None, None]

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
        StudentSetAllocation.objects.bulk_create([
            StudentSetAllocation(assignment=assignment, student_id=s.student_id, set=qset)
            for s in extra_sessions
        ])
        mock_roster.return_value = roster

        start = time.monotonic()
        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/export/")
        content = b"".join(resp.streaming_content).decode("utf-8")
        elapsed = time.monotonic() - start

        # header + BOM-prefixed header + 5004 data rows (4 original allocated
        # students — 2 submitted, 1 pending, 1 writing — + 5000 bulk)
        assert content.count("\n") >= 5004
        assert elapsed < 30, f"export of ~5000 rows took {elapsed:.1f}s"
