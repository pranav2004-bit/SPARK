from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()

VALID_ROLES = ("admin", "student", "super_admin")

# ── Admin management serializers ───────────────────────────────────────────────

class AdminSerializer(serializers.ModelSerializer):
    """Read serializer for admin user records returned to super admin."""
    class Meta:
        model = User
        fields = ["id", "email", "name", "department", "is_active", "created_at"]
        read_only_fields = fields


class AdminCreateSerializer(serializers.Serializer):
    name  = serializers.CharField(max_length=150, trim_whitespace=True, required=False, allow_blank=True, default="")
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower().strip()

    def validate_name(self, value):
        return value.strip()


class AdminUpdateExtendedSerializer(serializers.Serializer):
    """
    Super-admin PATCH on an admin account.
    Both fields are optional; at least one must be supplied.
    """
    name = serializers.CharField(max_length=150, trim_whitespace=True, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    def validate_name(self, value):
        return value.strip()

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one field (name, is_active) must be provided.")
        return attrs


# kept for backward-compat — existing tests use AdminUpdateSerializer via the
# deactivate path; we now route through AdminUpdateExtendedSerializer but keep
# this so nothing else breaks.
class AdminUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


class AdminPasswordResetByIdSerializer(serializers.Serializer):
    admin_id = serializers.UUIDField()
    new_password = serializers.CharField(write_only=True, min_length=8)


# ── Admin self-service serializers ────────────────────────────────────────────

class AdminSelfUpdateSerializer(serializers.Serializer):
    """Admin updates their own name."""
    name = serializers.CharField(max_length=150, trim_whitespace=True, required=False, allow_blank=True, default="")

    def validate_name(self, value):
        return value.strip()


class AdminChangePasswordSerializer(serializers.Serializer):
    """Admin changes their own password."""
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs


# ── Student serializers ───────────────────────────────────────────────────────

class StudentChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=6)
    repeat_new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["repeat_new_password"]:
            raise serializers.ValidationError(
                {"repeat_new_password": "Passwords do not match."}
            )
        return attrs


# ── Login / Logout ─────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    """
    Unified login serializer for all 3 roles.
    - admin / super_admin: email + password
    - student: student_id + password
    """
    role = serializers.ChoiceField(choices=VALID_ROLES)
    email = serializers.EmailField(required=False, allow_blank=True)
    student_id = serializers.CharField(required=False, allow_blank=True, max_length=100)
    password = serializers.CharField(write_only=True, min_length=1)

    def validate_email(self, value):
        return value.lower().strip() if value else value

    def validate_student_id(self, value):
        return value.strip() if value else value

    def validate(self, attrs):
        role = attrs["role"]
        if role == "student":
            if not attrs.get("student_id"):
                raise serializers.ValidationError({"student_id": "student_id is required for student login."})
        else:
            if not attrs.get("email"):
                raise serializers.ValidationError({"email": "email is required for admin/super_admin login."})
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class StudentPasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, min_length=6)


class AdminPasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, min_length=6)
