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
    def test_available_sets_lists_every_set_regardless_of_filters(self, mock_roster, admin_client, results_setup):
        # Drill-down target from Analytics' Set Fairness panel — each bar
        # links here with ?set=<label>.
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]
        qset_b = QuestionSet.objects.create(paper=assignment.paper, label="Set B", order=2)
        StudentSetAllocation.objects.filter(assignment=assignment, student_id=results_setup["student_d"]).update(set=qset_b)

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?set=Set+B")
        assert resp.status_code == 200
        body = resp.json()
        rows = body["results"]
        assert len(rows) == 1
        assert rows[0]["student_roll_id"] == "ROLL-004"
        # Stays the full roster's set list even while ?set= itself is
        # narrowing the table — otherwise the frontend's Set dropdown would
        # shrink to one option the moment a set filter is applied.
        assert body["available_sets"] == ["Set A", "Set B"]

    @patch("assessments.views.fetch_batch_roster")
    def test_set_filter_unknown_label_returns_no_rows(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/results/?set=Nonexistent")
        assert resp.json()["results"] == []

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


class TestQuestionResponses:
    """The cross-student counterpart to TestResultResponses above — one
    question, every student on that question's set — the Analytics page's
    Per-Question Difficulty drill-down target."""

    @patch("assessments.views.fetch_batch_roster")
    def test_shows_every_students_answer_to_the_question(self, mock_roster, admin_client, results_setup):
        mock_roster.return_value = results_setup["roster"]
        assignment = results_setup["assignment"]
        q1 = results_setup["q1"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/questions/{q1.id}/responses/")

        assert resp.status_code == 200
        body = resp.json()
        assert body["question_number"] == q1.question_number
        assert body["set_label"] == "Set A"
        assert body["marks"] == 5
        assert len(body["options"]) == 2

        students = {s["student_roll_id"]: s for s in body["students"]}
        assert len(students) == 4  # all 4 students allocated to Set A

        alice = students["ROLL-001"]  # submitted, answered correctly
        assert alice["answered"] is True
        assert alice["is_correct"] is True
        assert alice["exam_status"] == "submitted"

        bob = students["ROLL-002"]  # auto-submitted (malpractice), never answered q1 at all
        assert bob["answered"] is False
        assert bob["is_correct"] is False
        assert bob["exam_status"] == "submitted"

        carol = students["ROLL-003"]  # pending — never started, no session at all
        assert carol["answered"] is False
        assert carol["exam_status"] == "pending"

        dave = students["ROLL-004"]  # writing — session exists, no response yet
        assert dave["answered"] is False
        assert dave["exam_status"] == "writing"

    @patch("assessments.views.fetch_batch_roster")
    def test_students_on_a_different_set_are_excluded_not_shown_as_unanswered(self, mock_roster, admin_client, results_setup):
        assignment = results_setup["assignment"]
        q1 = results_setup["q1"]

        # A second set on the same assignment, with its own allocation — a
        # student here never had q1 (it belongs to Set A only), so they must
        # not appear at all, not show up as a false "not answered" row.
        qset_b = QuestionSet.objects.create(paper=assignment.paper, label="Set B", order=2)
        other_student = uuid.uuid4()
        StudentSetAllocation.objects.create(assignment=assignment, student_id=other_student, set=qset_b)
        mock_roster.return_value = results_setup["roster"] + [_roster_entry(other_student, "ROLL-005", "Eve E", "CSE")]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/questions/{q1.id}/responses/")
        rolls = {s["student_roll_id"] for s in resp.json()["students"]}
        assert rolls == {"ROLL-001", "ROLL-002", "ROLL-003", "ROLL-004"}

    def test_cross_institution_404(self, admin_b_client, results_setup):
        assignment = results_setup["assignment"]
        q1 = results_setup["q1"]
        resp = admin_b_client.get(f"/api/assessments/admin/assignments/{assignment.id}/questions/{q1.id}/responses/")
        assert resp.status_code == 404

    def test_student_forbidden(self, student_client, results_setup):
        assignment = results_setup["assignment"]
        q1 = results_setup["q1"]
        resp = student_client.get(f"/api/assessments/admin/assignments/{assignment.id}/questions/{q1.id}/responses/")
        assert resp.status_code == 403


class TestSessionTimeline:
    """The plain-English "logs/tracking" popup (eye icon in the results
    table) — keyed by session_id, not result_id, since it also has to work
    for a student who's still mid-exam (session_d: no ResultSummary yet)."""

    def test_submitted_session_shows_start_and_submit_bookends(self, admin_client, results_setup):
        session_a = results_setup["session_a"]
        resp = admin_client.get(f"/api/assessments/admin/sessions/{session_a.id}/timeline/")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["exam_status"] == "submitted"
        assert body["malpractice_flag"] is False
        assert body["malpractice_reasons"] == []
        assert body["retention_days"] == 15
        assert [e["description"] for e in body["events"]] == ["Started the exam", "Submitted the exam"]

    def test_auto_submitted_session_shows_plain_english_violation_and_timeout_message(self, admin_client, results_setup):
        session_b = results_setup["session_b"]
        resp = admin_client.get(f"/api/assessments/admin/sessions/{session_b.id}/timeline/")
        body = resp.json()["data"]
        assert body["exam_status"] == "submitted"
        assert body["malpractice_flag"] is True
        descriptions = [e["description"] for e in body["events"]]
        assert descriptions == [
            "Started the exam",
            "Switched away to another browser tab",
            "Exam was submitted automatically because time ran out",
        ]
        # No raw technical event-type strings in the narrative timeline
        # itself (malpractice_reasons is a separate structured field and
        # legitimately keeps the raw reason code) — the plain-English
        # description is the whole point of this feature.
        assert all("tab_switch" not in e["description"] for e in body["events"])

    def test_in_progress_session_has_no_closing_event_yet(self, admin_client, results_setup):
        session_d = results_setup["session_d"]
        resp = admin_client.get(f"/api/assessments/admin/sessions/{session_d.id}/timeline/")
        body = resp.json()["data"]
        assert body["exam_status"] == "writing"
        assert [e["description"] for e in body["events"]] == ["Started the exam"]
        assert body["malpractice_flag"] is False

    def test_cross_institution_404(self, admin_b_client, results_setup):
        resp = admin_b_client.get(f"/api/assessments/admin/sessions/{results_setup['session_a'].id}/timeline/")
        assert resp.status_code == 404

    def test_nonexistent_session_404(self, admin_client):
        resp = admin_client.get(f"/api/assessments/admin/sessions/{uuid.uuid4()}/timeline/")
        assert resp.status_code == 404

    def test_event_count_is_capped_but_reports_the_true_total(self, admin_client, results_setup):
        session_a = results_setup["session_a"]
        from assessments.views import _SESSION_TIMELINE_EVENT_CAP
        ActivityLog.objects.bulk_create([
            ActivityLog(session=session_a, event_type="copy", occurred_at=timezone.now())
            for _ in range(_SESSION_TIMELINE_EVENT_CAP + 5)
        ])
        resp = admin_client.get(f"/api/assessments/admin/sessions/{session_a.id}/timeline/")
        body = resp.json()["data"]
        assert body["total_event_count"] == _SESSION_TIMELINE_EVENT_CAP + 5
        assert body["truncated"] is True
        # +2 for the "Started"/"Submitted" bookends around the capped logs.
        assert len(body["events"]) == _SESSION_TIMELINE_EVENT_CAP + 2

    def test_unrecognized_event_type_still_gets_a_plain_english_fallback(self, admin_client, results_setup):
        # Defensive: today every ACTIVITY_EVENT_TYPE_CHOICES member has a
        # mapping, but a future event type landing here without one must
        # never leak a raw technical string to a non-technical viewer.
        session_a = results_setup["session_a"]
        ActivityLog.objects.create(session=session_a, event_type="paste", occurred_at=timezone.now())
        from assessments import views as views_module
        with patch.dict(views_module._ACTIVITY_EVENT_PLAIN_ENGLISH, {}, clear=True):
            resp = admin_client.get(f"/api/assessments/admin/sessions/{session_a.id}/timeline/")
        descriptions = [e["description"] for e in resp.json()["data"]["events"]]
        assert "Unrecognized activity was recorded" in descriptions

    def test_dynamic_events_render_their_per_occurrence_detail(self, admin_client, results_setup):
        # 2026-08-18 full-transparency events: unlike the fixed one-liners
        # (tab_switch etc.), these four carry per-occurrence detail in
        # metadata that must actually show up in the sentence, not just a
        # generic label.
        session_a = results_setup["session_a"]
        ActivityLog.objects.create(session=session_a, event_type="question_answered", occurred_at=timezone.now(), metadata={"question_number": 3})
        ActivityLog.objects.create(session=session_a, event_type="question_answer_changed", occurred_at=timezone.now(), metadata={"question_number": 3})
        ActivityLog.objects.create(session=session_a, event_type="admin_extended_time", occurred_at=timezone.now(), metadata={"added_minutes": 15})
        ActivityLog.objects.create(session=session_a, event_type="connection_lost", occurred_at=timezone.now(), metadata={"duration_seconds": 125})
        ActivityLog.objects.create(session=session_a, event_type="screenshot_attempt", occurred_at=timezone.now(), metadata={})

        resp = admin_client.get(f"/api/assessments/admin/sessions/{session_a.id}/timeline/")
        descriptions = [e["description"] for e in resp.json()["data"]["events"]]

        assert "Answered Question 3" in descriptions
        assert "Changed the answer for Question 3" in descriptions
        assert "Exam time was extended by 15 minute(s)" in descriptions
        assert "Lost internet connection for about 2.1 minute(s)" in descriptions
        assert "Attempted to take a screenshot" in descriptions
        # No raw event_type strings or metadata keys leak into the sentences.
        joined = " ".join(descriptions)
        for raw in ("question_answered", "question_answer_changed", "admin_extended_time", "connection_lost", "screenshot_attempt", "added_minutes", "duration_seconds"):
            assert raw not in joined

    def test_dynamic_events_fall_back_gracefully_without_metadata(self, admin_client, results_setup):
        # Edge case: metadata missing/empty (shouldn't happen in practice
        # since both writers always populate it, but the description must
        # never crash or show "None" if it somehow is).
        session_a = results_setup["session_a"]
        ActivityLog.objects.create(session=session_a, event_type="question_answered", occurred_at=timezone.now(), metadata={})
        ActivityLog.objects.create(session=session_a, event_type="admin_extended_time", occurred_at=timezone.now(), metadata={})
        ActivityLog.objects.create(session=session_a, event_type="connection_lost", occurred_at=timezone.now(), metadata={})

        resp = admin_client.get(f"/api/assessments/admin/sessions/{session_a.id}/timeline/")
        descriptions = [e["description"] for e in resp.json()["data"]["events"]]

        assert "Answered a question" in descriptions
        assert "Exam time was extended" in descriptions
        assert "Lost internet connection" in descriptions
        assert not any("None" in d for d in descriptions)


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
