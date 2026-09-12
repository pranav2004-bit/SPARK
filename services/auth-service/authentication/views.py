import logging
import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import connection
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated, SAFE_METHODS
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView
from django.core.cache import cache

from core.responses import success_response, error_response
from core.permissions import IsAdminUser, IsStudentUser, IsSuperAdminUser, IsInternalService, IsAdminOrSuperAdmin, IsITUser, IsSuperAdminOrIT, IsAdminOrSuperAdminOrIT
from .models import Department
from .serializers import (
    LoginSerializer, LogoutSerializer,
    StudentPasswordResetSerializer, AdminPasswordResetSerializer,
    AdminSerializer, AdminCreateSerializer,
    AdminUpdateExtendedSerializer,
    AdminPasswordResetByIdSerializer,
    AdminSelfUpdateSerializer, AdminChangePasswordSerializer,
    StudentChangePasswordSerializer,
    DepartmentSerializer, DepartmentCreateSerializer, DepartmentUpdateSerializer,
)
from .tokens import get_tokens_for_user
from .throttling import LoginAttemptThrottle, TokenRefreshThrottle

User = get_user_model()
logger = logging.getLogger(__name__)

INVALID_CREDENTIALS_MSG = "Invalid credentials"


def _get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


# ── Health ─────────────────────────────────────────────────────────────────────

class HealthView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = []  # never throttle — polled at high frequency by health checks

    def get(self, request):
        import os
        db_ok = "ok"
        redis_ok = "ok"
        institution_ok = "ok" if os.environ.get("INSTITUTION_ID", "").strip() else "missing"
        try:
            connection.ensure_connection()
        except Exception:
            db_ok = "error"
        try:
            cache.set("health_check", "1", timeout=5)
            cache.get("health_check")
        except Exception:
            redis_ok = "error"
        overall = "ok" if all(v == "ok" for v in [db_ok, redis_ok, institution_ok]) else "degraded"
        return success_response(
            data={
                "status": overall,
                "service": "auth-service",
                "db": db_ok,
                "redis": redis_ok,
                "institution_id": institution_ok,
            }
        )


# ── Token refresh ────────────────────────────────────────────────────────────
# Thin subclass (2026-09-12) — the only change from rest_framework_simplejwt's
# own TokenRefreshView is throttle_classes. Left as a subclass rather than
# editing settings.py's DEFAULT_THROTTLE_CLASSES globally so this scoped rate
# applies only to this endpoint, not every anonymous view in the service. See
# TokenRefreshThrottle's docstring (authentication/throttling.py) for why the
# global "anon" 60/min default isn't safe to leave this endpoint on.
class TokenRefreshView(SimpleJWTTokenRefreshView):
    throttle_classes = [TokenRefreshThrottle]


# ── Unified Login ──────────────────────────────────────────────────────────────

class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginAttemptThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", errors=serializer.errors, status_code=400)

        role = serializer.validated_data["role"]
        password = serializer.validated_data["password"]

        if role == "student":
            student_id = serializer.validated_data.get("student_id")
            try:
                user = User.objects.get(student_id=student_id, role="student")
            except User.DoesNotExist:
                logger.warning("Student login failed — unknown student_id: %s", student_id)
                return error_response(INVALID_CREDENTIALS_MSG, status_code=401)
            except User.MultipleObjectsReturned:
                logger.critical("Data integrity error: multiple auth records for student_id=%s", student_id)
                return error_response(INVALID_CREDENTIALS_MSG, status_code=401)
        else:
            email = serializer.validated_data.get("email")
            try:
                user = User.objects.get(email=email, role=role)
            except User.DoesNotExist:
                logger.warning("Login failed — unknown email: %s role: %s", email, role)
                return error_response(INVALID_CREDENTIALS_MSG, status_code=401)
            except User.MultipleObjectsReturned:
                logger.critical("Data integrity error: multiple auth records for email=%s role=%s", email, role)
                return error_response(INVALID_CREDENTIALS_MSG, status_code=401)

        if not user.check_password(password):
            logger.warning("Login failed — wrong password for user: %s", user.email)
            return error_response(INVALID_CREDENTIALS_MSG, status_code=401)

        if not user.is_active:
            return error_response("Account is disabled. Contact administrator.", status_code=403)

        tokens = get_tokens_for_user(user)
        user_data = {"role": user.role, "email": user.email}
        if role == "student":
            user_data["student_id"] = user.student_id
            user_data["fullname"] = user.name or ""
            user_data["is_profile_completed"] = user.is_profile_completed
        if role in ("admin", "super_admin", "it"):
            user_data["id"] = str(user.id)
            user_data["name"] = user.name
        if user.institution_id:
            user_data["institution_id"] = str(user.institution_id)
        user_data["force_password_change"] = user.force_password_change

        logger.info("Login successful: role=%s user=%s", role, user.email)
        return success_response(data={**tokens, "user": user_data}, message="Login successful")


