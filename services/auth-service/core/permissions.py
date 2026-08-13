from django.conf import settings
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


class IsInternalService(BasePermission):
    """
    Allows access only when the request carries the correct X-Service-Key header.
    Used exclusively for service-to-service calls within the Docker network.
    External clients never know this key and nginx never routes /internal/ paths
    from outside (calls go directly to auth-service:8000 on the internal network).
    """
    def has_permission(self, request, view):
        key = request.headers.get("X-Service-Key", "")
        expected = getattr(settings, "SERVICE_KEY", "")
        return bool(expected) and key == expected
