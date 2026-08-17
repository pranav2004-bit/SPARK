from rest_framework import serializers
from core.storage import get_cdn_url
from .models import QuestionPaper, QuestionSet, Question, QuestionOption, BatchAssignment


class QuestionPaperSerializer(serializers.ModelSerializer):
    set_count = serializers.SerializerMethodField()

    def get_set_count(self, obj):
        if hasattr(obj, "set_count"):
            return obj.set_count
        return obj.sets.count()

    class Meta:
        model = QuestionPaper
        fields = [
            "id", "title", "description", "instructions",
            "set_count", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class QuestionSetSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()
    total_marks = serializers.SerializerMethodField()

    def get_question_count(self, obj):
        if hasattr(obj, "question_count"):
            return obj.question_count
        return obj.questions.count()

    def get_total_marks(self, obj):
        return obj.total_marks()

    class Meta:
        model = QuestionSet
        fields = ["id", "paper", "label", "order", "question_count", "total_marks"]
        read_only_fields = ["id"]


class QuestionOptionSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    def get_image_url(self, obj):
        if obj.image_key:
            return get_cdn_url(obj.image_key)
        return None

    class Meta:
        model = QuestionOption
        fields = [
            "id", "question", "label", "content_type", "text",
            "image_key", "image_url", "is_correct", "order",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class QuestionSerializer(serializers.ModelSerializer):
    question_image_url = serializers.SerializerMethodField()

    def get_question_image_url(self, obj):
        if obj.question_image_key:
            return get_cdn_url(obj.question_image_key)
        return None

    class Meta:
        model = Question
        fields = [
            "id", "set", "question_number", "question_type", "mcq_type",
            "question_content_type", "question_text",
            "question_image_key", "question_image_url",
            "question_image_size_bytes", "marks",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "question_number", "question_image_url",
            "question_image_size_bytes", "created_at", "updated_at",
        ]


class StudentQuestionOptionSerializer(serializers.ModelSerializer):
    """Same as QuestionOptionSerializer but WITHOUT is_correct — this is
    what's served to a student mid-exam (Task 5.4). Leaking is_correct here
    would hand the student the answer key over the network."""
    image_url = serializers.SerializerMethodField()

    def get_image_url(self, obj):
        if obj.image_key:
            return get_cdn_url(obj.image_key)
        return None

    class Meta:
        model = QuestionOption
        fields = ["id", "label", "content_type", "text", "image_key", "image_url", "order"]
        read_only_fields = fields


class StudentQuestionSerializer(serializers.ModelSerializer):
    """Same as QuestionSerializer but nests StudentQuestionOptionSerializer
    (no is_correct) instead of the admin one."""
    question_image_url = serializers.SerializerMethodField()
    options = StudentQuestionOptionSerializer(many=True, read_only=True)

    def get_question_image_url(self, obj):
        if obj.question_image_key:
            return get_cdn_url(obj.question_image_key)
        return None

    class Meta:
        model = Question
        fields = [
            "id", "question_number", "mcq_type", "question_content_type",
            "question_text", "question_image_url", "marks", "options",
        ]
        read_only_fields = fields


class BatchAssignmentSerializer(serializers.ModelSerializer):
    # Additive, read-only — the frontend's new admin/assessments/assignments/
    # list page needs a human-readable label per row, and "paper" itself only
    # ever serializes to the FK's raw UUID. select_related("paper") in the
    # view (AdminAssignmentListCreateView.get) makes this free — no N+1.
    paper_title = serializers.CharField(source="paper.title", read_only=True)

    class Meta:
        model = BatchAssignment
        fields = [
            "id", "paper", "paper_title", "batch_id", "institution_id",
            "global_start_time", "global_expire_time", "exam_duration_minutes",
            "pass_cutoff_percentage", "show_result_to_student", "departments", "status", "created_by",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            # global_start_time is writable here — an admin may pre-schedule
            # it at creation (Task 3.3's "global start/expire time pickers");
            # once created, nothing else lets a client PATCH it directly —
            # only AdminAssignmentStartView's start/ action can move it, and
            # that view writes to the model directly rather than through
            # this serializer.
            "id", "institution_id", "status",
            "created_by", "created_at", "updated_at",
        ]

    def validate_departments(self, value):
        if not isinstance(value, list) or not all(isinstance(d, str) and d.strip() for d in value):
            raise serializers.ValidationError("departments must be a list of department names.")
        return [d.strip() for d in value]

    def validate(self, attrs):
        expire = attrs.get("global_expire_time")
        start = attrs.get("global_start_time") or (self.instance.global_start_time if self.instance else None)
        if expire and start and expire <= start:
            raise serializers.ValidationError(
                {"global_expire_time": "Must be after global_start_time."}
            )
        return attrs
