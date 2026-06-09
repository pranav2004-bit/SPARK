from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=1)

    def validate_email(self, value):
        return value.lower().strip()


class StudentLoginSerializer(serializers.Serializer):
    student_id = serializers.CharField(min_length=1, max_length=100)
    password = serializers.CharField(write_only=True, min_length=1)

    def validate_student_id(self, value):
        return value.strip()


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()