# ── Logout ─────────────────────────────────────────────────────────────────────

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("refresh_token is required", status_code=400)
        try:
            token = RefreshToken(serializer.validated_data["refresh_token"])
            token.blacklist()
        except TokenError:
            return error_response("Invalid or already blacklisted token", status_code=400)
        return success_response(message="Logged out successfully")


# ── Password Reset ─────────────────────────────────────────────────────────────

class StudentPasswordResetView(APIView):
    """IT resets a student's password to default (no email required).

    Exclusive to IT (2026-08-19) — student account management, like all
    Batches/Students CRUD, is IT's responsibility; Admin is read/query-only.
    """
    permission_classes = [IsITUser]

    def post(self, request, student_id):
        try:
            user = User.objects.get(student_id=student_id, role="student")
        except User.DoesNotExist:
            return error_response("Student not found", status_code=404)
        except User.MultipleObjectsReturned:
            logger.critical("Data integrity error: multiple auth records for student_id=%s", student_id)
            return error_response("System error", status_code=500)

        # IDOR check: IT can only reset students within their own institution.
        # The leading `and` is intentionally removed — if the IT user has no institution_id
        # (misconfigured account), the check must still fire, not be skipped.
        if user.institution_id != request.user.institution_id:
            return error_response("Access denied", status_code=403)

        user.set_password(settings.STUDENT_DEFAULT_PASSWORD)
        user.force_password_change = True
        user.token_version += 1  # invalidate existing tokens immediately
        user.save(update_fields=["password", "force_password_change", "token_version"])
        logger.info(
            "Student %s password reset to default by it_user=%s from IP=%s",
            user.student_id, request.user.email, _get_client_ip(request),
        )
        return success_response(message="Password reset to default successfully")


class AdminPasswordResetView(APIView):
    """Super Admin resets an admin's password (legacy endpoint — kept for compat)."""
    permission_classes = [IsSuperAdminUser]

    def post(self, request, pk):
        serializer = AdminPasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", errors=serializer.errors, status_code=400)
        try:
            user = User.objects.get(pk=pk, role="admin")
        except User.DoesNotExist:
            return error_response("Admin not found", status_code=404)

        user.set_password(serializer.validated_data["new_password"])
        user.force_password_change = False
        user.token_version += 1
        user.save(update_fields=["password", "force_password_change", "token_version"])
        logger.info(
            "Admin %s password reset by super_admin=%s IP=%s",
            user.email, request.user.email, _get_client_ip(request),
        )
        return success_response(message="Admin password reset successfully")


class StudentProfileCompletedView(APIView):
    """
    Internal endpoint — user-service calls this after profile update
    to sync is_profile_completed back to auth-service.
    """
    permission_classes = [IsStudentUser]

    def patch(self, request):
        user = request.user
        if not isinstance(user, User):
            return error_response("Not allowed", status_code=403)
        fullname = request.data.get("fullname", "").strip()
        update_fields = ["is_profile_completed"]
        user.is_profile_completed = True
        if fullname:
            user.name = fullname
            update_fields.append("name")
        user.save(update_fields=update_fields)
        tokens = get_tokens_for_user(user)
        return success_response(data=tokens, message="Profile marked complete, tokens refreshed")


# ── Student: self-service password change ──────────────────────────────────────

class StudentChangePasswordView(APIView):
    """Authenticated student changes their own password. Returns fresh tokens."""
    permission_classes = [IsStudentUser]

    def post(self, request):
        serializer = StudentChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", errors=serializer.errors, status_code=400)

        user = request.user
        if not isinstance(user, User):
            return error_response("Not allowed", status_code=403)

        if not user.check_password(serializer.validated_data["current_password"]):
            return error_response(
                "Current password is incorrect.", status_code=400
            )

        user.set_password(serializer.validated_data["new_password"])
        user.force_password_change = False
        user.token_version += 1  # invalidate all old tokens
        user.save(update_fields=["password", "force_password_change", "token_version", "updated_at"])

        tokens = get_tokens_for_user(user)
        logger.info(
            "Student %s changed their password from IP=%s",
            user.student_id or user.email, _get_client_ip(request),
        )
        return success_response(data=tokens, message="Password changed successfully.")


