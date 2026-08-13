import uuid
import pytest
from analytics.models import (
    PracticeEvent, ResourceViewEvent, DailyEngagementSnapshot, InstitutionSnapshot
)
from tests.conftest import (
    STUDENT_USER_ID, ADMIN_USER_ID, SUPER_ADMIN_USER_ID,
    INSTITUTION_A, INSTITUTION_B,
    MODULE_ID, QUESTION_ID, COMPANY_ID, RESOURCE_ID,
    TEST_SERVICE_KEY,
)


# ─── Internal Event ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestInternalEvent:
    def _practice_payload(self, student_id=None, institution_id=None):
        return {
            "event_type": "practice_attempt",
            "student_id": str(student_id or STUDENT_USER_ID),
            "institution_id": str(institution_id or INSTITUTION_A),
            "module_id": str(MODULE_ID),
            "question_id": str(QUESTION_ID),
            "topic": "Algebra",
            "difficulty": "easy",
            "is_correct": True,
        }

    def _resource_payload(self):
        return {
            "event_type": "resource_view",
            "student_id": str(STUDENT_USER_ID),
            "institution_id": str(INSTITUTION_A),
            "company_id": str(COMPANY_ID),
            "resource_id": str(RESOURCE_ID),
        }

    def test_event_requires_service_key(self, anon_client):
        resp = anon_client.post(
            "/api/analytics/internal/event/", self._practice_payload(), format="json"
        )
        assert resp.status_code == 403

    def test_event_jwt_not_accepted(self, student_client):
        resp = student_client.post(
            "/api/analytics/internal/event/", self._practice_payload(), format="json"
        )
        assert resp.status_code == 403

    def test_practice_event_creates_record(self, db, service_client):
        resp = service_client.post(
            "/api/analytics/internal/event/", self._practice_payload(), format="json"
        )
        assert resp.status_code == 201
        assert PracticeEvent.objects.filter(student_id=STUDENT_USER_ID).count() == 1

    def test_resource_view_event_creates_record(self, db, service_client):
        resp = service_client.post(
            "/api/analytics/internal/event/", self._resource_payload(), format="json"
        )
        assert resp.status_code == 201
        assert ResourceViewEvent.objects.filter(student_id=STUDENT_USER_ID).count() == 1

    def test_practice_event_missing_module_id_returns_400(self, db, service_client):
        payload = self._practice_payload()
        del payload["module_id"]
        resp = service_client.post(
            "/api/analytics/internal/event/", payload, format="json"
        )
        assert resp.status_code == 400

    def test_resource_event_missing_company_id_returns_400(self, db, service_client):
        payload = self._resource_payload()
        del payload["company_id"]
        resp = service_client.post(
            "/api/analytics/internal/event/", payload, format="json"
        )
        assert resp.status_code == 400

    def test_invalid_event_type_returns_400(self, db, service_client):
        payload = self._practice_payload()
        payload["event_type"] = "unknown_type"
        resp = service_client.post(
            "/api/analytics/internal/event/", payload, format="json"
        )
        assert resp.status_code == 400

    def test_practice_event_invalidates_student_cache(self, db, service_client, student_client):
        from django.core.cache import cache
        # Cache key now includes institution_id to prevent cross-tenant poisoning.
        cache.set(f"analytics:student:{INSTITUTION_A}:{STUDENT_USER_ID}", {"cached": True}, 300)
        service_client.post(
            "/api/analytics/internal/event/", self._practice_payload(), format="json"
        )
        assert cache.get(f"analytics:student:{INSTITUTION_A}:{STUDENT_USER_ID}") is None

    def test_practice_event_invalidates_admin_cache(self, db, service_client):
        from django.core.cache import cache
        cache.set(f"analytics:admin:{INSTITUTION_A}:overview", {"cached": True}, 900)
        service_client.post(
            "/api/analytics/internal/event/", self._practice_payload(), format="json"
        )
        assert cache.get(f"analytics:admin:{INSTITUTION_A}:overview") is None


