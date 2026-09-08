import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from assessments.models import (
    QuestionPaper, QuestionSet, Question, QuestionOption, BatchAssignment,
    AssessmentSession, AssessmentResponse, ResultSummary, StudentSetAllocation,
    ASSIGNMENT_STATUS_LIVE, SESSION_STATUS_SUBMITTED,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID


def _roster_entry(user_id, department):
    return {"user_id": str(user_id), "student_id": f"ROLL-{str(user_id)[:8]}", "fullname": "X", "department": department}


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def analytics_setup(db):
    """Hand-computable fixture — see test_admin_analytics.py's docstring-level
    comment below for the full manual computation this is built from."""
    paper = QuestionPaper.objects.create(
        institution_id=INSTITUTION_A, title="Analytics Test Paper",
        created_by=ADMIN_USER_ID,
    )
    set_a = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
    set_b = QuestionSet.objects.create(paper=paper, label="Set B", order=2)

    a_q1 = Question.objects.create(set=set_a, question_text="A1", marks=3)
    a_q1_correct = QuestionOption.objects.create(question=a_q1, label="A", text="r", is_correct=True, order=1)
    a_q1_wrong = QuestionOption.objects.create(question=a_q1, label="B", text="w", order=2)
    a_q2 = Question.objects.create(set=set_a, question_text="A2", marks=2)
    a_q2_correct = QuestionOption.objects.create(question=a_q2, label="A", text="r", is_correct=True, order=1)

    b_q1 = Question.objects.create(set=set_b, question_text="B1", marks=7)
    b_q1_correct = QuestionOption.objects.create(question=b_q1, label="A", text="r", is_correct=True, order=1)
    b_q1_wrong = QuestionOption.objects.create(question=b_q1, label="B", text="w", order=2)
    b_q2 = Question.objects.create(set=set_b, question_text="B2", marks=3)
    b_q2_correct = QuestionOption.objects.create(question=b_q2, label="A", text="r", is_correct=True, order=1)

    assignment = BatchAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
        global_expire_time=timezone.now() + timedelta(hours=3),
        exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
        pass_cutoff_percentage=40,
    )

    students = {
        "student_1": uuid.uuid4(),  # Set A, CSE — 100%
        "student_2": uuid.uuid4(),  # Set A, CSE — 0%, flagged
        "student_3": uuid.uuid4(),  # Set B, ECE — 100%
        "student_4": uuid.uuid4(),  # Set B, ECE — 30%
    }

    def _make(student_key, qset, responses, score, total_marks, flagged=False):
        sid = students[student_key]
        session = AssessmentSession.objects.create(
            assignment=assignment, student_id=sid, set=qset,
            ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_SUBMITTED,
            started_at=timezone.now() - timedelta(minutes=10),
        )
        for question, opt, is_correct, marks in responses:
            AssessmentResponse.objects.create(
                session=session, question=question, selected_option_ids=[str(opt.id)] if opt else [],
                is_correct=is_correct, marks_awarded=marks,
            )
        ResultSummary.objects.create(
            session=session, assignment=assignment, student_id=sid, institution_id=INSTITUTION_A,
            started_at=session.started_at, ended_at=timezone.now(), duration_seconds=600,
            score=score, total_marks=total_marks, status=SESSION_STATUS_SUBMITTED,
            malpractice_flag=flagged, malpractice_reasons=["tab_switch"] if flagged else [],
        )

    _make("student_1", set_a, [(a_q1, a_q1_correct, True, 3), (a_q2, a_q2_correct, True, 2)], 5, 5)
    _make("student_2", set_a, [(a_q1, a_q1_wrong, False, 0)], 0, 5, flagged=True)  # A2 unanswered
    _make("student_3", set_b, [(b_q1, b_q1_correct, True, 7), (b_q2, b_q2_correct, True, 3)], 10, 10)
    _make("student_4", set_b, [(b_q1, b_q1_wrong, False, 0), (b_q2, b_q2_correct, True, 3)], 3, 10)

    # Every completed student's own StudentSetAllocation row (the roster
    # snapshot any real assignment creates for everyone it's assigned to,
    # Task 3.1) — plus two more allocated students who never started, so
    # total_allocated (6) is genuinely greater than total_completed (4),
    # not just equal to it by fixture accident.
    for key in students:
        StudentSetAllocation.objects.create(assignment=assignment, student_id=students[key], set=set_a)
    students["student_5_pending"] = uuid.uuid4()
    students["student_6_pending"] = uuid.uuid4()
    StudentSetAllocation.objects.create(assignment=assignment, student_id=students["student_5_pending"], set=set_a)
    StudentSetAllocation.objects.create(assignment=assignment, student_id=students["student_6_pending"], set=set_b)

    roster = [
        _roster_entry(students["student_1"], "CSE"),
        _roster_entry(students["student_2"], "CSE"),
        _roster_entry(students["student_3"], "ECE"),
        _roster_entry(students["student_4"], "ECE"),
    ]

    return {"assignment": assignment, "roster": roster, "students": students}