# ── Admin: self-service profile ────────────────────────────────────────────────

def _admin_profile_data(user) -> dict:
    """Shared serialisation for admin self-profile responses."""
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "is_active": user.is_active,
        # ISO-8601 timestamp so the frontend can display "Member since …"
        "date_joined": user.created_at.isoformat() if user.created_at else None,
    }


class AdminSelfProfileView(APIView):
    """Admin or Super Admin views or updates their own profile (name only;
    email is immutable). Opened to Super Admin 2026-08-20, mirroring the
    self-service profile Admin already had."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        user = request.user
        if not isinstance(user, User):
            return error_response("Not allowed", status_code=403)
        return success_response(data=_admin_profile_data(user))

    def patch(self, request):
        serializer = AdminSelfUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", errors=serializer.errors, status_code=400)

        user = request.user
        if not isinstance(user, User):
            return error_response("Not allowed", status_code=403)

        user.name = serializer.validated_data.get("name", user.name)
        user.save(update_fields=["name", "updated_at"])
        logger.info("%s %s updated their profile name", user.role, user.email)
        return success_response(
            data=_admin_profile_data(user),
            message="Profile updated successfully.",
        )


class AdminChangePasswordView(APIView):
    """Admin or Super Admin changes their own password. Opened to Super
    Admin 2026-08-20, mirroring the self-service change Admin already had."""
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request):
        serializer = AdminChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", errors=serializer.errors, status_code=400)

        user = request.user
        if not isinstance(user, User):
            return error_response("Not allowed", status_code=403)

        if not user.check_password(serializer.validated_data["current_password"]):
            return error_response("Current password is incorrect.", status_code=400)

        new_pw = serializer.validated_data["new_password"]
        if user.check_password(new_pw):
            return error_response(
                "New password must be different from the current password.", status_code=400
            )

        user.set_password(new_pw)
        user.force_password_change = False
        user.token_version += 1  # invalidate all old tokens — new login required
        user.save(update_fields=["password", "force_password_change", "token_version", "updated_at"])
        logger.info(
            "%s %s changed their password from IP=%s",
            user.role, user.email, _get_client_ip(request),
        )
        tokens = get_tokens_for_user(user)
        return success_response(data=tokens, message="Password changed successfully.")


# ── Admin: shared lookups ────────────────────────────────────────────────────

class AdminUserLookupView(APIView):
    """GET /api/auth/admin/users/lookup/?ids=<uuid>,<uuid>,... — resolves a
    batch of user_ids to display name/email, scoped to the requesting
    admin's own institution only. Any admin or super admin may call this
    (unlike AdminListCreateView below, which is roster *management* and
    stays super-admin-only) — this is a read-only "whose account is this"
    lookup that any admin viewing shared institution content (e.g. another
    admin's authored question paper) needs.

    Bulk-by-ids, not one-id-per-call — callers (e.g. assessment-service's
    auth_service_client.resolve_user_names, used for papers-list "Created
    by <name>" labels) batch every id they need into one request instead of
    N+1 calling per row.

    An id outside the caller's own institution is silently omitted from the
    response, not 403'd or 404'd individually — that would let a caller
    probe for the existence of ids in other institutions one at a time.
    """
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        raw_ids = request.query_params.get("ids", "")
        ids = []
        for part in raw_ids.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.append(uuid.UUID(part))
            except ValueError:
                continue  # malformed id — just unresolvable, not a 400
        # Defensive cap — this endpoint answers "resolve the authors shown
        # on one page of results," never an arbitrarily large batch.
        ids = ids[:100]

        if not ids:
            return success_response(data=[])

        users = User.objects.filter(id__in=ids, institution_id=request.user.institution_id)
        data = [{"id": str(u.id), "name": u.name, "email": u.email} for u in users]
        return success_response(data=data)


# ── Admin Management (Super Admin only) ────────────────────────────────────────

class AdminListCreateView(APIView):
    """List all admin accounts (Super Admin, IT) or create a new one (IT only).

    Admin account management moved to IT (2026-08-19): phase 1 gave IT the
    same full access Super Admin had (validated live); phase 2, same day,
    restricts Super Admin to read-only here, matching the Batches treatment.
    """
    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsSuperAdminOrIT()]
        return [IsITUser()]

    def get(self, request):
        admins = User.objects.filter(role="admin").order_by("-created_at")
        return success_response(data=AdminSerializer(admins, many=True).data)

    def post(self, request):
        serializer = AdminCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", errors=serializer.errors, status_code=400)

        data = serializer.validated_data

        # institution_id flows from the creator's own account (super_admin or,
        # since 2026-08-19, it) — they belong to one college and every faculty
        # account they create is scoped to that same college.
        institution_id = request.user.institution_id
        if not institution_id:
            logger.error(
                "%s %s has no institution_id — cannot create faculty account.",
                request.user.role, request.user.email,
            )
            return error_response(
                "Your account is not linked to an institution. "
                "Contact the platform team to assign an institution.",
                status_code=500,
            )

        if User.objects.filter(email=data["email"]).exists():
            return error_response(
                "An account with this email already exists.", status_code=409
            )

        admin = User(
            email=data["email"],
            role="admin",
            name=data.get("name", ""),
            department=data.get("department", ""),
            institution_id=institution_id,
            force_password_change=True,  # must change password on first login
        )
        admin.set_password(settings.ADMIN_DEFAULT_PASSWORD)
        admin.save()
        logger.info(
            "Admin account created: %s by %s=%s institution_id=%s IP=%s",
            admin.email, request.user.role, request.user.email, institution_id, _get_client_ip(request),
        )
        return success_response(
            data=AdminSerializer(admin).data,
            message="Admin account created successfully.",
            status_code=201,
        )


class AdminDetailView(APIView):
    """Retrieve an admin account (Super Admin, IT); update (name / is_active)
    or delete (IT only) — see AdminListCreateView above for the 2026-08-19
    phase 1/phase 2 history."""
    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsSuperAdminOrIT()]
        return [IsITUser()]

    def _get_admin(self, pk):
        try:
            return User.objects.get(pk=pk, role="admin")
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        admin = self._get_admin(pk)
        if not admin:
            return error_response("Admin not found.", status_code=404)
        return success_response(data=AdminSerializer(admin).data)

    def patch(self, request, pk):
        admin = self._get_admin(pk)
        if not admin:
            return error_response("Admin not found.", status_code=404)

        serializer = AdminUpdateExtendedSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", errors=serializer.errors, status_code=400)

        data = serializer.validated_data
        update_fields = ["updated_at"]

        if "name" in data:
            admin.name = data["name"]
            update_fields.append("name")
        if "is_active" in data:
            admin.is_active = data["is_active"]
            update_fields.append("is_active")
        if "department" in data:
            admin.department = data["department"]
            update_fields.append("department")

        admin.save(update_fields=update_fields)
        logger.info(
            "Admin %s updated by %s=%s — fields: %s",
            admin.email, request.user.role, request.user.email, update_fields,
        )
        return success_response(
            data=AdminSerializer(admin).data,
            message="Admin updated successfully.",
        )

    def delete(self, request, pk):
        admin = self._get_admin(pk)
        if not admin:
            return error_response("Admin not found.", status_code=404)

        email = admin.email
        admin.delete()
        logger.info("Admin %s permanently deleted by %s=%s", email, request.user.role, request.user.email)
        return success_response(message="Admin account deleted permanently.")


class AdminResetDefaultPasswordView(APIView):
    """Reset an admin's password back to the default (spark@123). IT-exclusive
    (2026-08-19, phase 2) — a write-only action with no read equivalent, so
    Super Admin loses it outright rather than keeping a read-only remnant."""
    permission_classes = [IsITUser]

    def post(self, request, pk):
        try:
            admin = User.objects.get(pk=pk, role="admin")
        except User.DoesNotExist:
            return error_response("Admin not found.", status_code=404)

        admin.set_password(settings.ADMIN_DEFAULT_PASSWORD)
        admin.force_password_change = True
        admin.token_version += 1  # invalidate existing tokens immediately
        admin.save(update_fields=["password", "force_password_change", "token_version", "updated_at"])
        logger.info(
            "Admin %s password reset to default by %s=%s IP=%s",
            admin.email, request.user.role, request.user.email, _get_client_ip(request),
        )
        return success_response(message="Password reset to default successfully.")


MAX_BULK_IMPORT = 1000


def _bulk_create_accounts(request, role, default_password):
    """Shared by AdminBulkCreateView and SuperAdminBulkCreateView (2026-08-20,
    revised same day) — bulk CSV import for IT, mirroring
    AdminStudentBulkCreateView in user-service exactly: the CSV is a single
    column of emails (source of mail IDs only), with one Department picked
    in the UI and applied to every row — same shape as the student bulk
    import's shared Department+Batch, not a per-row column. `name` is not
    collected here; bulk-created accounts start blank and can be renamed via
    the ordinary edit flow, same as bulk-created students. One POST with the
    whole email list, existing emails pre-fetched once (not per-email),
    every email appended to `results` whether it succeeds or fails, response
    {total, created, rejected, results}."""
    emails_raw = request.data.get("emails")
    department = str(request.data.get("department", "")).strip()

    if not isinstance(emails_raw, list):
        return error_response("emails must be a list of strings.", status_code=400)
    if not emails_raw:
        return error_response("No emails provided.", status_code=400)
    if len(emails_raw) > MAX_BULK_IMPORT:
        return error_response(
            f"Maximum {MAX_BULK_IMPORT} accounts per import. Received {len(emails_raw)}.",
            status_code=400,
        )
    if not department:
        return error_response("department is required.", status_code=400)

    institution_id = request.user.institution_id
    if not institution_id:
        logger.error(
            "IT %s has no institution_id — cannot bulk-create %s accounts.",
            request.user.email, role,
        )
        return error_response(
            "Your account is not linked to an institution. "
            "Contact the platform team to assign an institution.",
            status_code=500,
        )

    email_validator = EmailValidator()

    normalized = [str(e if e is not None else "").strip().lower() for e in emails_raw]

    non_empty_emails = [e for e in normalized if e]
    existing_emails = set(
        User.objects.filter(email__in=non_empty_emails).values_list("email", flat=True)
    )

    results = []
    seen = set()
    created_count = 0
    rejected_count = 0

    for email in normalized:
        if not email:
            results.append({"email": "(empty)", "status": "rejected", "reason": "Email is required."})
            rejected_count += 1
            continue

        try:
            email_validator(email)
        except ValidationError:
            results.append({"email": email, "status": "rejected", "reason": "Invalid email format."})
            rejected_count += 1
            continue

        if email in seen:
            results.append({"email": email, "status": "rejected", "reason": "Duplicate in import file."})
            rejected_count += 1
            continue
        seen.add(email)

        if email in existing_emails:
            results.append({"email": email, "status": "rejected", "reason": "An account with this email already exists."})
            rejected_count += 1
            continue

        account = User(
            email=email,
            role=role,
            name="",
            department=department,
            institution_id=institution_id,
            force_password_change=True,
        )
        account.set_password(default_password)
        account.save()
        existing_emails.add(email)
        results.append({"email": email, "status": "created"})
        created_count += 1

    logger.info(
        "Bulk %s import: %s created, %s rejected, by it=%s institution_id=%s IP=%s",
        role, created_count, rejected_count, request.user.email, institution_id, _get_client_ip(request),
    )
    return success_response(
        data={
            "total": len(normalized),
            "created": created_count,
            "rejected": rejected_count,
            "results": results,
        },
        message=f"Import complete: {created_count} created, {rejected_count} rejected.",
    )


class AdminBulkCreateView(APIView):
    """Bulk-create admin accounts from a CSV-derived row list. IT only."""
    permission_classes = [IsITUser]

    def post(self, request):
        return _bulk_create_accounts(request, "admin", settings.ADMIN_DEFAULT_PASSWORD)


class AdminPasswordResetByIdView(APIView):
    """Reset an admin's password to a custom value using admin_id in the body. Super Admin only."""
    permission_classes = [IsSuperAdminUser]

    def post(self, request):
        serializer = AdminPasswordResetByIdSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", errors=serializer.errors, status_code=400)

        try:
            admin = User.objects.get(
                pk=serializer.validated_data["admin_id"], role="admin"
            )
        except User.DoesNotExist:
            return error_response("Admin not found.", status_code=404)

        admin.set_password(serializer.validated_data["new_password"])
        admin.force_password_change = False
        admin.token_version += 1
        admin.save(update_fields=["password", "force_password_change", "token_version", "updated_at"])
        logger.info(
            "Admin %s password reset by super_admin=%s IP=%s",
            admin.email, request.user.email, _get_client_ip(request),
        )
        return success_response(message="Admin password reset successfully.")


# ── Super Admin account management (IT-exclusive) ────────────────────────────
# Added 2026-08-20: IT is now the platform's bootstrapped root (see
# create_default_it), and provisions Super Admin accounts the same way it
# already provisions Admin accounts — byte-for-byte the same mechanism as
# AdminListCreateView / AdminDetailView / AdminResetDefaultPasswordView
# above. Unlike Admin management, there is no read-only remnant for the
# managed role: a Super Admin has zero access here, not even GET — matching
# how an Admin has zero visibility into other Admin accounts today. This
# replaces the old IT-account-management block (ITListCreateView /
# ITDetailView / ITResetDefaultPasswordView, Super-Admin-only) — IT is now
# single-account and bootstrapped, so nothing creates additional IT accounts.

class SuperAdminListCreateView(APIView):
    """List all super_admin accounts or create a new one. IT only."""
    permission_classes = [IsITUser]

    def get(self, request):
        super_admins = User.objects.filter(role="super_admin").order_by("-created_at")
        return success_response(data=AdminSerializer(super_admins, many=True).data)

    def post(self, request):
        serializer = AdminCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", errors=serializer.errors, status_code=400)

        data = serializer.validated_data

        # Same institution-scoping rule as admin creation — a super_admin
        # account belongs to the same college as the IT account that created it.
        institution_id = request.user.institution_id
        if not institution_id:
            logger.error(
                "IT %s has no institution_id — cannot create super_admin account.",
                request.user.email,
            )
            return error_response(
                "Your account is not linked to an institution. "
                "Contact the platform team to assign an institution.",
                status_code=500,
            )

        if User.objects.filter(email=data["email"]).exists():
            return error_response(
                "An account with this email already exists.", status_code=409
            )

        super_admin = User(
            email=data["email"],
            role="super_admin",
            name=data.get("name", ""),
            department=data.get("department", ""),
            institution_id=institution_id,
            force_password_change=True,  # must change password on first login
        )
        super_admin.set_password(settings.SUPERADMIN_DEFAULT_PASSWORD)
        super_admin.save()
        logger.info(
            "Super admin account created: %s by it=%s institution_id=%s IP=%s",
            super_admin.email, request.user.email, institution_id, _get_client_ip(request),
        )
        return success_response(
            data=AdminSerializer(super_admin).data,
            message="Super admin account created successfully.",
            status_code=201,
        )


class SuperAdminDetailView(APIView):
    """Retrieve, update (name / is_active), or delete a super_admin account. IT only."""
    permission_classes = [IsITUser]

    def _get_super_admin(self, pk):
        try:
            return User.objects.get(pk=pk, role="super_admin")
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        super_admin = self._get_super_admin(pk)
        if not super_admin:
            return error_response("Super admin not found.", status_code=404)
        return success_response(data=AdminSerializer(super_admin).data)

    def patch(self, request, pk):
        super_admin = self._get_super_admin(pk)
        if not super_admin:
            return error_response("Super admin not found.", status_code=404)

        serializer = AdminUpdateExtendedSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", errors=serializer.errors, status_code=400)

        data = serializer.validated_data
        update_fields = ["updated_at"]

        if "name" in data:
            super_admin.name = data["name"]
            update_fields.append("name")
        if "is_active" in data:
            super_admin.is_active = data["is_active"]
            update_fields.append("is_active")
        if "department" in data:
            super_admin.department = data["department"]
            update_fields.append("department")

        super_admin.save(update_fields=update_fields)
        logger.info(
            "Super admin %s updated by it=%s — fields: %s",
            super_admin.email, request.user.email, update_fields,
        )
        return success_response(
            data=AdminSerializer(super_admin).data,
            message="Super admin updated successfully.",
        )

    def delete(self, request, pk):
        super_admin = self._get_super_admin(pk)
        if not super_admin:
            return error_response("Super admin not found.", status_code=404)

        email = super_admin.email
        super_admin.delete()
        logger.info("Super admin %s permanently deleted by it=%s", email, request.user.email)
        return success_response(message="Super admin account deleted permanently.")


class SuperAdminResetDefaultPasswordView(APIView):
    """IT resets a super_admin's password back to the default."""
    permission_classes = [IsITUser]

    def post(self, request, pk):
        try:
            super_admin = User.objects.get(pk=pk, role="super_admin")
        except User.DoesNotExist:
            return error_response("Super admin not found.", status_code=404)

        super_admin.set_password(settings.SUPERADMIN_DEFAULT_PASSWORD)
        super_admin.force_password_change = True
        super_admin.token_version += 1  # invalidate existing tokens immediately
        super_admin.save(update_fields=["password", "force_password_change", "token_version", "updated_at"])
        logger.info(
            "Super admin %s password reset to default by it=%s IP=%s",
            super_admin.email, request.user.email, _get_client_ip(request),
        )
        return success_response(message="Password reset to default successfully.")


class SuperAdminBulkCreateView(APIView):
    """Bulk-create super_admin accounts from a CSV-derived row list. IT only."""
    permission_classes = [IsITUser]

    def post(self, request):
        return _bulk_create_accounts(request, "super_admin", settings.SUPERADMIN_DEFAULT_PASSWORD)


# ── Department management (2026-08-20) ────────────────────────────────────────
# Read: Admin + Super Admin + IT (they all consume this as dropdown/filter
# options across the app). Write: IT only. Mirrors Batch's read/write split
# in user-service (IsAdminOrSuperAdminOrIT / IsITUser), the closest existing
# precedent for "IT-managed reference data other roles only read."

class DepartmentListCreateView(APIView):
    """List all departments for the caller's institution, or create one. IT-only create."""
    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAdminOrSuperAdminOrIT()]
        return [IsITUser()]

    def get(self, request):
        institution_id = None if request.user.role == "super_admin" else getattr(request.user, "institution_id", None)
        departments = Department.objects.all()
        if institution_id:
            departments = departments.filter(institution_id=institution_id)
        return success_response(data=DepartmentSerializer(departments, many=True).data)

    def post(self, request):
        institution_id = request.user.institution_id
        if not institution_id:
            logger.error("IT %s has no institution_id — cannot create department.", request.user.email)
            return error_response(
                "Your account is not linked to an institution. "
                "Contact the platform team to assign an institution.",
                status_code=500,
            )

        serializer = DepartmentCreateSerializer(data=request.data, context={"institution_id": institution_id})
        if not serializer.is_valid():
            return error_response("Validation failed", errors=serializer.errors, status_code=400)

        data = serializer.validated_data
        department = Department.objects.create(
            code=data["code"],
            name=data.get("name", ""),
            institution_id=institution_id,
            is_active=data.get("is_active", True),
        )
        logger.info(
            "Department created: %s by it=%s institution_id=%s IP=%s",
            department.code, request.user.email, institution_id, _get_client_ip(request),
        )
        return success_response(
            data=DepartmentSerializer(department).data,
            message="Department created successfully.",
            status_code=201,
        )


class DepartmentDetailView(APIView):
    """Retrieve, update (name / is_active), or delete a department. IT-only write."""
    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAdminOrSuperAdminOrIT()]
        return [IsITUser()]

    def _get_department(self, request, pk):
        institution_id = None if request.user.role == "super_admin" else getattr(request.user, "institution_id", None)
        qs = Department.objects.all()
        if institution_id:
            qs = qs.filter(institution_id=institution_id)
        try:
            return qs.get(pk=pk)
        except Department.DoesNotExist:
            return None

    def get(self, request, pk):
        department = self._get_department(request, pk)
        if not department:
            return error_response("Department not found.", status_code=404)
        return success_response(data=DepartmentSerializer(department).data)

    def patch(self, request, pk):
        department = self._get_department(request, pk)
        if not department:
            return error_response("Department not found.", status_code=404)

        serializer = DepartmentUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", errors=serializer.errors, status_code=400)

        data = serializer.validated_data
        update_fields = ["updated_at"]

        if "name" in data:
            department.name = data["name"]
            update_fields.append("name")
        if "is_active" in data:
            department.is_active = data["is_active"]
            update_fields.append("is_active")

        department.save(update_fields=update_fields)
        logger.info(
            "Department %s updated by it=%s — fields: %s",
            department.code, request.user.email, update_fields,
        )
        return success_response(
            data=DepartmentSerializer(department).data,
            message="Department updated successfully.",
        )

    def delete(self, request, pk):
        department = self._get_department(request, pk)
        if not department:
            return error_response("Department not found.", status_code=404)

        code = department.code
        department.delete()
        logger.info("Department %s permanently deleted by it=%s", code, request.user.email)
        return success_response(message="Department deleted permanently.")