# ─── Student Analytics ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStudentAnalytics:
    def test_student_analytics_requires_auth(self, anon_client):
        resp = anon_client.get("/api/analytics/student/")
        assert resp.status_code == 401

    def test_admin_cannot_access_student_analytics(self, admin_client):
        resp = admin_client.get("/api/analytics/student/")
        assert resp.status_code == 403

    def test_student_analytics_zero_attempts(self, student_client):
        resp = student_client.get("/api/analytics/student/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_attempts"] == 0
        assert data["accuracy_percent"] == 0.0
        assert data["topic_breakdown"] == []
        assert data["practice_streak_days"] == 0

    def test_student_analytics_correct_counts(self, db, student_client):
        PracticeEvent.objects.bulk_create([
            PracticeEvent(student_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
                          module_id=MODULE_ID, question_id=QUESTION_ID,
                          topic="Algebra", difficulty="easy", is_correct=i % 2 == 0)
            for i in range(10)
        ])
        resp = student_client.get("/api/analytics/student/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_attempts"] == 10
        assert data["correct_attempts"] == 5
        assert data["accuracy_percent"] == 50.0

    def test_student_analytics_topic_breakdown(self, db, student_client):
        PracticeEvent.objects.bulk_create([
            PracticeEvent(student_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
                          module_id=MODULE_ID, question_id=QUESTION_ID,
                          topic="Algebra", difficulty="easy", is_correct=True)
            for _ in range(4)
        ])
        PracticeEvent.objects.bulk_create([
            PracticeEvent(student_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
                          module_id=MODULE_ID, question_id=QUESTION_ID,
                          topic="Geometry", difficulty="hard", is_correct=False)
            for _ in range(3)
        ])
        resp = student_client.get("/api/analytics/student/")
        data = resp.json()["data"]
        topics = {t["topic"]: t for t in data["topic_breakdown"]}
        assert "Algebra" in topics
        assert "Geometry" in topics
        assert topics["Algebra"]["accuracy"] == 100.0
        assert topics["Geometry"]["accuracy"] == 0.0

    def test_student_analytics_strong_and_weak_topics(self, db, student_client):
        PracticeEvent.objects.bulk_create([
            PracticeEvent(student_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
                          module_id=MODULE_ID, question_id=QUESTION_ID,
                          topic="Strong", difficulty="easy", is_correct=True)
            for _ in range(5)
        ])
        PracticeEvent.objects.bulk_create([
            PracticeEvent(student_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
                          module_id=MODULE_ID, question_id=QUESTION_ID,
                          topic="Weak", difficulty="hard", is_correct=False)
            for _ in range(5)
        ])
        resp = student_client.get("/api/analytics/student/")
        data = resp.json()["data"]
        strong_topics = [t["topic"] for t in data["strong_topics"]]
        weak_topics = [t["topic"] for t in data["weak_topics"]]
        assert "Strong" in strong_topics
        assert "Weak" in weak_topics

    def test_student_analytics_served_from_cache(self, db, student_client):
        from django.core.cache import cache
        # Cache key now includes institution_id to prevent cross-tenant poisoning.
        cache.set(f"analytics:student:{INSTITUTION_A}:{STUDENT_USER_ID}", {"cached_value": True}, 300)
        resp = student_client.get("/api/analytics/student/")
        assert resp.json()["data"]["cached_value"] is True

    def test_student_analytics_not_affected_by_other_student(self, db, student_client):
        other = uuid.uuid4()
        PracticeEvent.objects.create(
            student_id=other, institution_id=INSTITUTION_A,
            module_id=MODULE_ID, question_id=QUESTION_ID,
            topic="Algebra", difficulty="easy", is_correct=True,
        )
        resp = student_client.get("/api/analytics/student/")
        assert resp.json()["data"]["total_attempts"] == 0


# ─── Admin Overview ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminOverview:
    def test_admin_overview_requires_auth(self, anon_client):
        resp = anon_client.get("/api/analytics/admin/overview/")
        assert resp.status_code == 401

    def test_student_cannot_access_admin_overview(self, student_client):
        resp = student_client.get("/api/analytics/admin/overview/")
        assert resp.status_code == 403

    def test_super_admin_cannot_access_admin_overview(self, super_admin_client):
        resp = super_admin_client.get("/api/analytics/admin/overview/")
        assert resp.status_code == 403

    def test_admin_overview_no_snapshot_returns_zeros(self, admin_client):
        resp = admin_client.get("/api/analytics/admin/overview/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_students"] == 0
        assert data["practice_completion_rate"] == 0.0

    def test_admin_overview_returns_snapshot_data(self, admin_client, institution_snapshot):
        resp = admin_client.get("/api/analytics/admin/overview/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_students"] == 100
        assert data["total_active"] == 60
        assert data["practice_completion_rate"] == 72.5

    def test_admin_overview_cached(self, admin_client, institution_snapshot):
        from django.core.cache import cache
        resp1 = admin_client.get("/api/analytics/admin/overview/")
        cache.set(f"analytics:admin:{INSTITUTION_A}:overview", {"override": True}, 900)
        resp2 = admin_client.get("/api/analytics/admin/overview/")
        assert resp2.json()["data"]["override"] is True

    def test_admin_cannot_see_other_institution_snapshot(self, admin_b_client, institution_snapshot):
        resp = admin_b_client.get("/api/analytics/admin/overview/")
        assert resp.status_code == 200
        # institution B has no snapshot — should return zeros
        assert resp.json()["data"]["total_students"] == 0


