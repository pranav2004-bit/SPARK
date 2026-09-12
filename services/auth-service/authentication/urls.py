from django.urls import path

from .views import (
    HealthView,
    LoginView,
    LogoutView,
    TokenRefreshView,
    StudentPasswordResetView,
    AdminPasswordResetView,
    StudentProfileCompletedView,
    StudentChangePasswordView,
    AdminSelfProfileView,
    AdminChangePasswordView,
    AdminUserLookupView,
    AdminListCreateView,
    AdminDetailView,
    AdminResetDefaultPasswordView,
    AdminBulkCreateView,
    AdminPasswordResetByIdView,
    SuperAdminListCreateView,
    SuperAdminDetailView,
    SuperAdminResetDefaultPasswordView,
    SuperAdminBulkCreateView,
    DepartmentListCreateView,
    DepartmentDetailView,
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
    path("admin/users/lookup/", AdminUserLookupView.as_view(), name="admin-user-lookup"),

    # Password resets
    path("student/<str:student_id>/reset-password/", StudentPasswordResetView.as_view(), name="student-reset-password"),
    path("admin/<uuid:pk>/reset-password/", AdminPasswordResetView.as_view(), name="admin-reset-password"),
    path("student/change-password/", StudentChangePasswordView.as_view(), name="student-change-password"),

    # Admin management — read: Super Admin + IT; write: IT only
    path("admins/import/", AdminBulkCreateView.as_view(), name="admin-bulk-create"),
    path("admins/", AdminListCreateView.as_view(), name="admin-list-create"),
    path("admins/<uuid:pk>/", AdminDetailView.as_view(), name="admin-detail"),
    path("admins/<uuid:pk>/reset-default-password/", AdminResetDefaultPasswordView.as_view(), name="admin-reset-default-password"),
    path("admin-password-reset/", AdminPasswordResetByIdView.as_view(), name="admin-password-reset-by-id"),

    # Super admin account management — IT only (2026-08-20; same mechanism as
    # Admin management above, but no read access for the managed role at all)
    path("super-admins/import/", SuperAdminBulkCreateView.as_view(), name="super-admin-bulk-create"),
    path("super-admins/", SuperAdminListCreateView.as_view(), name="super-admin-list-create"),
    path("super-admins/<uuid:pk>/", SuperAdminDetailView.as_view(), name="super-admin-detail"),
    path("super-admins/<uuid:pk>/reset-default-password/", SuperAdminResetDefaultPasswordView.as_view(), name="super-admin-reset-default-password"),

    # Department management — read: Admin + Super Admin + IT; write: IT only
    path("departments/", DepartmentListCreateView.as_view(), name="department-list-create"),
    path("departments/<uuid:pk>/", DepartmentDetailView.as_view(), name="department-detail"),

    # Internal service-to-service endpoints (user-service → auth-service).
    # Only reachable via Docker internal network (http://auth-service:8000).
    # Protected by X-Service-Key header — never exposed through nginx to external clients.
    path("internal/students/", InternalStudentCreateView.as_view(), name="internal-student-create"),
    path("internal/students/<str:student_id>/", InternalStudentUpdateView.as_view(), name="internal-student-update"),
    path("internal/students/<str:student_id>/delete/", InternalStudentDeleteView.as_view(), name="internal-student-delete"),
]
