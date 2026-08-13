from django.urls import path
from .views import (
    HealthView,
    NotificationListView,
    UnreadCountView,
    MarkReadView,
    ReadAllView,
    InternalSendView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("", NotificationListView.as_view(), name="notification-list"),
    path("unread-count/", UnreadCountView.as_view(), name="unread-count"),
    path("<uuid:pk>/read/", MarkReadView.as_view(), name="mark-read"),
    path("read-all/", ReadAllView.as_view(), name="read-all"),
    path("internal/send/", InternalSendView.as_view(), name="internal-send"),
]
