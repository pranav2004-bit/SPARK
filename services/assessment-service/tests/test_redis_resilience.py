"""
Task 13.1 — Redis graceful-degradation tests.

The test settings' CACHES backend is LocMemCache (core/test_settings.py),
not Redis, so it can never actually raise redis.exceptions.RedisError —
these tests simulate a Redis outage by patching django.core.cache.cache's
get/set/delete methods to raise directly, which exercises the exact
exception-handling path core/cache_utils.py and
core/throttling_resilience.py add, without needing a real Redis instance
to kill. A live Docker-stack verification (actually stopping the redis
container) was also done separately for this task — see
LIVETRACKER2_V1.md's Task 13.1 notes — this file is the automated,
repeatable half of that verification.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
import redis.exceptions
from django.core.cache import cache
from django.utils import timezone

from core.cache_utils import safe_cache_get, safe_cache_set, safe_cache_delete
from assessments.models import (
    QuestionPaper, QuestionSet, Question, QuestionOption, BatchAssignment,
    AssessmentSession, SESSION_STATUS_IN_PROGRESS, ASSIGNMENT_STATUS_LIVE, MCQ_TYPE_SINGLE,
)
from assessments.scoring import finalize_sessions
from assessments.models import SESSION_STATUS_SUBMITTED

from .conftest import INSTITUTION_A, ADMIN_USER_ID, STUDENT_USER_ID


class TestCacheUtils:
    def test_safe_get_returns_default_on_redis_error(self, db):
        with patch.object(cache, "get", side_effect=redis.exceptions.ConnectionError("down")):
            assert safe_cache_get("some_key") is None
            assert safe_cache_get("some_key", default="fallback") == "fallback"

    def test_safe_set_silently_no_ops_on_redis_error(self, db):
        with patch.object(cache, "set", side_effect=redis.exceptions.ConnectionError("down")):
            safe_cache_set("some_key", {"x": 1}, 60)  # must not raise

    def test_safe_delete_silently_no_ops_on_redis_error(self, db):
        with patch.object(cache, "delete", side_effect=redis.exceptions.ConnectionError("down")):
            safe_cache_delete("some_key")  # must not raise

    def test_safe_get_still_works_normally_when_redis_is_fine(self, db):
        cache.set("real_key", "real_value", 60)
        assert safe_cache_get("real_key") == "real_value"
        cache.delete("real_key")


class TestAnalyticsDashboardDegradeOnRedisFailure:
    @pytest.fixture
    def assignment_setup(self, db):
        paper = QuestionPaper.objects.create(
            institution_id=INSTITUTION_A, title="Redis Resilience Paper",
            created_by=ADMIN_USER_ID,
        )
        qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
        assignment = BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
        )
        return assignment

    def test_dashboard_still_works_when_redis_read_fails(self, admin_client, assignment_setup):
        with patch.object(cache, "get", side_effect=redis.exceptions.ConnectionError("down")):
            resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment_setup.id}/dashboard/")
        assert resp.status_code == 200
        assert resp.json()["data"]["assignment_id"] == str(assignment_setup.id)

    def test_dashboard_still_works_when_redis_write_fails(self, admin_client, assignment_setup):
        with patch.object(cache, "set", side_effect=redis.exceptions.ConnectionError("down")):
            resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment_setup.id}/dashboard/")
        assert resp.status_code == 200

    @patch("assessments.views.fetch_batch_roster")
    def test_analytics_still_works_when_redis_read_fails(self, mock_roster, admin_client, assignment_setup):
        mock_roster.return_value = []
        with patch.object(cache, "get", side_effect=redis.exceptions.ConnectionError("down")):
            resp = admin_client.get(f"/api/assessments/admin/assignments/{assignment_setup.id}/analytics/")
        assert resp.status_code == 200


class TestFinalizeSessionsSurvivesRedisFailure:
    def test_submit_succeeds_even_if_dashboard_cache_invalidation_fails(self, db):
        paper = QuestionPaper.objects.create(
            institution_id=INSTITUTION_A, title="X", created_by=ADMIN_USER_ID,
        )
        qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
        assignment = BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
        )
        session = AssessmentSession.objects.create(
            assignment=assignment, student_id=STUDENT_USER_ID, set=qset,
            ends_at=timezone.now() + timedelta(hours=1), status=SESSION_STATUS_IN_PROGRESS,
        )

        with patch.object(cache, "delete", side_effect=redis.exceptions.ConnectionError("down")):
            count = finalize_sessions(
                AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_SUBMITTED,
            )

        # The whole point: finalize_sessions() must not raise, and the
        # session must actually be finalized, even though the dashboard
        # cache-invalidation side effect inside it hit a dead Redis.
        assert count == 1
        session.refresh_from_db()
        assert session.status == SESSION_STATUS_SUBMITTED


class TestThrottleFailsOpenOnRedisFailure:
    def test_answer_submit_throttle_allows_request_when_redis_down(self, db):
        paper = QuestionPaper.objects.create(
            institution_id=INSTITUTION_A, title="X", created_by=ADMIN_USER_ID,
        )
        qset = QuestionSet.objects.create(paper=paper, label="Set A", order=1)
        q = Question.objects.create(set=qset, question_text="Q", marks=1, mcq_type=MCQ_TYPE_SINGLE)
        opt = QuestionOption.objects.create(question=q, label="A", text="x", is_correct=True, order=1)
        assignment = BatchAssignment.objects.create(
            paper=paper, batch_id=uuid.uuid4(), institution_id=INSTITUTION_A,
            global_expire_time=timezone.now() + timedelta(hours=3),
            exam_duration_minutes=60, created_by=ADMIN_USER_ID, status=ASSIGNMENT_STATUS_LIVE,
        )
        session = AssessmentSession.objects.create(
            assignment=assignment, student_id=STUDENT_USER_ID, set=qset,
            ends_at=timezone.now() + timedelta(hours=1),
        )

        from .conftest import _make_token
        from rest_framework.test import APIClient
        token = _make_token(STUDENT_USER_ID, "student", INSTITUTION_A, student_id=STUDENT_USER_ID)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        with patch.object(cache, "get", side_effect=redis.exceptions.ConnectionError("down")):
            resp = client.put(
                f"/api/assessments/student/sessions/{session.id}/questions/{q.id}/answer/",
                {"selected_option_ids": [str(opt.id)]}, format="json",
            )
        # Fails open: the request is allowed through (not throttled), not
        # rejected with a 500 from the dead cache backend.
        assert resp.status_code == 200
