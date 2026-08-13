from rest_framework import serializers
from .models import PracticeEvent, ResourceViewEvent


class InternalEventSerializer(serializers.Serializer):
    EVENT_TYPES = [
        ("practice_attempt", "Practice Attempt"),
        ("resource_view", "Resource View"),
    ]

    event_type = serializers.ChoiceField(choices=[e[0] for e in EVENT_TYPES])
    student_id = serializers.UUIDField()
    institution_id = serializers.UUIDField()
    # practice_attempt fields
    module_id = serializers.UUIDField(required=False)
    question_id = serializers.UUIDField(required=False)
    topic = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    difficulty = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    is_correct = serializers.BooleanField(required=False)
    # resource_view fields
    company_id = serializers.UUIDField(required=False)
    resource_id = serializers.UUIDField(required=False)

    def validate(self, data):
        event_type = data.get("event_type")
        if event_type == "practice_attempt":
            if not data.get("module_id"):
                raise serializers.ValidationError("module_id is required for practice_attempt.")
            if not data.get("question_id"):
                raise serializers.ValidationError("question_id is required for practice_attempt.")
            if "is_correct" not in data:
                raise serializers.ValidationError("is_correct is required for practice_attempt.")
        elif event_type == "resource_view":
            if not data.get("company_id"):
                raise serializers.ValidationError("company_id is required for resource_view.")
            if not data.get("resource_id"):
                raise serializers.ValidationError("resource_id is required for resource_view.")
        return data
