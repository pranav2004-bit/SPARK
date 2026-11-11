from django.urls import path, include

urlpatterns = [
    path("api/practice/", include("practice.urls")),
]
