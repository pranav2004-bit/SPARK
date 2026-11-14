from rest_framework import serializers
from core.storage import get_cdn_url
from .models import QuestionPaper, QuestionSet, QuestionSection, Question, QuestionOption, BatchAssignment


class QuestionPaperSerializer(serializers.ModelSerializer):
    set_count = serializers.SerializerMethodField()

    def get_set_count(self, obj):
        # Once content is deleted (2026-11-13) the real sets are gone —
        # obj.sets.count() (or an annotated set_count) would read 0, which
        # would silently violate "the number of sets must keep displaying
        # after the paper is deleted." deleted_set_count is the frozen
        # pre-deletion value, saved for exactly this.
        if obj.is_deleted:
            return obj.deleted_set_count or 0
        if hasattr(obj, "set_count"):
            return obj.set_count
        return obj.sets.count()

    class Meta:
        model = QuestionPaper
        fields = [
            "id", "title", "description", "instructions",
            "set_count", "created_by", "created_at", "updated_at",
            "is_deleted", "deleted_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at", "is_deleted", "deleted_at"]


class QuestionSetSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()
    total_marks = serializers.SerializerMethodField()
    section_count = serializers.SerializerMethodField()

    def get_question_count(self, obj):
        if hasattr(obj, "question_count"):
            return obj.question_count
        return obj.questions.count()

    def get_total_marks(self, obj):
        return obj.total_marks()

    def get_section_count(self, obj):
        if hasattr(obj, "section_count"):
            return obj.section_count
        return obj.sections.count()

    class Meta:
        model = QuestionSet
        fields = ["id", "paper", "label", "order", "question_count", "total_marks", "section_count"]
        read_only_fields = ["id"]


class QuestionSectionSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()

    def get_question_count(self, obj):
        return obj.questions.count()

    class Meta:
        model = QuestionSection
        fields = ["id", "set", "title", "order", "question_count"]
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
            "id", "set", "section", "question_number", "question_type", "mcq_type",
            "question_content_type", "question_text",
            "question_image_key", "question_image_url",
            "question_image_size_bytes", "marks",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "question_number", "question_image_url",
            "question_image_size_bytes", "created_at", "updated_at",
        ]
        extra_kwargs = {
            # Callers that don't pass a section fall back to Question.save()'s
            # auto-default-section-per-set behaviour (see models.py) rather
            # than being rejected here — keeps the older set-level creation
            # endpoint working unchanged.
            "section": {"required": False},
        }


class StudentQuestionOptionSerializer(serializers.ModelSerializer):
    """Same as QuestionOptionSerializer but WITHOUT is_correct — this is
    what's served to a student mid-exam (Task 5.4). Leaking is_correct here
    would hand the student the answer key over the network.

    label/order are SerializerMethodFields, not direct model fields: when
    the caller has shuffled this option's display position (assessments.
    shuffling.shuffle_options), it stamps a transient display_label/
    display_order attribute on the instance, and that — not the admin's
    own stored label/order — is what gets sent here. Without this, a
    shuffled option would still show its ORIGINAL letter out of sequence
    (e.g. "C, A, D, B" top to bottom), which looks broken to a student
    even though it's functionally harmless (submission is always by id).
    Falls back to the stored value when nothing shuffled it (unused by
    any current caller, but keeps this serializer correct standalone)."""
    image_url = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()
    order = serializers.SerializerMethodField()

    def get_image_url(self, obj):
        if obj.image_key:
            return get_cdn_url(obj.image_key)
        return None

    def get_label(self, obj):
        return getattr(obj, "display_label", obj.label)

    def get_order(self, obj):
        return getattr(obj, "display_order", obj.order)

    class Meta:
        model = QuestionOption
        fields = ["id", "label", "content_type", "text", "image_key", "image_url", "order"]
        read_only_fields = fields


class StudentQuestionSerializer(serializers.ModelSerializer):
    """Same as QuestionSerializer but nests StudentQuestionOptionSerializer
    (no is_correct) instead of the admin one.

    options/question_number are SerializerMethodFields rather than a plain
    nested serializer/model field, for the same reason as
    StudentQuestionOptionSerializer above: the caller shuffles each
    question's options and the whole set's question order per student
    (assessments.shuffling), stamping transient display_question_number /
    _shuffled_options attributes on each instance. get_options reads the
    shuffled list directly instead of the model's own .options.all()
    (which would just return the admin's original order via Meta.ordering,
    silently undoing the shuffle) — falling back to the real relation only
    if nothing shuffled it. get_question_number renumbers 1..N over the
    final (section-grouped, shuffled-within-section) display order, so the
    navigator always shows a clean sequential count regardless of which
    question the admin originally numbered what."""
    question_image_url = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()
    question_number = serializers.SerializerMethodField()
    # section_id comes straight off the model's own FK column (no explicit
    # field needed for that one); section_title needs one since it isn't a
    # direct column. Added so the exam-taking UI can group its question
    # navigator by section instead of just a flat number list.
    section_title = serializers.CharField(source="section.title", read_only=True)

    def get_question_image_url(self, obj):
        if obj.question_image_key:
            return get_cdn_url(obj.question_image_key)
        return None

    def get_options(self, obj):
        options = getattr(obj, "_shuffled_options", None)
        if options is None:
            options = list(obj.options.all())
        return StudentQuestionOptionSerializer(options, many=True).data

    def get_question_number(self, obj):
        return getattr(obj, "display_question_number", obj.question_number)

    class Meta:
        model = Question
        fields = [
            "id", "question_number", "mcq_type", "question_content_type",
            "question_text", "question_image_url", "marks", "options",
            "section_id", "section_title",
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
            "pass_cutoff_percentage", "show_result_to_student", "results_published_at",
            "department_sections", "status", "created_by",
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
            # results_published_at is only ever written by
            # AdminAssignmentPublishResultsView, directly on the model —
            # never client-settable (an admin can't pre-date when they
            # "published" something).
            "results_published_at",
            "created_by", "created_at", "updated_at",
        ]

    def validate_department_sections(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "department_sections must be a list of {department, sections} objects."
            )
        cleaned = []
        for entry in value:
            if not isinstance(entry, dict):
                raise serializers.ValidationError(
                    "Each department_sections entry must be an object with 'department' and optional 'sections'."
                )
            department = entry.get("department")
            if not isinstance(department, str) or not department.strip():
                raise serializers.ValidationError("Each department_sections entry needs a non-empty 'department'.")
            sections = entry.get("sections") or []
            if not isinstance(sections, list) or not all(isinstance(s, str) and s.strip() for s in sections):
                raise serializers.ValidationError("'sections' must be a list of section names.")
            cleaned.append({"department": department.strip(), "sections": [s.strip() for s in sections]})
        return cleaned

    def validate(self, attrs):
        expire = attrs.get("global_expire_time")
        start = attrs.get("global_start_time") or (self.instance.global_start_time if self.instance else None)
        if expire and start and expire <= start:
            raise serializers.ValidationError(
                {"global_expire_time": "Must be after global_start_time."}
            )
        return attrs
