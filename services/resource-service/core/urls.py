from django.urls import path, include

urlpatterns = [
    path("api/resources/", include("resources.urls")),
]
