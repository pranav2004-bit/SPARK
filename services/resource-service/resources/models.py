import uuid
from django.db import models


class UploadType(models.TextChoices):
    PDF = "pdf", "PDF"
    AUDIO = "audio", "Audio"
    VIDEO = "video", "Video"
    IMAGE = "image", "Image"
    VIDEO_LINK = "video_link", "Video Link"
    EXTERNAL_LINK = "external_link", "External Link"


# ── General study-material models (migrated from user-service) ─────────────────

class Module(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    institution_id = models.UUIDField(null=True, blank=True, db_index=True)
    is_published = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    parent = models.ForeignKey(
        "self",
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="children",
        db_index=True,
    )
    order = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "modules"
        ordering = ["order", "created_at"]
        indexes = [
            models.Index(fields=["order"], name="idx_modules_order"),
            models.Index(fields=["institution_id"], name="idx_modules_institution_id"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["institution_id"],
                condition=models.Q(is_system=True),
                nulls_distinct=False,
                name="unique_system_module_per_institution",
            ),
        ]

    def __str__(self):
        return self.name


class ModuleSection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="module_sections", db_index=True)
    name = models.CharField(max_length=200)
    is_published = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "module_sections"
        ordering = ["order", "created_at"]
        indexes = [
            models.Index(fields=["module"], name="idx_module_sections_module"),
        ]

    def __str__(self):
        return self.name


class ModuleUpload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(ModuleSection, on_delete=models.CASCADE, related_name="uploads", db_index=True)
    upload_type = models.CharField(max_length=20, choices=UploadType.choices)
    file_url = models.TextField()
    original_filename = models.CharField(max_length=500, blank=True, null=True)
    file_size_bytes = models.BigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "module_uploads"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["section"], name="idx_module_uploads_section"),
        ]

    def __str__(self):
        return f"{self.upload_type}: {self.original_filename or self.file_url[:50]}"


# ── Company-based placement-material models ────────────────────────────────────

class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_name = models.CharField(max_length=255)
    institution_id = models.UUIDField(null=True, blank=True, db_index=True)
    is_published = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "companies"
        ordering = ["-created_at"]
        unique_together = [("company_name", "institution_id")]
        indexes = [
            models.Index(fields=["is_published"], name="idx_companies_is_published"),
            models.Index(fields=["institution_id"], name="idx_companies_institution_id"),
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
