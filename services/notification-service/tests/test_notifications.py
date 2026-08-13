import uuid
import pytest
from notifications.models import Notification
from tests.conftest import (
    STUDENT_USER_ID,
    STUDENT_B_USER_ID,
    INSTITUTION_A,
    INSTITUTION_B,
    TEST_SERVICE_KEY,
)


# ─── List ────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestNotificationList:
    def test_list_requires_auth(self, anon_client):
        resp = anon_client.get("/api/notifications/")
        assert resp.status_code == 401

    def test_list_returns_own_notifications(self, student_client, notification):
        resp = student_client.get("/api/notifications/")
        assert resp.status_code == 200
        ids = [n["id"] for n in resp.json()["results"]]
        assert str(notification.id) in ids

    def test_list_excludes_deleted(self, db, student_client):
        Notification.objects.create(
            user_id=STUDENT_USER_ID,
            institution_id=INSTITUTION_A,
            type="announcement",
            title="Deleted",
            body="Should not appear",
            is_deleted=True,
        )
        resp = student_client.get("/api/notifications/")
        assert resp.status_code == 200
        for n in resp.json()["results"]:
            assert n["title"] != "Deleted"

    def test_list_excludes_other_user_notifications(self, db, student_client):
        Notification.objects.create(
            user_id=STUDENT_B_USER_ID,
            institution_id=INSTITUTION_A,
            type="announcement",
            title="Other user",
            body="Not mine",
        )
        resp = student_client.get("/api/notifications/")
        for n in resp.json()["results"]:
            assert n["title"] != "Other user"

    def test_list_cursor_pagination_format(self, student_client, notification):
        resp = student_client.get("/api/notifications/")
        data = resp.json()
        assert "results" in data
        assert "next" in data
        assert "previous" in data

    def test_list_ordered_newest_first(self, db, student_client):
        from django.utils import timezone
        from datetime import timedelta

        n1 = Notification.objects.create(
            user_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            type="announcement", title="First", body="b",
        )
        n2 = Notification.objects.create(
            user_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            type="announcement", title="Second", body="b",
        )
        # Ensure n1 is older by backdating it (bypasses auto_now_add via queryset update)
        Notification.objects.filter(pk=n1.pk).update(
            created_at=timezone.now() - timedelta(seconds=10)
        )
        resp = student_client.get("/api/notifications/")
        ids = [n["id"] for n in resp.json()["results"]]
        assert ids.index(str(n2.id)) < ids.index(str(n1.id))


# ─── Unread Count ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestUnreadCount:
    def test_unread_count_requires_auth(self, anon_client):
        resp = anon_client.get("/api/notifications/unread-count/")
        assert resp.status_code == 401

    def test_unread_count_returns_correct_number(self, db, student_client):
        Notification.objects.bulk_create([
            Notification(user_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
                         type="announcement", title=f"N{i}", body="b")
            for i in range(3)
        ])
        Notification.objects.create(
            user_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            type="announcement", title="Read", body="b", is_read=True,
        )
        resp = student_client.get("/api/notifications/unread-count/")
        assert resp.status_code == 200
        assert resp.json()["data"]["count"] == 3

    def test_unread_count_excludes_deleted(self, db, student_client):
        Notification.objects.create(
            user_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            type="announcement", title="Deleted unread", body="b",
            is_deleted=True,
        )
        resp = student_client.get("/api/notifications/unread-count/")
        assert resp.json()["data"]["count"] == 0

    def test_unread_count_served_from_cache(self, db, student_client):
        from django.core.cache import cache
        Notification.objects.create(
            user_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            type="announcement", title="Cached", body="b",
        )
        # First call populates cache
        resp1 = student_client.get("/api/notifications/unread-count/")
        assert resp1.json()["data"]["count"] == 1
        # Manually override cache value
        cache.set(f"notifications:unread:{STUDENT_USER_ID}", 999, 60)
        resp2 = student_client.get("/api/notifications/unread-count/")
        assert resp2.json()["data"]["count"] == 999

    def test_unread_count_invalidated_on_mark_read(self, student_client, notification):
        # Populate cache
        student_client.get("/api/notifications/unread-count/")
        # Mark as read
        student_client.patch(f"/api/notifications/{notification.id}/read/")
        resp = student_client.get("/api/notifications/unread-count/")
        assert resp.json()["data"]["count"] == 0


