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


class IsITUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "it"
        )


class IsSuperAdminOrIT(BasePermission):
    """Read-only scope for Admin-account management (revised 2026-08-19):
    Super Admin and IT can both list/view admin accounts, but all
    create/update/delete/reset-password operations are IT-exclusive —
    enforced by using this class only on GET/read endpoints and IsITUser on
    the write endpoints. Super Admin briefly had equal write access here
    (2026-08-19 phase 1, added so IT could reach full parity); that was
    reversed the same day (phase 2) in favor of IT owning all
    account-management responsibility while Super Admin stays
    read/query-only — same treatment as Batches."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in ("super_admin", "it")
        )


class IsAdminOrSuperAdminOrIT(BasePermission):
    """Read-only scope for Department management (2026-08-20): Admin, Super
    Admin, and IT can all list/view departments — they all consume this list
    as dropdown/filter options — but create/update/delete are IT-exclusive,
    same split as Batches in user-service (this class mirrors that service's
    permission class of the same name)."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in ("admin", "super_admin", "it")
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
