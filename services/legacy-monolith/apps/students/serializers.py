from django.contrib.auth import get_user_model
from rest_framework import serializers
from apps.batches.models import Batch
from .models import Student, Inquiry, ScrollConfig, ScrollUpdate, ResourceModule, ResourceSection, ResourceUpload

User = get_user_model()

DEFAULT_PASSWORD = "ANITS@123"


class StudentListSerializer(serializers.ModelSerializer):
    """Compact serializer for list views."""
    email = serializers.SerializerMethodField()
    batch_name = serializers.CharField(source="batch.batch_name", read_only=True)

    class Meta:
        model = Student
        fields = [
            "id", "student_id", "fullname", "email",
            "department", "batch_id", "batch_name",
            "is_active", "is_profile_completed", "created_at",
        ]

    def get_email(self, obj):
        return obj.college_email_id or ""


class StudentDetailSerializer(serializers.ModelSerializer):
    """Full serializer for create/retrieve/update."""
    batch_name = serializers.CharField(source="batch.batch_name", read_only=True)
    batch_id = serializers.PrimaryKeyRelatedField(
        queryset=Batch.objects.all(), source="batch", write_only=False
    )

    class Meta:
        model = Student
        fields = [
            "id", "student_id", "fullname", "college_email_id",
            "department", "batch_id", "batch_name",
            "is_active", "is_profile_completed", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "student_id", "is_active", "is_profile_completed", "created_at", "updated_at"]


class StudentCreateSerializer(serializers.Serializer):
    student_id = serializers.CharField(max_length=100)
    department = serializers.CharField(max_length=255)
    batch_id = serializers.UUIDField()

    def validate_student_id(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("student_id cannot be empty.")
        if Student.objects.filter(student_id=value).exists():
            raise serializers.ValidationError("A student with this ID already exists.")
        return value

    def validate_department(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Department cannot be empty.")
        return value

    def validate_batch_id(self, value):
        try:
            return Batch.objects.get(pk=value)
        except Batch.DoesNotExist:
            raise serializers.ValidationError("Batch does not exist.")

    def create(self, validated_data):
        batch = validated_data["batch_id"]
        email = f"{validated_data['student_id'].lower()}@aptlogic.internal"
        user = User.objects.create_user(
            email=email,
            password=DEFAULT_PASSWORD,
            role="student",
        )
        student = Student.objects.create(
            student_id=validated_data["student_id"],
            user=user,
            department=validated_data["department"],
            batch=batch,
        )
        return student


class StudentEditSerializer(serializers.ModelSerializer):
    batch_id = serializers.PrimaryKeyRelatedField(
        queryset=Batch.objects.all(), source="batch"
    )

    class Meta:
        model = Student
        fields = ["fullname", "college_email_id", "department", "batch_id"]

    def validate_department(self, value):
        value = value.strip() if value else value
        if not value:
            raise serializers.ValidationError("Department cannot be empty.")
        return value


class StudentProfileSerializer(serializers.ModelSerializer):
    """Student's own profile — readonly fields enforced."""
    batch_name = serializers.CharField(source="batch.batch_name", read_only=True)

    class Meta:
        model = Student
        fields = [
            "student_id", "fullname", "college_email_id",
            "department", "batch_id", "batch_name", "is_profile_completed",
        ]
        read_only_fields = ["student_id", "department", "batch_id", "batch_name", "is_profile_completed"]

    def validate_fullname(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Full name cannot be empty.")
        return value.strip()

    def validate_college_email_id(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("College email cannot be empty.")
        return value.strip()


class InquirySerializer(serializers.ModelSerializer):
    """Inquiry with full student context — used by both student submit and admin list."""
    student_id = serializers.CharField(source="student.student_id", read_only=True)
    fullname = serializers.CharField(source="student.fullname", read_only=True, default="")
    college_email_id = serializers.EmailField(source="student.college_email_id", read_only=True, default="")
    department = serializers.CharField(source="student.department", read_only=True)
    batch_name = serializers.CharField(source="student.batch.batch_name", read_only=True)

    class Meta:
        model = Inquiry
        fields = [
            "id", "student_id", "fullname", "college_email_id",
            "department", "batch_name", "message", "is_read", "created_at",
        ]
        read_only_fields = [
            "id", "student_id", "fullname", "college_email_id",
            "department", "batch_name", "is_read", "created_at",
        ]


class ScrollConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScrollConfig
        fields = ["is_enabled", "direction", "updated_at"]
        read_only_fields = ["updated_at"]


class ScrollUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScrollUpdate
        fields = ["id", "text", "link", "show_new_badge", "order", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_text(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Text cannot be empty.")
        return value

    def validate_link(self, value):
        return value.strip() if value else ""


class ScrollReorderSerializer(serializers.Serializer):
    """Accepts an ordered list of UUIDs — reorders updates to match."""
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
    )


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    repeat_new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["repeat_new_password"]:
            raise serializers.ValidationError({"repeat_new_password": "Passwords do not match."})
        return attrs


class ResourceModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ResourceModule
        fields = ["id", "name", "is_published", "is_system", "order", "created_at", "updated_at"]
        read_only_fields = ["id", "is_system", "order", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Module name cannot be empty.")
        return value


class ResourceSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ResourceSection
        fields = ["id", "module_id", "name", "is_published", "order", "created_at", "updated_at"]
        read_only_fields = ["id", "module_id", "order", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Section name cannot be empty.")
        return value


class ResourceUploadSerializer(serializers.ModelSerializer):
    read_url = serializers.SerializerMethodField()

    class Meta:
        model  = ResourceUpload
        fields = [
            "id", "resource_section_id", "upload_type",
            "file_url", "read_url", "original_filename",
            "file_size_bytes", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "resource_section_id", "read_url", "created_at", "updated_at"]

    def get_read_url(self, obj):
        from core.storage import get_cdn_url, is_file_type
        if is_file_type(obj.upload_type):
            return get_cdn_url(obj.file_url)
        return obj.file_url


# ── Reuse companies upload request serializers ────────────────────────────────
# These are generic (no Company/Section fields) — safe to import and reuse.
from apps.companies.serializers import (
    PresignedUploadRequestSerializer,   # noqa: F401  (re-exported for views)
    ConfirmUploadSerializer,            # noqa: F401
    AddLinkSerializer,                  # noqa: F401
)
