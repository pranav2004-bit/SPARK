from rest_framework import serializers
from .models import Company, Section, Upload


class CompanySerializer(serializers.ModelSerializer):
    section_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Company
        fields = ["id", "company_name", "is_published", "section_count", "created_at", "updated_at"]
        read_only_fields = ["id", "is_published", "section_count", "created_at", "updated_at"]

    def validate_company_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Company name cannot be empty.")
        qs = Company.objects.filter(company_name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A company with this name already exists.")
        return value


class SectionSerializer(serializers.ModelSerializer):
    upload_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Section
        fields = ["id", "section_name", "company_id", "upload_count", "created_at", "updated_at"]
        read_only_fields = ["id", "company_id", "upload_count", "created_at", "updated_at"]

    def validate_section_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Section name cannot be empty.")
        return value

    def validate(self, attrs):
        section_name = attrs.get("section_name", "")
        company = self.context.get("company")
        qs = Section.objects.filter(company=company, section_name__iexact=section_name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"section_name": "A section with this name already exists in this company."}
            )
        return attrs


class UploadSerializer(serializers.ModelSerializer):
    read_url = serializers.SerializerMethodField()

    class Meta:
        model = Upload
        fields = [
            "id", "upload_type", "file_url", "original_filename",
            "file_size_bytes", "read_url", "created_at",
        ]
        read_only_fields = ["id", "created_at", "read_url"]

    def get_read_url(self, obj):
        from core.storage import get_cdn_url, is_file_type
        if is_file_type(obj.upload_type):
            return get_cdn_url(obj.file_url)
        return obj.file_url


class PresignedUploadRequestSerializer(serializers.Serializer):
    """
    Step 1 of the upload flow.
    Validates the file metadata before generating a presigned PUT URL.
    """
    filename = serializers.CharField(max_length=500)
    content_type = serializers.CharField(max_length=100)
    upload_type = serializers.ChoiceField(choices=["pdf", "audio", "video", "image"])

    ALLOWED_EXTENSIONS = {
        "pdf": [".pdf"],
        "audio": [".mp3", ".wav", ".ogg", ".m4a", ".aac"],
        "video": [".mp4", ".mov", ".avi", ".mkv", ".webm"],
        "image": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"],
    }

    def validate(self, attrs):
        import os
        filename = attrs["filename"]
        upload_type = attrs["upload_type"]
        ext = os.path.splitext(filename)[1].lower()
        allowed = self.ALLOWED_EXTENSIONS.get(upload_type, [])
        if ext not in allowed:
            raise serializers.ValidationError(
                {"filename": f"File extension '{ext}' is not allowed for upload type '{upload_type}'. Allowed: {allowed}"}
            )
        return attrs


class ConfirmUploadSerializer(serializers.Serializer):
    """
    Step 2 of the upload flow.
    Called after the browser has successfully PUT the file to R2.
    Creates the Upload database record.
    """
    file_key = serializers.CharField(max_length=1000)
    original_filename = serializers.CharField(max_length=500)
    file_size_bytes = serializers.IntegerField(min_value=1)
    upload_type = serializers.ChoiceField(choices=["pdf", "audio", "video", "image"])


class AddLinkSerializer(serializers.Serializer):
    upload_type = serializers.ChoiceField(choices=["video_link", "external_link"])
    file_url = serializers.URLField(max_length=2000)
