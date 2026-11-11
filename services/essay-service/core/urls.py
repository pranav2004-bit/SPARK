from django.urls import path, include

urlpatterns = [
    path("api/essay/", include("essays.urls")),
]