# ── Internal service-to-service endpoints (user-service → auth-service) ────────
# Accessible only within the Docker network via http://auth-service:8000.
# Protected by X-Service-Key header — never routed through nginx from outside.

class InternalStudentCreateView(APIView):
    """
    Called by user-service when a new student is created.
    Creates the corresponding auth User so the student can log in.
    """
    permission_classes = [IsInternalService]
    authentication_classes = []  # No JWT — service key auth only
    # Legitimate high-frequency internal traffic (bypasses nginx entirely —
    # called directly on the Docker network) must not share the anon/user
    # DRF throttle buckets meant for external-facing endpoints.
    throttle_classes = []

    def post(self, request):
        user_id = request.data.get("user_id")
        student_id = request.data.get("student_id")
        institution_id = request.data.get("institution_id")

        if not user_id or not student_id:
            return error_response("user_id and student_id are required.", status_code=400)
        if not institution_id:
            return error_response("institution_id is required.", status_code=400)

        # ── Idempotency check on user_id (primary key) ────────────────────────
        # If the client timed out after auth-service already processed a prior
        # attempt, the same user_id arrives again.  Treat it as success rather
        # than crashing on a primary-key conflict.
        existing_by_pk = User.objects.filter(pk=user_id).first()
        if existing_by_pk:
            if existing_by_pk.student_id == student_id:
                logger.info(
                    "Idempotent create: auth account for student_id=%s already exists "
                    "(user_id=%s) — returning success.",
                    student_id, user_id,
                )
                return success_response(
                    data={"id": str(existing_by_pk.id), "student_id": existing_by_pk.student_id},
                    message="Auth account created.",
                    status_code=201,
                )
            else:
                return error_response(
                    f"User ID '{user_id}' is already assigned to a different student.",
                    status_code=409,
                )

        # ── Check for existing account by student_id ───────────────────────
        existing = User.objects.filter(student_id=student_id).first()
        if existing:
            # An existing record with a DIFFERENT user_id means the old student
            # was deleted in user-service but auth cleanup failed (non-fatal path).
            # user-service is the source of truth for student existence; if it is
            # issuing a create with a new user_id, the old auth record is an orphan
            # regardless of its is_active flag.
            existing.delete()
            logger.info(
                "Removed orphan auth account (is_active=%s) for student_id=%s before re-creation",
                existing.is_active,
                student_id,
            )

        try:
            user = User(
                id=user_id,
                student_id=student_id,
                # Students log in via student_id, not email.
                # A deterministic internal address satisfies the unique constraint
                # without exposing a real email address.
                email=f"{student_id.lower()}@students.internal",
                role="student",
                institution_id=institution_id,
                force_password_change=True,  # must change password on first login
            )
            user.set_password(settings.STUDENT_DEFAULT_PASSWORD)
            user.save()
        except Exception as exc:
            logger.error("Internal student create failed for student_id=%s: %s", student_id, exc)
            return error_response("Failed to create auth account.", status_code=500)

        logger.info("Auth account created for student_id=%s by internal service", student_id)
        return success_response(
            data={"id": str(user.id), "student_id": user.student_id},
            message="Auth account created.",
            status_code=201,
        )


