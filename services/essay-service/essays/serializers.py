from rest_framework import serializers
from .models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayAttempt,
    EssaySubmission, EssaySubmissionEvent, EssayLLMTrace,
)


class EssayPaperSerializer(serializers.ModelSerializer):
    set_count = serializers.SerializerMethodField()

    def get_set_count(self, obj):
        if hasattr(obj, "set_count"):
            return obj.set_count
        return obj.sets.count()

    class Meta:
        model = EssayPaper
        fields = [
            "id", "title", "description",
            "set_count", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class EssaySetSerializer(serializers.ModelSerializer):
    has_question = serializers.SerializerMethodField()

    def get_has_question(self, obj):
        # AdminPaperDetailView annotates this as a Count (an integer, not a
        # bool) for query efficiency — cast explicitly so the API always
        # returns a real boolean, not 0/1.
        if hasattr(obj, "has_question"):
            return bool(obj.has_question)
        return EssayQuestion.objects.filter(set=obj).exists()

    class Meta:
        model = EssaySet
        fields = ["id", "paper", "label", "order", "has_question"]
        read_only_fields = ["id"]


class EssayQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EssayQuestion
        fields = [
            "id", "set", "question_text", "llm_rubric_prompt",
            "word_limit", "time_limit_minutes", "max_score",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "set", "created_at", "updated_at"]

    def validate_question_text(self, value):
        if not value.strip():
            raise serializers.ValidationError("question_text cannot be empty.")
        return value

    def validate_llm_rubric_prompt(self, value):
        if not value.strip():
            raise serializers.ValidationError("llm_rubric_prompt cannot be empty.")
        return value


class EssayAssignmentSerializer(serializers.ModelSerializer):
    # Read-only convenience field, same free-JOIN pattern as
    # assessment-service's BatchAssignmentSerializer.paper_title (the view
    # select_related("paper")s, so this costs nothing extra).
    paper_title = serializers.CharField(source="paper.title", read_only=True)

    class Meta:
        model = EssayAssignment
        fields = [
            "id", "paper", "paper_title", "batch_id", "institution_id",
            "global_start_time", "global_expire_time", "departments",
            "status", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "institution_id", "status", "created_by", "created_at", "updated_at",
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


# ── Admin: Submissions Module (Phase 6, Task 6.1) ───────────────────────────

class EssaySubmissionEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = EssaySubmissionEvent
        # admin_user_id/reason added in Phase 7 (Task 7.1) — populated only
        # by the two admin-initiated event writers (retrigger, override);
        # blank/null for the two automatic pipeline writers from Phase 6.
        fields = ["id", "event_type", "detail", "worker_hostname", "task_id", "admin_user_id", "reason", "occurred_at"]
        read_only_fields = fields


class EssayLLMTraceSerializer(serializers.ModelSerializer):
    """Phase 7, Task 7.1's own "LLM trace/debug view" — the exact prompt,
    the raw response, the request id, and when it was evaluated."""
    class Meta:
        model = EssayLLMTrace
        fields = ["prompt_messages", "raw_response", "request_id", "model_used", "evaluated_at"]
        read_only_fields = fields


class EssaySubmissionListSerializer(serializers.ModelSerializer):
    """One row of the paginated submissions list (Task 6.1). Dotted
    `source=` reads, not SerializerMethodField, for every attempt/
    assignment-derived field — the view's own select_related() (matching
    every other list serializer in this file) makes these free joins, not
    N+1 queries."""
    student_id     = serializers.UUIDField(source="attempt.student_id", read_only=True)
    attempt_id     = serializers.UUIDField(source="attempt.id", read_only=True)
    assignment_id  = serializers.UUIDField(source="attempt.assignment.id", read_only=True)
    batch_id       = serializers.UUIDField(source="attempt.assignment.batch_id", read_only=True)
    paper_title    = serializers.CharField(source="attempt.assignment.paper.title", read_only=True)
    malpractice_flag = serializers.BooleanField(source="attempt.malpractice_flag", read_only=True)
    score = serializers.SerializerMethodField()

    def get_score(self, obj):
        # obj.score is EssayScore's own related_name — a real DB hit per
        # row unless the view's own queryset prefetches it (select_related
        # can't span a reverse OneToOne the same way, so the view uses
        # select_related("score") too, which Django DOES support for a
        # OneToOneField's reverse accessor).
        score = getattr(obj, "score", None)
        return score.score if score is not None else None

    class Meta:
        model = EssaySubmission
        fields = [
            "id", "status", "student_id", "attempt_id", "assignment_id",
            "batch_id", "paper_title", "malpractice_flag", "score",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class EssaySubmissionDetailSerializer(serializers.ModelSerializer):
    """Task 6.1's detail view: the essay itself (full, unredacted text —
    PII redaction (ADR 003 Decision 4) only ever applied to the outbound
    LLM call, never to what an authorized admin reviews here), the score/
    feedback breakdown if one exists, and the full chronological
    EssaySubmissionEvent trail (this task's own audit-log requirement)."""
    student_id      = serializers.UUIDField(source="attempt.student_id", read_only=True)
    attempt_id      = serializers.UUIDField(source="attempt.id", read_only=True)
    assignment_id   = serializers.UUIDField(source="attempt.assignment.id", read_only=True)
    batch_id        = serializers.UUIDField(source="attempt.assignment.batch_id", read_only=True)
    paper_title     = serializers.CharField(source="attempt.assignment.paper.title", read_only=True)
    question_text   = serializers.CharField(source="attempt.set.question.question_text", read_only=True)
    draft_response  = serializers.CharField(source="attempt.draft_response", read_only=True)
    malpractice_flag   = serializers.BooleanField(source="attempt.malpractice_flag", read_only=True)
    malpractice_reasons = serializers.ListField(source="attempt.malpractice_reasons", read_only=True)
    score    = serializers.SerializerMethodField()
    feedback = serializers.SerializerMethodField()
    # Phase 7, Task 7.1 — "visibly distinguishable from an LLM-assigned
    # score in every later view" (EssayScore.evaluated_by's own docstring).
    evaluated_by = serializers.SerializerMethodField()
    events   = EssaySubmissionEventSerializer(many=True, read_only=True)
    has_llm_trace = serializers.SerializerMethodField()

    def get_score(self, obj):
        score = getattr(obj, "score", None)
        return score.score if score is not None else None

    def get_feedback(self, obj):
        score = getattr(obj, "score", None)
        return score.feedback if score is not None else None

    def get_evaluated_by(self, obj):
        score = getattr(obj, "score", None)
        return score.evaluated_by if score is not None else None

    def get_has_llm_trace(self, obj):
        return hasattr(obj, "llm_trace")

    class Meta:
        model = EssaySubmission
        fields = [
            "id", "status", "student_id", "attempt_id", "assignment_id", "batch_id", "paper_title",
            "question_text", "draft_response", "malpractice_flag", "malpractice_reasons",
            "score", "feedback", "evaluated_by", "has_llm_trace", "events", "created_at", "updated_at",
        ]
        read_only_fields = fields


class StudentEssayQuestionSerializer(serializers.ModelSerializer):
    """Same as EssayQuestionSerializer but WITHOUT llm_rubric_prompt — this
    is what's served to a student during an attempt (Task 4.1/4.2). Leaking
    the rubric here would hand the student the exact criteria the LLM will
    grade against, the essay-writing equivalent of leaking is_correct to a
    student mid-exam in assessment-service."""
    class Meta:
        model = EssayQuestion
        fields = ["id", "question_text", "word_limit", "time_limit_minutes", "max_score"]
        read_only_fields = fields
