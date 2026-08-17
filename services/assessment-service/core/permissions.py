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
    """Used on the question-paper authoring surface (papers/sets/questions/
    options/assign) so a super admin's _require_paper_owner override
    (views.py) can actually take effect — plain IsAdminUser would 403 a
    super_admin before the view method (and its ownership override) ever
    runs. Results/Analytics/Dashboard deliberately keep plain IsAdminUser —
    they're institution-wide for every admin already and were never part of
    the ownership restriction this permission class exists to support."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in ("admin", "super_admin")
        )