# ─── Mark Read ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestMarkRead:
    def test_mark_read_requires_auth(self, anon_client, notification):
        resp = anon_client.patch(f"/api/notifications/{notification.id}/read/")
        assert resp.status_code == 401

    def test_mark_read_sets_is_read_true(self, student_client, notification):
        assert not notification.is_read
        resp = student_client.patch(f"/api/notifications/{notification.id}/read/")
        assert resp.status_code == 200
        notification.refresh_from_db()
        assert notification.is_read

    def test_mark_read_other_user_notification_not_found(self, student_b_client, notification):
        # Since user_id is included in the DB query, a cross-user request returns
        # 404 (not 403) — this prevents IDOR existence oracle attacks.
        resp = student_b_client.patch(f"/api/notifications/{notification.id}/read/")
        assert resp.status_code == 404

    def test_mark_read_nonexistent_returns_404(self, student_client):
        fake_id = uuid.uuid4()
        resp = student_client.patch(f"/api/notifications/{fake_id}/read/")
        assert resp.status_code == 404

    def test_mark_read_deleted_notification_returns_404(self, db, student_client):
        n = Notification.objects.create(
            user_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            type="announcement", title="Deleted", body="b", is_deleted=True,
        )
        resp = student_client.patch(f"/api/notifications/{n.id}/read/")
        assert resp.status_code == 404

    def test_mark_read_already_read_is_idempotent(self, student_client, read_notification):
        resp = student_client.patch(f"/api/notifications/{read_notification.id}/read/")
        assert resp.status_code == 200
        read_notification.refresh_from_db()
        assert read_notification.is_read

    def test_mark_read_response_contains_notification_fields(self, student_client, notification):
        resp = student_client.patch(f"/api/notifications/{notification.id}/read/")
        data = resp.json()["data"]
        assert "id" in data
        assert "title" in data
        assert data["is_read"] is True


# ─── Read All ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestReadAll:
    def test_read_all_requires_auth(self, anon_client):
        resp = anon_client.post("/api/notifications/read-all/")
        assert resp.status_code == 401

    def test_read_all_marks_all_unread_as_read(self, db, student_client):
        Notification.objects.bulk_create([
            Notification(user_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
                         type="announcement", title=f"N{i}", body="b")
            for i in range(5)
        ])
        resp = student_client.post("/api/notifications/read-all/")
        assert resp.status_code == 200
        unread_count = Notification.objects.filter(
            user_id=STUDENT_USER_ID, is_read=False, is_deleted=False
        ).count()
        assert unread_count == 0

    def test_read_all_does_not_affect_other_users(self, db, student_client):
        other = Notification.objects.create(
            user_id=STUDENT_B_USER_ID, institution_id=INSTITUTION_A,
            type="announcement", title="Other", body="b",
        )
        student_client.post("/api/notifications/read-all/")
        other.refresh_from_db()
        assert not other.is_read

    def test_read_all_invalidates_unread_cache(self, db, student_client):
        from django.core.cache import cache
        Notification.objects.create(
            user_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            type="announcement", title="N", body="b",
        )
        student_client.get("/api/notifications/unread-count/")
        student_client.post("/api/notifications/read-all/")
        key = f"notifications:unread:{STUDENT_USER_ID}"
        assert cache.get(key) is None

    def test_read_all_with_no_notifications_is_ok(self, student_client):
        resp = student_client.post("/api/notifications/read-all/")
        assert resp.status_code == 200


