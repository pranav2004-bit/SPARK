from rest_framework import serializers
from .models import Company, Section, Upload, Module, ModuleSection, ModuleUpload
from core.upload_constraints import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES, MAX_FILE_SIZES


# ── General module serializers ─────────────────────────────────────────────────

class ModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ["id", "name", "is_published", "is_system", "order", "created_at", "updated_at"]
        read_only_fields = ["id", "is_system", "order", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Module name cannot be empty.")
        return value


class ModuleSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModuleSection
        fields = ["id", "module_id", "name", "is_published", "order", "created_at", "updated_at"]
        read_only_fields = ["id", "module_id", "order", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Section name cannot be empty.")
        return value


class ModuleUploadSerializer(serializers.ModelSerializer):
    read_url = serializers.SerializerMethodField()

    class Meta:
        model = ModuleUpload
        fields = [
            "id", "section_id", "upload_type",
            "file_url", "read_url", "original_filename",
            "file_size_bytes", "scan_status", "created_at",
        ]
        read_only_fields = ["id", "section_id", "read_url", "scan_status", "created_at"]

    def get_read_url(self, obj):
        from core.storage import get_cdn_url, is_file_type
        if is_file_type(obj.upload_type):
            return get_cdn_url(obj.file_url)
        return obj.file_url


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
        institution_id = self.context.get("institution_id")
        qs = Company.objects.filter(company_name__iexact=value, institution_id=institution_id)
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
        if company:
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
            "file_size_bytes", "scan_status", "read_url", "created_at",
        ]
        read_only_fields = ["id", "created_at", "read_url", "scan_status"]

    def get_read_url(self, obj):
        from core.storage import get_cdn_url, is_file_type
        if is_file_type(obj.upload_type):
            return get_cdn_url(obj.file_url)
        return obj.file_url


class PresignedUploadRequestSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=500)
    content_type = serializers.CharField(max_length=100)
    upload_type = serializers.ChoiceField(choices=["pdf", "audio", "video", "image"])

    def validate(self, attrs):
        import os
        filename = attrs["filename"]
        content_type = attrs["content_type"]
        upload_type = attrs["upload_type"]

        ext = os.path.splitext(filename)[1].lower()
        allowed_ext = ALLOWED_EXTENSIONS.get(upload_type, [])
        if ext not in allowed_ext:
            raise serializers.ValidationError(
                {"filename": f"Extension '{ext}' not allowed for '{upload_type}'. Allowed: {allowed_ext}"}
            )

        allowed_mime = ALLOWED_MIME_TYPES.get(upload_type, [])
        if content_type not in allowed_mime:
            raise serializers.ValidationError(
                {"content_type": f"Content type '{content_type}' not allowed for '{upload_type}'. Allowed: {allowed_mime}"}
            )
        return attrs


class ConfirmUploadSerializer(serializers.Serializer):
    file_key = serializers.CharField(max_length=1000)
    original_filename = serializers.CharField(max_length=500)
    # Client-reported size — used only as a cheap early rejection before the
    # real HEAD-based check against storage (see views.py). Never trusted as
    # the final file_size_bytes value stored on the record.
    file_size_bytes = serializers.IntegerField(min_value=1)
    upload_type = serializers.ChoiceField(choices=["pdf", "audio", "video", "image"])

    def validate(self, attrs):
        upload_type = attrs["upload_type"]
        max_size = MAX_FILE_SIZES.get(upload_type)
        if max_size and attrs["file_size_bytes"] > max_size:
            raise serializers.ValidationError(
                {"file_size_bytes": f"File exceeds the {max_size // (1024*1024)} MB limit for '{upload_type}'."}
            )
        return attrs


class AddLinkSerializer(serializers.Serializer):
    upload_type = serializers.ChoiceField(choices=["video_link", "external_link"])
    file_url = serializers.URLField(max_length=2000)
