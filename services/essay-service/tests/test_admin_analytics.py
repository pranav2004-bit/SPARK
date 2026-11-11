"""
test_admin_analytics.py — Phase 9, Task 9.1's own testing checklist: hand-
computed fixture verification, cross-institution isolation, and this
phase's own corrected caching design (a plain 60s TTL, not explicit
invalidation — see AdminEssayAssignmentAnalyticsView's own module-header
comment in essays/views.py for why Task 9.1's literal "explicit
invalidation" instruction was corrected before any code was written
against it). The test that would have been "cache invalidation fires on a
new score landing" is replaced by its own inverse: proving the cache
genuinely serves a stale value within the TTL window, since that's the
actual, deliberate behavior this design produces.
"""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from essays.models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayStudentSetAllocation, EssayAttempt,
    EssaySubmission, EssayScore, ATTEMPT_STATUS_SUBMITTED, ATTEMPT_STATUS_IN_PROGRESS,
    SUBMISSION_STATUS_LLM_COMPLETE, SUBMISSION_STATUS_LLM_FAILED,
    MALPRACTICE_EVENT_TEXT_SIMILARITY,
)

from .conftest import INSTITUTION_A, ADMIN_USER_ID


def _make_assignment(*, institution_id=INSTITUTION_A):
    paper = EssayPaper.objects.create(institution_id=institution_id, title="Analytics Test Paper", created_by=ADMIN_USER_ID)
    eset = EssaySet.objects.create(paper=paper, label="Set A", order=1)
    EssayQuestion.objects.create(set=eset, question_text="Q", llm_rubric_prompt="R", word_limit=500, time_limit_minutes=30)
    assignment = EssayAssignment.objects.create(
        paper=paper, batch_id=uuid.uuid4(), institution_id=institution_id,
        global_expire_time=timezone.now() + timedelta(hours=3), created_by=ADMIN_USER_ID,
    )
    return assignment, eset


def _allocate_and_score(assignment, eset, *, score, word_count, feedback=None, malpractice_reasons=None,
                          status=ATTEMPT_STATUS_SUBMITTED, submission_status=SUBMISSION_STATUS_LLM_COMPLETE):
    student_id = uuid.uuid4()
    EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=student_id, set=eset)
    attempt = EssayAttempt.objects.create(
        assignment=assignment, student_id=student_id, set=eset,
        ends_at=timezone.now() + timedelta(hours=1), status=status,
        draft_response=" ".join(["word"] * word_count),
        malpractice_flag=bool(malpractice_reasons), malpractice_reasons=malpractice_reasons or [],
    )
    submission = EssaySubmission.objects.create(attempt=attempt)
    EssaySubmission.objects.filter(pk=submission.pk).update(status=submission_status)
    if score is not None:
        EssayScore.objects.create(submission=submission, score=score, feedback=feedback or {"overall": "x"})
    return student_id, attempt, submission


