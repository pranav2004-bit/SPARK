from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse


def health_check(request):
    return JsonResponse({"status": "ok", "service": "aptlogic-backend"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_check, name="health_check"),
    path("api/auth/", include("apps.authentication.urls")),
    path("api/admin/", include("apps.authentication.admin_urls")),
    path("api/admin/batches/", include("apps.batches.urls")),
    path("api/admin/students/", include("apps.students.admin_urls")),
    path("api/students/", include("apps.students.urls")),
    path("api/admin/companies/", include("apps.companies.admin_urls")),
    path("api/students/companies/", include("apps.companies.student_urls")),
    path("api/admin/practice/", include("apps.practice.admin_urls")),
    path("api/students/practice/", include("apps.practice.student_urls")),
]
