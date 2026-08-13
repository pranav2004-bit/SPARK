from django.conf import settings
from rest_framework.permissions import BasePermission


class IsServiceKey(BasePermission):
    """Validates X-Service-Key header for internal service-to-service calls."""

    def has_permission(self, request, view):
        key = request.META.get("HTTP_X_SERVICE_KEY", "")
        service_key = getattr(settings, "SERVICE_KEY", "")
        return bool(key and service_key and key == service_key)


class IsStudentUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "student"
        )


class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "admin"
        )


class IsSuperAdminUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "super_admin"
        )
