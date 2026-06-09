from rest_framework import serializers
from .models import Batch


class BatchSerializer(serializers.ModelSerializer):
    student_count = serializers.IntegerField(read_only=True)

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
        instance = self.instance
        qs = Batch.objects.filter(batch_name__iexact=batch_name)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"batch_name": "A batch with this name already exists."})
        return attrs
