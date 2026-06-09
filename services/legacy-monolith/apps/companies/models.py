import uuid
from django.db import models


class UploadType(models.TextChoices):
    PDF = "pdf", "PDF"
    AUDIO = "audio", "Audio"
    VIDEO = "video", "Video"
    IMAGE = "image", "Image"
    VIDEO_LINK = "video_link", "Video Link"
    EXTERNAL_LINK = "external_link", "External Link"


class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_name = models.CharField(max_length=255, unique=True)
    is_published = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "companies"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_published"], name="idx_companies_is_published"),
        ]

    def __str__(self):
        return self.company_name


class Section(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="sections",
        db_index=True,
    )
    section_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sections"
        ordering = ["created_at"]
        unique_together = [("company", "section_name")]
        indexes = [
            models.Index(fields=["company"], name="idx_sections_company_id"),
        ]

    def __str__(self):
        return f"{self.company.company_name} — {self.section_name}"


class Upload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="uploads",
        db_index=True,
    )
    upload_type = models.CharField(max_length=20, choices=UploadType.choices)
    file_url = models.TextField()
    original_filename = models.CharField(max_length=500, blank=True, null=True)
    file_size_bytes = models.BigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "uploads"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["section"], name="idx_uploads_section_id"),
            models.Index(fields=["upload_type"], name="idx_uploads_upload_type"),
        ]

    def __str__(self):
        return f"{self.upload_type}: {self.original_filename or self.file_url[:50]}"
