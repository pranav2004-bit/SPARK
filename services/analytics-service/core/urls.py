from django.urls import path, include

urlpatterns = [
    path("api/analytics/", include("analytics.urls")),
]
