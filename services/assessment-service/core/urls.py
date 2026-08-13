from django.urls import path, include

urlpatterns = [
    path("api/assessments/", include("assessments.urls")),
]