@pytest.mark.django_db
class TestAnalyticsHandComputedFixture:
    def test_numbers_match_a_known_fixture(self, admin_client):
        assignment, eset = _make_assignment()
        # Two students haven't started; three are scored (6, 8, 10); one
        # is LLM_FAILED; one is flagged for plagiarism.
        EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=uuid.uuid4(), set=eset)
        EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=uuid.uuid4(), set=eset)
        _allocate_and_score(assignment, eset, score=6, word_count=100)
        _allocate_and_score(assignment, eset, score=8, word_count=200)
        _allocate_and_score(assignment, eset, score=10, word_count=300)
        _allocate_and_score(assignment, eset, score=None, word_count=50, submission_status=SUBMISSION_STATUS_LLM_FAILED)
        _allocate_and_score(assignment, eset, score=7, word_count=150, malpractice_reasons=[MALPRACTICE_EVENT_TEXT_SIMILARITY])

        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        assert resp.status_code == 200
        data = resp.data["data"]

        assert data["total_allocated"] == 7
        assert data["total_submitted"] == 5  # every _allocate_and_score() call, all terminal-status attempts
        assert data["total_scored"] == 4  # the 4 that got an EssayScore (not the LLM_FAILED one)
        assert data["average_score"] == 7.75  # (6 + 8 + 10 + 7) / 4

        dist = {row["score"]: row["count"] for row in data["score_distribution"]}
        assert dist[6] == 1 and dist[8] == 1 and dist[10] == 1 and dist[7] == 1
        assert dist[0] == 0

        # 1 of 5 submitted attempts is plagiarism-flagged
        assert data["plagiarism_flag_rate_percentage"] == 20.0
        # 1 of 5 submissions ended up LLM_FAILED
        assert data["llm_failure_rate_percentage"] == 20.0

    def test_word_count_vs_score(self, admin_client):
        assignment, eset = _make_assignment()
        _allocate_and_score(assignment, eset, score=8, word_count=100)
        _allocate_and_score(assignment, eset, score=8, word_count=300)  # same score, different word count -> averaged
        _allocate_and_score(assignment, eset, score=5, word_count=50)

        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        wcvs = {row["score"]: row for row in resp.data["data"]["word_count_vs_score"]}
        assert wcvs[8]["average_word_count"] == 200.0  # (100 + 300) / 2
        assert wcvs[8]["count"] == 2
        assert wcvs[5]["average_word_count"] == 50.0
        # A score with zero submissions is not included at all, not a
        # spurious {average_word_count: 0} entry.
        assert 0 not in wcvs
        assert 10 not in wcvs

    def test_weakest_criterion(self, admin_client):
        assignment, eset = _make_assignment()
        _allocate_and_score(assignment, eset, score=6, word_count=100, feedback={
            "overall": "x", "breakdown": {
                "Clarity": {"score": 2, "maxScore": 5, "feedback": "weak"},
                "Grammar": {"score": 4, "maxScore": 5, "feedback": "fine"},
            },
        })
        _allocate_and_score(assignment, eset, score=7, word_count=100, feedback={
            "overall": "x", "breakdown": {
                "Clarity": {"score": 1, "maxScore": 5, "feedback": "weak"},
                "Grammar": {"score": 5, "maxScore": 5, "feedback": "fine"},
            },
        })

        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        weakest = resp.data["data"]["weakest_criterion"]
        assert weakest["name"] == "Clarity"
        assert weakest["weak_count"] == 2
        assert weakest["total_count"] == 2
        assert weakest["weak_rate_percentage"] == 100.0

    def test_weakest_criterion_tie_break_is_deterministic(self, admin_client):
        # Real gap found by this phase's own final-audit round: a plain
        # max() with no tie-break, fed from a query with no .order_by(),
        # meant a genuine tie between two criteria's own weak counts
        # could resolve to a different "winner" across different
        # cache-miss recomputations of the SAME underlying data — never
        # reproducible from a single test run alone, but real. Fixed
        # with an explicit tie-break (highest weak, then highest total,
        # then alphabetically first) — asserted here directly, not left
        # to chance: "Aardvark" and "Zebra" are both weak in exactly one
        # of one appearances (a genuine tie on both weak_count and
        # total_count), so the alphabetical rule is what actually
        # decides, and must decide the same way every time.
        assignment, eset = _make_assignment()
        _allocate_and_score(assignment, eset, score=6, word_count=100, feedback={
            "overall": "x", "breakdown": {
                "Zebra": {"score": 1, "maxScore": 5, "feedback": "weak"},
                "Aardvark": {"score": 1, "maxScore": 5, "feedback": "weak"},
            },
        })
        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        assert resp.data["data"]["weakest_criterion"]["name"] == "Aardvark"

    def test_weakest_criterion_null_when_nothing_is_weak(self, admin_client):
        assignment, eset = _make_assignment()
        _allocate_and_score(assignment, eset, score=9, word_count=100, feedback={
            "overall": "x", "breakdown": {"Clarity": {"score": 5, "maxScore": 5, "feedback": "great"}},
        })
        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        assert resp.data["data"]["weakest_criterion"] is None

    def test_weakest_criterion_null_with_no_scored_submissions(self, admin_client):
        assignment, eset = _make_assignment()
        EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=uuid.uuid4(), set=eset)
        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        data = resp.data["data"]
        assert data["weakest_criterion"] is None
        assert data["average_score"] is None
        assert data["score_distribution"] == [{"score": i, "count": 0} for i in range(11)]

    def test_not_yet_started_students_excluded_from_plagiarism_denominator(self, admin_client):
        # A student with no attempt at all was never eligible for the
        # text-similarity check — including them in the denominator would
        # understate the real rate among students who actually submitted.
        assignment, eset = _make_assignment()
        EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=uuid.uuid4(), set=eset)
        _allocate_and_score(assignment, eset, score=8, word_count=100, malpractice_reasons=[MALPRACTICE_EVENT_TEXT_SIMILARITY])

        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        # 1 of 1 SUBMITTED attempt flagged — not 1 of 2 allocated.
        assert resp.data["data"]["plagiarism_flag_rate_percentage"] == 100.0

    def test_llm_failure_rate_shares_the_same_visible_denominator_as_plagiarism_rate(self, admin_client):
        # Real gap found by this phase's own third final-audit round:
        # llm_failure_rate_percentage used to divide by a separately-
        # computed EssaySubmission count that was never itself exposed
        # anywhere in the response — an admin would see "LLM failure
        # rate: X%" with no visible denominator at all. Fixed to share
        # total_submitted (already displayed as the "Submitted" stat
        # tile) with plagiarism_flag_rate_percentage, so both rates on
        # the page now read against the same visible population.
        assignment, eset = _make_assignment()
        _allocate_and_score(assignment, eset, score=8, word_count=100)
        student_id = uuid.uuid4()
        EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=student_id, set=eset)
        attempt = EssayAttempt.objects.create(
            assignment=assignment, student_id=student_id, set=eset,
            ends_at=timezone.now() + timedelta(hours=1), status=ATTEMPT_STATUS_SUBMITTED,
        )
        submission = EssaySubmission.objects.create(attempt=attempt)
        EssaySubmission.objects.filter(pk=submission.pk).update(status=SUBMISSION_STATUS_LLM_FAILED)

        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        data = resp.data["data"]
        assert data["total_submitted"] == 2  # the ONE visible denominator both rates now read against
        assert data["llm_failure_rate_percentage"] == 50.0  # 1 of 2
        assert data["plagiarism_flag_rate_percentage"] == 0.0  # 0 of 2

    def test_in_progress_attempt_does_not_count_as_submitted(self, admin_client):
        assignment, eset = _make_assignment()
        student_id = uuid.uuid4()
        EssayStudentSetAllocation.objects.create(assignment=assignment, student_id=student_id, set=eset)
        EssayAttempt.objects.create(
            assignment=assignment, student_id=student_id, set=eset,
            ends_at=timezone.now() + timedelta(hours=1), status=ATTEMPT_STATUS_IN_PROGRESS,
        )
        resp = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        data = resp.data["data"]
        assert data["total_allocated"] == 1
        assert data["total_submitted"] == 0