# ─── Admin Top Performers ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminTopPerformers:
    def test_top_performers_requires_auth(self, anon_client):
        resp = anon_client.get("/api/analytics/admin/top-performers/")
        assert resp.status_code == 401

    def test_student_cannot_access_top_performers(self, student_client):
        resp = student_client.get("/api/analytics/admin/top-performers/")
        assert resp.status_code == 403

    def test_top_performers_returns_list(self, admin_client, practice_event):
        resp = admin_client.get("/api/analytics/admin/top-performers/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_top_performers_correct_fields(self, admin_client, practice_event):
        resp = admin_client.get("/api/analytics/admin/top-performers/")
        item = resp.json()["data"][0]
        assert "student_id" in item
        assert "total_attempts" in item
        assert "correct_attempts" in item
        assert "accuracy_percent" in item

    def test_top_performers_scoped_to_institution(self, admin_b_client, practice_event):
        resp = admin_b_client.get("/api/analytics/admin/top-performers/")
        assert resp.status_code == 200
        # Institution B has no events — empty list
        assert resp.json()["data"] == []

    def test_top_performers_max_10(self, db, admin_client):
        PracticeEvent.objects.bulk_create([
            PracticeEvent(student_id=uuid.uuid4(), institution_id=INSTITUTION_A,
                          module_id=MODULE_ID, question_id=QUESTION_ID,
                          topic="T", difficulty="easy", is_correct=True)
            for _ in range(15)
        ])
        resp = admin_client.get("/api/analytics/admin/top-performers/")
        assert len(resp.json()["data"]) <= 10


# ─── Admin Weak Topics ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminWeakTopics:
    def test_weak_topics_requires_auth(self, anon_client):
        resp = anon_client.get("/api/analytics/admin/weak-topics/")
        assert resp.status_code == 401

    def test_weak_topics_returns_list(self, admin_client, practice_event):
        resp = admin_client.get("/api/analytics/admin/weak-topics/")
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    def test_weak_topics_sorted_by_accuracy_asc(self, db, admin_client):
        PracticeEvent.objects.bulk_create([
            PracticeEvent(student_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
                          module_id=MODULE_ID, question_id=QUESTION_ID,
                          topic="Weak Topic", difficulty="hard", is_correct=False)
            for _ in range(3)
        ])
        PracticeEvent.objects.bulk_create([
            PracticeEvent(student_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
                          module_id=MODULE_ID, question_id=QUESTION_ID,
                          topic="Strong Topic", difficulty="easy", is_correct=True)
            for _ in range(3)
        ])
        resp = admin_client.get("/api/analytics/admin/weak-topics/")
        data = resp.json()["data"]
        if len(data) >= 2:
            accuracies = [t["accuracy_percent"] for t in data]
            assert accuracies == sorted(accuracies)

    def test_weak_topics_scoped_to_institution(self, admin_b_client, practice_event):
        resp = admin_b_client.get("/api/analytics/admin/weak-topics/")
        assert resp.json()["data"] == []


# ─── Admin Resource Usage ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAdminResourceUsage:
    def test_resource_usage_requires_auth(self, anon_client):
        resp = anon_client.get("/api/analytics/admin/resource-usage/")
        assert resp.status_code == 401

    def test_resource_usage_student_forbidden(self, student_client):
        resp = student_client.get("/api/analytics/admin/resource-usage/")
        assert resp.status_code == 403

    def test_resource_usage_returns_top_companies_and_resources(self, admin_client, resource_event):
        resp = admin_client.get("/api/analytics/admin/resource-usage/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "top_companies" in data
        assert "top_resources" in data
        assert len(data["top_companies"]) >= 1
        assert len(data["top_resources"]) >= 1

    def test_resource_usage_scoped_to_institution(self, admin_b_client, resource_event):
        resp = admin_b_client.get("/api/analytics/admin/resource-usage/")
        data = resp.json()["data"]
        assert data["top_companies"] == []
        assert data["top_resources"] == []


# ─── Super Admin ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSuperAdminOverview:
    def test_overview_requires_super_admin(self, anon_client):
        resp = anon_client.get("/api/analytics/super-admin/overview/")
        assert resp.status_code == 401

    def test_admin_cannot_access_super_admin_overview(self, admin_client):
        resp = admin_client.get("/api/analytics/super-admin/overview/")
        assert resp.status_code == 403

    def test_student_cannot_access_super_admin_overview(self, student_client):
        resp = student_client.get("/api/analytics/super-admin/overview/")
        assert resp.status_code == 403

    def test_super_admin_overview_no_data_returns_zeros(self, super_admin_client):
        resp = super_admin_client.get("/api/analytics/super-admin/overview/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_institutions"] == 0
        assert data["total_students"] == 0

    def test_super_admin_overview_aggregates_institutions(self, super_admin_client, institution_snapshot):
        resp = super_admin_client.get("/api/analytics/super-admin/overview/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_institutions"] == 1
        assert data["total_students"] == 100

    def test_super_admin_overview_cached(self, super_admin_client, institution_snapshot):
        from django.core.cache import cache
        super_admin_client.get("/api/analytics/super-admin/overview/")
        cache.set("analytics:superadmin:overview", {"override": True}, 1800)
        resp = super_admin_client.get("/api/analytics/super-admin/overview/")
        assert resp.json()["data"]["override"] is True


@pytest.mark.django_db
class TestSuperAdminDepartments:
    def test_departments_requires_super_admin(self, admin_client):
        resp = admin_client.get("/api/analytics/super-admin/departments/")
        assert resp.status_code == 403

    def test_departments_empty_when_no_snapshots(self, super_admin_client):
        resp = super_admin_client.get("/api/analytics/super-admin/departments/")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_departments_returns_breakdown(self, db, super_admin_client):
        from django.utils import timezone
        DailyEngagementSnapshot.objects.create(
            student_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            department="Engineering", practice_attempts=10, correct_attempts=7,
            resource_views=5, snapshot_date=timezone.now().date(),
        )
        resp = super_admin_client.get("/api/analytics/super-admin/departments/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        dept = data[0]
        assert "institution_id" in dept
        assert "department" in dept
        assert "student_count" in dept


# ─── Nightly Aggregation Task ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestNightlyAggregation:
    def test_aggregation_creates_engagement_snapshot(self, db):
        from django.utils import timezone
        from datetime import timedelta
        from analytics.tasks import run_nightly_aggregation

        yesterday = timezone.now().date() - timedelta(days=1)
        # Backdate an event to yesterday
        e = PracticeEvent.objects.create(
            student_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            module_id=MODULE_ID, question_id=QUESTION_ID,
            topic="Algebra", difficulty="easy", is_correct=True,
        )
        import datetime as _dt
        PracticeEvent.objects.filter(pk=e.pk).update(
            created_at=_dt.datetime.combine(yesterday, _dt.time.min, tzinfo=_dt.timezone.utc)
        )

        result = run_nightly_aggregation()
        assert result["engagement_snapshots"] >= 1
        assert DailyEngagementSnapshot.objects.filter(
            student_id=STUDENT_USER_ID, snapshot_date=yesterday
        ).exists()

    def test_aggregation_creates_institution_snapshot(self, db):
        from django.utils import timezone
        from datetime import timedelta
        from analytics.tasks import run_nightly_aggregation

        yesterday = timezone.now().date() - timedelta(days=1)
        e = PracticeEvent.objects.create(
            student_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            module_id=MODULE_ID, question_id=QUESTION_ID,
            topic="Algebra", difficulty="easy", is_correct=True,
        )
        import datetime as _dt
        PracticeEvent.objects.filter(pk=e.pk).update(
            created_at=_dt.datetime.combine(yesterday, _dt.time.min, tzinfo=_dt.timezone.utc)
        )

        result = run_nightly_aggregation()
        assert result["institution_snapshots"] >= 1
        assert InstitutionSnapshot.objects.filter(
            institution_id=INSTITUTION_A, snapshot_date=yesterday
        ).exists()

    def test_aggregation_no_events_returns_zero_counts(self, db):
        from analytics.tasks import run_nightly_aggregation
        result = run_nightly_aggregation()
        assert result["engagement_snapshots"] == 0
        assert result["institution_snapshots"] == 0

    def test_aggregation_is_idempotent(self, db):
        from django.utils import timezone
        from datetime import timedelta
        from analytics.tasks import run_nightly_aggregation

        yesterday = timezone.now().date() - timedelta(days=1)
        e = PracticeEvent.objects.create(
            student_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            module_id=MODULE_ID, question_id=QUESTION_ID,
            topic="Algebra", difficulty="easy", is_correct=True,
        )
        import datetime as _dt
        PracticeEvent.objects.filter(pk=e.pk).update(
            created_at=_dt.datetime.combine(yesterday, _dt.time.min, tzinfo=_dt.timezone.utc)
        )

        run_nightly_aggregation()
        run_nightly_aggregation()  # Second run must not create duplicates
        assert DailyEngagementSnapshot.objects.filter(
            student_id=STUDENT_USER_ID, snapshot_date=yesterday
        ).count() == 1
