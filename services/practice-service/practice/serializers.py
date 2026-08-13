from rest_framework import serializers
from core.storage import get_cdn_url
from .models import PracticeModule, PracticeSection, PracticeQuestion, PracticeQuestionOption


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
        if hasattr(obj, "question_count"):
            return obj.question_count
        return obj.questions.count()

    class Meta:
        model  = PracticeSection
        fields = [
            "id", "name", "module", "is_published",
            "order", "question_count", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PracticeQuestionOptionAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PracticeQuestionOption
        fields = [
            "id", "question", "label", "text",
            "is_correct", "order", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PracticeQuestionOptionStudentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PracticeQuestionOption
        fields = ["id", "label", "text", "order"]


class PracticeQuestionSerializer(serializers.ModelSerializer):
    question_image_url    = serializers.SerializerMethodField()
    explanation_image_url = serializers.SerializerMethodField()

    def get_question_image_url(self, obj):
        if obj.question_image_key:
            return get_cdn_url(obj.question_image_key)
        return None

    def get_explanation_image_url(self, obj):
        if obj.explanation_image_key:
            return get_cdn_url(obj.explanation_image_key)
        return None

    class Meta:
        model  = PracticeQuestion
        fields = [
            "id", "section", "question_number", "title", "question_type",
            "mcq_type",
            "question_content_type",
            "question_text", "question_image_key", "question_image_url",
            "question_image_size_bytes",
            "fib_answer",
            "explanation_type", "explanation_text",
            "explanation_image_key", "explanation_image_url",
            "explanation_image_size_bytes",
            "is_published", "order", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "question_number",
            "question_image_url",
            "question_image_size_bytes",
            "explanation_image_url",
            "explanation_image_size_bytes",
            "created_at", "updated_at",
        ]


class StudentPracticeQuestionSerializer(PracticeQuestionSerializer):
    """
    Student-facing read serializer — identical to PracticeQuestionSerializer
    but with fib_answer excluded at the serializer level so no view can
    accidentally expose it via a forgotten pop().
    """
    class Meta(PracticeQuestionSerializer.Meta):
        fields = [f for f in PracticeQuestionSerializer.Meta.fields if f != "fib_answer"]
        read_only_fields = PracticeQuestionSerializer.Meta.read_only_fields