@pytest.mark.django_db
class TestAnalyticsCaching:
    def test_second_request_within_ttl_serves_the_cached_value(self, admin_client):
        # Proves this phase's own corrected design (plain 60s TTL, not
        # explicit invalidation — see the view's own module-header
        # comment) actually caches: change the underlying data between
        # two requests and confirm the SECOND one still returns the
        # FIRST, stale value, rather than recomputing.
        assignment, eset = _make_assignment()
        _allocate_and_score(assignment, eset, score=5, word_count=100)

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        assert first.data["data"]["total_scored"] == 1

        _allocate_and_score(assignment, eset, score=9, word_count=100)  # a genuinely new score lands

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        assert second.data["data"]["total_scored"] == 1  # still the stale, cached value
        assert second.data["data"]["generated_at"] == first.data["data"]["generated_at"]

    def test_refresh_true_bypasses_the_cache(self, admin_client):
        # Real gap found by this phase's own second final-audit round:
        # the frontend's own "Refresh" button had no way to actually
        # bypass the cache, so it could silently re-serve the exact same
        # stale data — a genuine inconsistency with the LLM Controls
        # page's own always-fresh "Refresh" button (Phase 7). Confirms
        # the fix: unlike the plain-request test above, a request that
        # sets ?refresh=true DOES see the newly-landed score.
        assignment, eset = _make_assignment()
        _allocate_and_score(assignment, eset, score=5, word_count=100)

        first = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        assert first.data["data"]["total_scored"] == 1

        _allocate_and_score(assignment, eset, score=9, word_count=100)

        second = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/", {"refresh": "true"})
        assert second.data["data"]["total_scored"] == 2  # the fresh value, not the stale cached one

        # And the fresh value is itself now cached for the NEXT plain load.
        third = admin_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        assert third.data["data"]["total_scored"] == 2

    def test_different_assignments_have_independent_cache_entries(self, admin_client):
        assignment1, eset1 = _make_assignment()
        assignment2, eset2 = _make_assignment()
        _allocate_and_score(assignment1, eset1, score=3, word_count=100)
        _allocate_and_score(assignment2, eset2, score=9, word_count=100)

        resp1 = admin_client.get(f"/api/essay/admin/assignments/{assignment1.id}/analytics/")
        resp2 = admin_client.get(f"/api/essay/admin/assignments/{assignment2.id}/analytics/")
        assert resp1.data["data"]["average_score"] == 3.0
        assert resp2.data["data"]["average_score"] == 9.0


@pytest.mark.django_db
class TestAnalyticsPermissionsAndIsolation:
    def test_institution_isolated_404(self, admin_client, admin_b_client):
        assignment, eset = _make_assignment()
        resp = admin_b_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        assert resp.status_code == 404

    def test_unauthenticated_rejected(self, anon_client):
        assignment, eset = _make_assignment()
        resp = anon_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        assert resp.status_code == 401

    def test_student_role_rejected(self, student_client):
        assignment, eset = _make_assignment()
        resp = student_client.get(f"/api/essay/admin/assignments/{assignment.id}/analytics/")
        assert resp.status_code == 403

    def test_nonexistent_assignment_404(self, admin_client):
        resp = admin_client.get(f"/api/essay/admin/assignments/{uuid.uuid4()}/analytics/")
        assert resp.status_code == 404
