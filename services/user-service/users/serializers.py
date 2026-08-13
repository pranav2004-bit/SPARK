import uuid
from rest_framework import serializers
from .models import Batch, Student, Inquiry, ScrollConfig, ScrollUpdate, OutboxEvent


class BatchSerializer(serializers.ModelSerializer):
    student_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Batch
        fields = ["id", "batch_name", "student_count", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at", "student_count"]

    def validate_batch_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Batch name cannot be empty.")
        if len(value) > 255:
            raise serializers.ValidationError("Batch name cannot exceed 255 characters.")
        return value

    def validate(self, attrs):
        batch_name = attrs.get("batch_name", "")
        institution_id = self.context.get("institution_id")
        instance = self.instance
        qs = Batch.objects.filter(batch_name__iexact=batch_name)
        if institution_id:
            qs = qs.filter(institution_id=institution_id)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"batch_name": "A batch with this name already exists."})
        return attrs


class StudentListSerializer(serializers.ModelSerializer):
    college_email_id = serializers.CharField(default="")
    batch_name = serializers.CharField(source="batch.batch_name", read_only=True)

    class Meta:
        model = Student
        fields = [
            # user_id (the auth-service account UUID, i.e. the JWT's
            # user_id claim) is additive here for assessment-service's
            # roster-snapshot call (LIVETRACKER2_V1.md Task 3.1) — it needs
            # this exact value so StudentSetAllocation.student_id matches
            # request.user.id when the student later authenticates, the
            # same convention analytics-service already uses. "id" (this
            # Student row's own PK) is unrelated and insufficient for that
            # purpose. Purely additive: existing consumers of this endpoint
            # are unaffected by one more key in each result object.
            "id", "user_id", "student_id", "fullname", "college_email_id",
            "department", "batch_id", "batch_name",
            "is_active", "is_profile_completed", "created_at",
        ]


class StudentDetailSerializer(serializers.ModelSerializer):
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
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("Student ID cannot be empty.")
        existing = Student.objects.filter(student_id=value).first()
        if existing:
            if existing.is_active:
                raise serializers.ValidationError("A student with this ID already exists.")
            else:
                raise serializers.ValidationError(
                    "This Student ID belongs to a deactivated account. "
                    "Reactivate the existing student instead of creating a new one."
                )
        return value

    def validate_department(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Department cannot be empty.")
        return value

    def validate_batch_id(self, value):
        institution_id = self.context.get("institution_id")
        qs = Batch.objects.filter(pk=value)
        if institution_id:
            qs = qs.filter(institution_id=institution_id)
        try:
            return qs.get()
        except Batch.DoesNotExist:
            raise serializers.ValidationError("Batch not found in this institution.")

    def create(self, validated_data):
        import logging
        from core.auth_client import create_student_auth, delete_student_auth
        log = logging.getLogger(__name__)

        institution_id = self.context.get("institution_id")
        batch = validated_data["batch_id"]
        user_id = uuid.uuid4()

        # Step 1 — create auth account first so the student can log in immediately.
        try:
            create_student_auth(
                user_id=str(user_id),
                student_id=validated_data["student_id"],
                institution_id=str(institution_id) if institution_id else None,
            )
        except RuntimeError as exc:
            raise serializers.ValidationError(
                {"non_field_errors": [f"Could not create student account: {exc}"]}
            )

        # Step 2 — create the profile record in user-service.
        try:
            student = Student.objects.create(
                user_id=user_id,
                student_id=validated_data["student_id"],
                department=validated_data["department"],
                batch=batch,
                institution_id=institution_id,
            )
        except Exception:
            # Compensating transaction: remove the auth account we just created.
            delete_student_auth(validated_data["student_id"])
            log.error(
                "Student profile creation failed for student_id=%s; auth account rolled back.",
                validated_data["student_id"],
            )
            raise

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
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
    )



class OutboxEventSerializer(serializers.ModelSerializer):
    student_id = serializers.SerializerMethodField()

    class Meta:
        model = OutboxEvent
        fields = [
            'id', 'event_type', 'payload', 'student_id',
            'attempts', 'last_error', 'created_at', 'last_attempted_at',
        ]

    def get_student_id(self, obj):
        return obj.payload.get('student_id', '')
