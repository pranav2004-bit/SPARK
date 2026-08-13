from django.urls import path, include

urlpatterns = [
    path("api/notifications/", include("notifications.urls")),
]
