from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "admin"
        )


class IsStudentUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "student"
        )


class IsSuperAdminUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "super_admin"
        )


class IsAdminOrSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in ("admin", "super_admin")
        )


class IsITUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "it"
        )


class IsAdminOrSuperAdminOrIT(BasePermission):
    """Read-only scope for Batches (revised 2026-08-19): Admin and Super Admin
    can list/view batches — including a batch's own student roster
    (AdminBatchStudentsView) — but all CRUD/management operations (create,
    update, delete) are exclusive to IT — enforced by using this class only
    on GET/read endpoints and IsITUser on the write endpoints. Admin briefly
    had equal write access (2026-08-19 "shared access" phase); that was
    reversed the same day in favor of IT owning all account-management
    responsibility while Admin/Super Admin stay read/query-only on Batches.
    The standalone Students module (AdminStudentListCreateView/Detail) is not
    scoped by this class at all — it was removed entirely from both Admin
    and Super Admin the same day, and is IsITUser-only end to end."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in ("admin", "super_admin", "it")
        )