# ─── Internal Send ────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestInternalSend:
    def _payload(self, user_ids=None):
        return {
            "user_ids": [str(uid) for uid in (user_ids or [STUDENT_USER_ID])],
            "institution_id": str(INSTITUTION_A),
            "type": "resource_upload",
            "title": "New Resource",
            "body": "A new resource has been uploaded.",
        }

    def test_internal_send_requires_service_key(self, anon_client):
        resp = anon_client.post(
            "/api/notifications/internal/send/", self._payload(), format="json"
        )
        assert resp.status_code == 403

    def test_internal_send_jwt_not_accepted(self, student_client):
        resp = student_client.post(
            "/api/notifications/internal/send/", self._payload(), format="json"
        )
        assert resp.status_code == 403

    def test_internal_send_creates_notifications(self, db, service_client):
        resp = service_client.post(
            "/api/notifications/internal/send/", self._payload(), format="json"
        )
        assert resp.status_code == 201
        assert Notification.objects.filter(user_id=STUDENT_USER_ID).count() == 1

    def test_internal_send_bulk_creates_for_multiple_users(self, db, service_client):
        user_ids = [uuid.uuid4() for _ in range(500)]
        payload = {
            "user_ids": [str(uid) for uid in user_ids],
            "institution_id": str(INSTITUTION_A),
            "type": "announcement",
            "title": "Announcement",
            "body": "For everyone.",
        }
        resp = service_client.post(
            "/api/notifications/internal/send/", payload, format="json"
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["sent"] == 500
        assert Notification.objects.count() == 500

    def test_internal_send_empty_user_ids_returns_400(self, db, service_client):
        payload = {
            "user_ids": [],
            "institution_id": str(INSTITUTION_A),
            "type": "announcement",
            "title": "Test",
            "body": "Body",
        }
        resp = service_client.post(
            "/api/notifications/internal/send/", payload, format="json"
        )
        assert resp.status_code == 400

    def test_internal_send_missing_fields_returns_400(self, db, service_client):
        resp = service_client.post(
            "/api/notifications/internal/send/",
            {"user_ids": [str(STUDENT_USER_ID)]},
            format="json",
        )
        assert resp.status_code == 400

    def test_internal_send_invalid_type_returns_400(self, db, service_client):
        payload = self._payload()
        payload["type"] = "invalid_type"
        resp = service_client.post(
            "/api/notifications/internal/send/", payload, format="json"
        )
        assert resp.status_code == 400

    def test_internal_send_invalidates_unread_cache(self, db, service_client, student_client):
        from django.core.cache import cache
        # Pre-populate cache with 0
        cache.set(f"notifications:unread:{STUDENT_USER_ID}", 0, 60)
        service_client.post(
            "/api/notifications/internal/send/", self._payload(), format="json"
        )
        # Cache should be cleared
        assert cache.get(f"notifications:unread:{STUDENT_USER_ID}") is None

    def test_internal_send_notification_fields_correct(self, db, service_client):
        service_client.post(
            "/api/notifications/internal/send/", self._payload(), format="json"
        )
        n = Notification.objects.get(user_id=STUDENT_USER_ID)
        assert n.type == "resource_upload"
        assert n.title == "New Resource"
        assert n.institution_id == INSTITUTION_A
        assert not n.is_read
        assert not n.is_deleted


# ─── Auto-Expiry Task ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestExpireOldNotifications:
    def test_expire_marks_old_notifications_deleted(self, db):
        from django.utils import timezone
        from datetime import timedelta
        from notifications.tasks import expire_old_notifications

        old = Notification.objects.create(
            user_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            type="announcement", title="Old", body="b",
        )
        # Manually backdate
        Notification.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=91)
        )

        result = expire_old_notifications()
        assert result["expired"] == 1
        old.refresh_from_db()
        assert old.is_deleted

    def test_expire_does_not_touch_recent_notifications(self, notification):
        from notifications.tasks import expire_old_notifications

        result = expire_old_notifications()
        assert result["expired"] == 0
        notification.refresh_from_db()
        assert not notification.is_deleted

    def test_expire_does_not_touch_already_deleted(self, db):
        from django.utils import timezone
        from datetime import timedelta
        from notifications.tasks import expire_old_notifications

        n = Notification.objects.create(
            user_id=STUDENT_USER_ID, institution_id=INSTITUTION_A,
            type="announcement", title="Old deleted", body="b",
            is_deleted=True,
        )
        Notification.objects.filter(pk=n.pk).update(
            created_at=timezone.now() - timedelta(days=91)
        )
        result = expire_old_notifications()
        assert result["expired"] == 0

    def test_expire_returns_count(self, db):
        from django.utils import timezone
        from datetime import timedelta
        from notifications.tasks import expire_old_notifications

        old_notifications = [
            Notification(user_id=uuid.uuid4(), institution_id=INSTITUTION_A,
                         type="announcement", title=f"Old {i}", body="b")
            for i in range(5)
        ]
        Notification.objects.bulk_create(old_notifications)
        Notification.objects.filter(title__startswith="Old ").update(
            created_at=timezone.now() - timedelta(days=91)
        )
        result = expire_old_notifications()
        assert result["expired"] == 5