class TestAnalytics:
    @patch("assessments.views.fetch_batch_roster")
    def test_hand_computed_values_match_exactly(self, mock_roster, admin_client, analytics_setup):
        mock_roster.return_value = analytics_setup["roster"]
        assignment = analytics_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/")
        assert resp.status_code == 200
        data = resp.json()["data"]

        assert data["total_completed"] == 4
        assert data["total_allocated"] == 6  # 4 completed + 2 who never started
        assert "generated_at" in data and data["generated_at"]

        # Average score: mean of 100, 0, 100, 30 = 57.5
        assert data["average_score_percentage"] == 57.5

        # Average completion time: all 4 fixture sessions use duration_seconds=600
        assert data["average_completion_time_seconds"] == 600
        assert data["exam_duration_minutes"] == 60

        # Pass/fail: cutoff 40%, pass = student_1(100%), student_3(100%) = 2
        pf = data["pass_fail"]
        assert pf["pass_count"] == 2
        assert pf["fail_count"] == 2
        assert pf["pass_rate_percentage"] == 50.0
        assert pf["cutoff_percentage"] == 40

        # Distribution: 0% -> bucket 0, 30% -> bucket 3, 100%x2 -> bucket 9
        dist = {d["bucket"]: d["count"] for d in data["score_distribution"]}
        assert dist["0-10%"] == 1
        assert dist["30-40%"] == 1
        assert dist["90-100%"] == 2
        assert sum(dist.values()) == 4

        # Department comparison: CSE avg(100,0)=50.0, ECE avg(100,30)=65.0
        dept = {d["department"]: d for d in data["department_comparison"]}
        assert dept["CSE"]["average_percentage"] == 50.0
        assert dept["CSE"]["student_count"] == 2
        assert dept["ECE"]["average_percentage"] == 65.0
        assert dept["ECE"]["student_count"] == 2

        # Malpractice: 1 flagged of 4 = 25%
        mp = data["malpractice_rate"]
        assert mp["flagged_count"] == 1
        assert mp["total_count"] == 4
        assert mp["rate_percentage"] == 25.0

        # Malpractice breakdown: student_2 alone, flagged for tab_switch only
        assert data["malpractice_breakdown"] == [{"reason": "tab_switch", "count": 1}]

        # Set comparison: Set A avg(100,0)=50.0, Set B avg(100,30)=65.0
        sets = {s["set_label"]: s for s in data["set_comparison"]}
        assert sets["Set A"]["average_percentage"] == 50.0
        assert sets["Set A"]["student_count"] == 2
        assert sets["Set B"]["average_percentage"] == 65.0
        assert sets["Set B"]["student_count"] == 2

        # Question difficulty
        diff_by_number_and_set = {(q["set_label"], q["question_number"]): q for q in data["question_difficulty"]}
        a1 = diff_by_number_and_set[("Set A", 1)]
        assert a1["total_answered"] == 2 and a1["correct_count"] == 1 and a1["percentage_correct"] == 50.0
        assert a1["average_seconds_spent"] is None  # no question_time_spent events in this fixture
        a2 = diff_by_number_and_set[("Set A", 2)]
        assert a2["total_answered"] == 1 and a2["correct_count"] == 1 and a2["percentage_correct"] == 100.0
        b1 = diff_by_number_and_set[("Set B", 1)]
        assert b1["total_answered"] == 2 and b1["correct_count"] == 1 and b1["percentage_correct"] == 50.0
        b2 = diff_by_number_and_set[("Set B", 2)]
        assert b2["total_answered"] == 2 and b2["correct_count"] == 2 and b2["percentage_correct"] == 100.0

        assert "metric_definitions" in data

    @patch("assessments.views.fetch_batch_roster")
    def test_cross_set_percentage_used_not_raw_score(self, mock_roster, admin_client, analytics_setup):
        # student_3 (score 10) and student_1 (score 5) both scored 100% on
        # their own set — raw-score comparison would wrongly suggest
        # student_3 "did better." Percentage-based distribution/pass-fail
        # must treat them identically.
        mock_roster.return_value = analytics_setup["roster"]
        assignment = analytics_setup["assignment"]
        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/")
        dist = {d["bucket"]: d["count"] for d in resp.json()["data"]["score_distribution"]}
        assert dist["90-100%"] == 2  # both land in the same bucket despite different raw scores/total_marks

    @patch("assessments.views.fetch_batch_roster")
    def test_cache_hit_avoids_recomputation(self, mock_roster, admin_client, analytics_setup):
        mock_roster.return_value = analytics_setup["roster"]
        assignment = analytics_setup["assignment"]

        admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/")
        admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/")
        admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/")

        assert mock_roster.call_count == 1  # only the first call actually computed anything

    def test_cross_institution_403(self, admin_b_client, analytics_setup):
        resp = admin_b_client.get(f"/api/assessments/admin/assignments/{analytics_setup['assignment'].id}/analytics/")
        assert resp.status_code == 404

    @patch("assessments.views.fetch_batch_roster")
    def test_zero_completed_sessions_no_division_by_zero(self, mock_roster, admin_client, analytics_setup):
        mock_roster.return_value = []
        paper = analytics_setup["assignment"].paper
        empty_assignment = BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
        )
        resp = admin_client.get(f"/api/assessments/admin/assignments/{empty_assignment.id}/analytics/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_completed"] == 0
        assert data["total_allocated"] == 0
        assert data["average_score_percentage"] is None  # never a misleading 0.0 — genuinely no data yet
        assert data["average_completion_time_seconds"] is None
        assert data["pass_fail"]["pass_rate_percentage"] == 0.0
        assert data["malpractice_rate"]["rate_percentage"] == 0.0
        assert data["set_comparison"] == []
        assert data["malpractice_breakdown"] == []
        assert all(q["percentage_correct"] is None for q in data["question_difficulty"])
        assert all(q["average_seconds_spent"] is None for q in data["question_difficulty"])

    @patch("assessments.views.fetch_batch_roster")
    def test_one_student_no_crash(self, mock_roster, admin_client, analytics_setup):
        # Reuses student_1 only, via a filtered query — just confirms no
        # division-by-zero even at n=1 for department/pass-fail averages.
        mock_roster.return_value = analytics_setup["roster"][:1]
        assignment = analytics_setup["assignment"]
        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/")
        assert resp.status_code == 200

    def test_student_forbidden(self, student_client, analytics_setup):
        resp = student_client.get(f"/api/assessments/admin/assignments/{analytics_setup['assignment'].id}/analytics/")
        assert resp.status_code == 403


