from django.urls import path, include

urlpatterns = [
    path("api/practice/content/", include("content.urls")),
    path("api/practice/", include("practice.urls")),
]
