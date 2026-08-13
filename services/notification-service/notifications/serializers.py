from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "type", "title", "body", "is_read", "created_at"]
        read_only_fields = fields


class InternalSendSerializer(serializers.Serializer):
    user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        min_length=1,
    )
    institution_id = serializers.UUIDField()
    type = serializers.ChoiceField(choices=[c[0] for c in Notification.NOTIFICATION_TYPES])
    title = serializers.CharField(max_length=255)
    body = serializers.CharField()
