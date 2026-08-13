from django.core.cache import cache
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework import status

from core.pagination import NotificationCursorPagination
from core.permissions import IsAnyAuthenticatedUser, IsServiceKey
from core.responses import success_response, error_response
from .models import Notification
from .serializers import NotificationSerializer, InternalSendSerializer

_UNREAD_CACHE_TTL = 60  # seconds


def _unread_cache_key(user_id):
    return f"notifications:unread:{user_id}"


def _invalidate_unread_cache(user_id):
    cache.delete(_unread_cache_key(user_id))


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = []  # never throttle — polled at high frequency by health checks

    def get(self, request):
        from django.db import connection
        try:
            connection.ensure_connection()
            db_status = "ok"
        except Exception:
            db_status = "error"
        return success_response(data={"service": "notification-service", "status": "ok", "db": db_status})


class NotificationListView(APIView):
    permission_classes = [IsAnyAuthenticatedUser]

    def get(self, request):
        user_id = request.user.id
        qs = Notification.objects.filter(user_id=user_id, is_deleted=False)
        paginator = NotificationCursorPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = NotificationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class UnreadCountView(APIView):
    permission_classes = [IsAnyAuthenticatedUser]

    def get(self, request):
        user_id = request.user.id
        key = _unread_cache_key(user_id)
        count = cache.get(key)
        if count is None:
            count = Notification.objects.filter(
                user_id=user_id, is_read=False, is_deleted=False
            ).count()
            cache.set(key, count, _UNREAD_CACHE_TTL)
        return success_response(data={"count": count})


class MarkReadView(APIView):
    permission_classes = [IsAnyAuthenticatedUser]

    def patch(self, request, pk):
        user_id = request.user.id
        # Include user_id in the query — prevents existence oracle (IDOR):
        # an attacker probing another user's notification ID gets 404, not 403.
        notification = get_object_or_404(Notification, pk=pk, user_id=user_id, is_deleted=False)

        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
            _invalidate_unread_cache(user_id)

        return success_response(data=NotificationSerializer(notification).data)


class ReadAllView(APIView):
    permission_classes = [IsAnyAuthenticatedUser]

    def post(self, request):
        user_id = request.user.id
        Notification.objects.filter(
            user_id=user_id, is_read=False, is_deleted=False
        ).update(is_read=True)
        _invalidate_unread_cache(user_id)
        return success_response(message="All notifications marked as read.")


class InternalSendView(APIView):
    authentication_classes = []
    permission_classes = [IsServiceKey]
    # Legitimate high-frequency internal traffic (bypasses nginx entirely —
    # called directly on the Docker network) must not share the anon/user
    # DRF throttle buckets meant for external-facing endpoints.
    throttle_classes = []

    def post(self, request):
        serializer = InternalSendSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                "Invalid payload.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data
        user_ids = data["user_ids"]
        institution_id = data["institution_id"]
        notif_type = data["type"]
        title = data["title"]
        body = data["body"]

        notifications = [
            Notification(
                user_id=uid,
                institution_id=institution_id,
                type=notif_type,
                title=title,
                body=body,
            )
            for uid in user_ids
        ]
        Notification.objects.bulk_create(notifications)

        # Invalidate unread cache for all recipients
        cache.delete_many([_unread_cache_key(uid) for uid in user_ids])

        return success_response(
            data={"sent": len(notifications)},
            status_code=status.HTTP_201_CREATED,
        )