class TestAnalyticsExport:
    @patch("assessments.views.fetch_batch_roster")
    def test_export_contains_all_sections(self, mock_roster, admin_client, analytics_setup):
        mock_roster.return_value = analytics_setup["roster"]
        assignment = analytics_setup["assignment"]

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/export/")
        content = resp.content.decode("utf-8")

        assert resp.status_code == 200
        assert content.startswith("﻿")
        for section in ["Assessment Analytics", "Score Distribution", "Pass / Fail Summary",
                         "Per-Question Difficulty", "Department Comparison", "Set Comparison",
                         "Malpractice Rate", "Malpractice Breakdown by Reason"]:
            assert section in content
        assert "50.0" in content  # CSE department average, sanity check real numbers made it in
        assert "57.5" in content  # average score
        assert "4 / 6" in content  # completed / allocated
        assert "Average Completion Time" in content
        assert "Exam Duration Allowed" in content

    def test_cross_institution_403(self, admin_b_client, analytics_setup):
        resp = admin_b_client.get(f"/api/assessments/admin/assignments/{analytics_setup['assignment'].id}/analytics/export/")
        assert resp.status_code == 404


# ── Average time per question (2026-08-18) ───────────────────────────────────

class TestQuestionTimeSpent:
    def _session_for(self, assignment, students, key):
        return AssessmentSession.objects.get(assignment=assignment, student_id=students[key])

    @patch("assessments.views.fetch_batch_roster")
    def test_averages_across_sessions_on_the_same_set(self, mock_roster, admin_client, analytics_setup):
        from assessments.models import ActivityLog, ACTIVITY_EVENT_QUESTION_TIME_SPENT
        mock_roster.return_value = analytics_setup["roster"]
        assignment, students = analytics_setup["assignment"], analytics_setup["students"]

        # student_1 and student_2 are both on Set A — two data points for
        # Set A's Question 1, must average, not just take one.
        for key, seconds in [("student_1", 40), ("student_2", 60)]:
            ActivityLog.objects.create(
                session=self._session_for(assignment, students, key),
                event_type=ACTIVITY_EVENT_QUESTION_TIME_SPENT,
                occurred_at=timezone.now(), metadata={"question_number": 1, "seconds": seconds},
            )

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/")
        diff_by = {(q["set_label"], q["question_number"]): q for q in resp.json()["data"]["question_difficulty"]}
        assert diff_by[("Set A", 1)]["average_seconds_spent"] == 50.0  # (40+60)/2

    @patch("assessments.views.fetch_batch_roster")
    def test_disambiguates_the_same_question_number_across_different_sets(self, mock_roster, admin_client, analytics_setup):
        # Set A's "Question 1" and Set B's "Question 1" are different actual
        # Questions — a naive question_number-only aggregation would wrongly
        # merge these two students' times together. Deliberately different
        # values so a merge bug would be caught immediately.
        from assessments.models import ActivityLog, ACTIVITY_EVENT_QUESTION_TIME_SPENT
        mock_roster.return_value = analytics_setup["roster"]
        assignment, students = analytics_setup["assignment"], analytics_setup["students"]

        ActivityLog.objects.create(
            session=self._session_for(assignment, students, "student_1"),  # Set A
            event_type=ACTIVITY_EVENT_QUESTION_TIME_SPENT,
            occurred_at=timezone.now(), metadata={"question_number": 1, "seconds": 20},
        )
        ActivityLog.objects.create(
            session=self._session_for(assignment, students, "student_3"),  # Set B
            event_type=ACTIVITY_EVENT_QUESTION_TIME_SPENT,
            occurred_at=timezone.now(), metadata={"question_number": 1, "seconds": 200},
        )

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/")
        diff_by = {(q["set_label"], q["question_number"]): q for q in resp.json()["data"]["question_difficulty"]}
        assert diff_by[("Set A", 1)]["average_seconds_spent"] == 20.0
        assert diff_by[("Set B", 1)]["average_seconds_spent"] == 200.0

    @patch("assessments.views.fetch_batch_roster")
    def test_malformed_or_zero_metadata_excluded_not_treated_as_zero(self, mock_roster, admin_client, analytics_setup):
        from assessments.models import ActivityLog, ACTIVITY_EVENT_QUESTION_TIME_SPENT
        mock_roster.return_value = analytics_setup["roster"]
        assignment, students = analytics_setup["assignment"], analytics_setup["students"]
        session = self._session_for(assignment, students, "student_1")

        for metadata in [
            {"question_number": 1},              # missing seconds
            {"seconds": 30},                      # missing question_number
            {"question_number": 1, "seconds": 0}, # zero — excluded, not counted as a real 0s data point
            {"question_number": 1, "seconds": -5},
        ]:
            ActivityLog.objects.create(
                session=session, event_type=ACTIVITY_EVENT_QUESTION_TIME_SPENT,
                occurred_at=timezone.now(), metadata=metadata,
            )

        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/")
        diff_by = {(q["set_label"], q["question_number"]): q for q in resp.json()["data"]["question_difficulty"]}
        assert diff_by[("Set A", 1)]["average_seconds_spent"] is None  # nothing valid contributed

    @patch("assessments.views.fetch_batch_roster")
    def test_a_question_with_no_time_data_stays_null_not_zero(self, mock_roster, admin_client, analytics_setup):
        # No question_time_spent events at all anywhere in this fixture —
        # every question's average must be null (unknown), never a
        # misleading 0 that looks like "everyone answered instantly."
        mock_roster.return_value = analytics_setup["roster"]
        assignment = analytics_setup["assignment"]
        resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment.id}/analytics/")
        assert all(q["average_seconds_spent"] is None for q in resp.json()["data"]["question_difficulty"])
