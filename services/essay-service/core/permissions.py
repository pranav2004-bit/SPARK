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
    """Admin and super_admin share the entire admin surface in essay-service
    (Question Bank, Assign, Results, Analytics, Dashboard, Submissions, LLM
    Controls, Reports, DLQ, Notifications) — there is no per-paper ownership
    restriction here the way assessment-service's IsAdminOrSuperAdmin exists
    to support (that class's own docstring documents a faculty-privacy
    restriction this service does not have a stated requirement for). Kept
    as its own class rather than inlined everywhere it's used, so a future
    ownership rule (if one is ever added) has one place to change."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in ("admin", "super_admin")
        )
