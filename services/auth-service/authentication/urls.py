from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    HealthView,
    LoginView,
    LogoutView,
    StudentPasswordResetView,
    AdminPasswordResetView,
    StudentProfileCompletedView,
    StudentChangePasswordView,
    AdminSelfProfileView,
    AdminChangePasswordView,
    AdminListCreateView,
    AdminDetailView,
    AdminResetDefaultPasswordView,
    AdminPasswordResetByIdView,
    InternalStudentCreateView,
    InternalStudentUpdateView,
    InternalStudentDeleteView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="auth-health"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("profile/complete/", StudentProfileCompletedView.as_view(), name="profile-complete"),

    # Admin self-service
    path("me/", AdminSelfProfileView.as_view(), name="admin-self-profile"),
    path("me/change-password/", AdminChangePasswordView.as_view(), name="admin-change-password"),

    # Password resets
    path("student/<str:student_id>/reset-password/", StudentPasswordResetView.as_view(), name="student-reset-password"),
    path("admin/<uuid:pk>/reset-password/", AdminPasswordResetView.as_view(), name="admin-reset-password"),
    path("student/change-password/", StudentChangePasswordView.as_view(), name="student-change-password"),

    # Admin management — Super Admin only
    path("admins/", AdminListCreateView.as_view(), name="admin-list-create"),
    path("admins/<uuid:pk>/", AdminDetailView.as_view(), name="admin-detail"),
    path("admins/<uuid:pk>/reset-default-password/", AdminResetDefaultPasswordView.as_view(), name="admin-reset-default-password"),
    path("admin-password-reset/", AdminPasswordResetByIdView.as_view(), name="admin-password-reset-by-id"),

    # Internal service-to-service endpoints (user-service → auth-service).
    # Only reachable via Docker internal network (http://auth-service:8000).
    # Protected by X-Service-Key header — never exposed through nginx to external clients.
    path("internal/students/", InternalStudentCreateView.as_view(), name="internal-student-create"),
    path("internal/students/<str:student_id>/", InternalStudentUpdateView.as_view(), name="internal-student-update"),
    path("internal/students/<str:student_id>/delete/", InternalStudentDeleteView.as_view(), name="internal-student-delete"),
]
