from rest_framework import serializers
from .models import PracticeModule, PracticeSection, PracticeQuestion, PracticeQuestionOption
from core.storage import get_cdn_url


class PracticeModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PracticeModule
        fields = [
            "id", "name", "parent", "is_published",
            "order", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PracticeSectionSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()

    def get_question_count(self, obj):
        return obj.questions.count()

    class Meta:
        model  = PracticeSection
        fields = [
            "id", "name", "module", "is_published",
            "order", "question_count", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# ── MCQ Option serializers ────────────────────────────────────────────────────

class PracticeQuestionOptionAdminSerializer(serializers.ModelSerializer):
    """Full option serializer for admin — exposes is_correct."""
    class Meta:
        model  = PracticeQuestionOption
        fields = [
            "id", "question", "label", "text",
            "is_correct", "order", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PracticeQuestionOptionStudentSerializer(serializers.ModelSerializer):
    """Student option serializer — never exposes is_correct."""
    class Meta:
        model  = PracticeQuestionOption
        fields = ["id", "label", "text", "order"]


# ── Question serializer ───────────────────────────────────────────────────────

class PracticeQuestionSerializer(serializers.ModelSerializer):
    question_image_url    = serializers.SerializerMethodField()
    explanation_image_url = serializers.SerializerMethodField()

    def get_question_image_url(self, obj):
        """Return the CDN URL for the question body image, or None if not set."""
        if obj.question_image_key:
            return get_cdn_url(obj.question_image_key)
        return None

    def get_explanation_image_url(self, obj):
        """Return the CDN URL for the explanation image, or None if not set."""
        if obj.explanation_image_key:
            return get_cdn_url(obj.explanation_image_key)
        return None

    class Meta:
        model  = PracticeQuestion
        fields = [
            "id", "section", "question_number", "title", "question_type",
            # MCQ sub-type
            "mcq_type",
            # Question body
            "question_content_type",
            "question_text", "question_image_key", "question_image_url",
            # FIB answer (admin-only field — student views must strip this)
            "fib_answer",
            # Explanation
            "explanation_type", "explanation_text",
            "explanation_image_key", "explanation_image_url",
            # Meta
            "is_published", "order", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "question_number",
            "question_image_url",
            "explanation_image_url",
            "created_at", "updated_at",
        ]