class InternalStudentUpdateView(APIView):
    """
    Called by user-service when a student's is_active status changes
    (deactivate / reactivate).
    """
    permission_classes = [IsInternalService]
    authentication_classes = []
    throttle_classes = []

    def patch(self, request, student_id):
        is_active = request.data.get("is_active")
        if is_active is None:
            return error_response("is_active is required.", status_code=400)

        try:
            user = User.objects.get(student_id=student_id, role="student")
        except User.DoesNotExist:
            return error_response("Student auth account not found.", status_code=404)
        except User.MultipleObjectsReturned:
            logger.critical("Data integrity error: multiple auth records for student_id=%s", student_id)
            return error_response("System error", status_code=500)

        user.is_active = bool(is_active)
        user.save(update_fields=["is_active"])
        logger.info(
            "Student %s is_active=%s set by internal service", student_id, user.is_active
        )
        return success_response(message="Student auth account updated.")


class InternalStudentDeleteView(APIView):
    """
    Called by user-service when a student record is permanently removed.
    Deletes the corresponding auth User.
    """
    permission_classes = [IsInternalService]
    authentication_classes = []
    throttle_classes = []

    def delete(self, request, student_id):
        expected_user_id = (request.data or {}).get("expected_user_id")

        try:
            user = User.objects.get(student_id=student_id, role="student")
        except User.DoesNotExist:
            # Already gone — idempotent success.
            return success_response(message="Student auth account not found (already deleted).")
        except User.MultipleObjectsReturned:
            logger.critical("Data integrity error: multiple auth records for student_id=%s", student_id)
            return error_response("System error", status_code=500)

        if expected_user_id and str(user.id) != str(expected_user_id):
            # The student was deleted and then immediately re-added with a new
            # user_id.  The outbox event targets the OLD account; the new one
            # must never be touched.
            logger.info(
                "Delete skipped for student_id=%s: existing id=%s does not match "
                "expected=%s (student was re-created with a new account).",
                student_id, user.id, expected_user_id,
            )
            return success_response(
                message="Auth account belongs to a re-created student — skipped."
            )

        user.delete()
        logger.info("Auth account for student_id=%s deleted by internal service", student_id)
        return success_response(message="Student auth account deleted.")
