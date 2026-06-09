from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """Grants access only to users with role == 'admin' in the JWT payload."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "admin"
        )


class IsStudentUser(BasePermission):
    """Grants access only to users with role == 'student' in the JWT payload."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "student"
        )


class IsAdminOrReadOnly(BasePermission):
    """Admins get full access; authenticated users get read-only."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return getattr(request.user, "role", None) == "admin"
