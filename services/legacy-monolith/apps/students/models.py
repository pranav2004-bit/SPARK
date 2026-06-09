import uuid
from django.db import models
from apps.authentication.models import User
from apps.batches.models import Batch


# ── Scroll Updates ────────────────────────────────────────────────────────────

class ScrollConfig(models.Model):
    """
    Singleton that governs the student-facing scrolling updates bar.
    Enforce singleton by always using pk=1.
    """
    DIRECTION_CHOICES = [
        ("left", "Left (RTL marquee)"),
        ("right", "Right (LTR marquee)"),
    ]

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    is_enabled = models.BooleanField(default=False)
    direction = models.CharField(max_length=5, choices=DIRECTION_CHOICES, default="left")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "scroll_config"

    def save(self, *args, **kwargs):
        # Enforce singleton — pk is always 1
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"ScrollConfig (enabled={self.is_enabled}, direction={self.direction})"


class ScrollUpdate(models.Model):
    """
    A single item that appears in the student-facing scrolling bar.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    text = models.CharField(max_length=300)
    link = models.CharField(max_length=500, blank=True, default="")
    show_new_badge = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "scroll_updates"
        ordering = ["order", "created_at"]
        indexes = [
            models.Index(fields=["order"], name="idx_scroll_updates_order"),
        ]

    def __str__(self):
        return self.text[:60]


# ── Resource Modules ─────────────────────────────────────────────────────────

class ResourceModule(models.Model):
    """
    Admin-managed placement resource modules shown in the Resources hub.
    is_system=True  → Company Resources (cannot be deleted, always present).
    is_system=False → Admin-created dynamic modules.
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name         = models.CharField(max_length=200)
    is_published = models.BooleanField(default=False)
    is_system    = models.BooleanField(default=False)
    parent       = models.ForeignKey(
        "self",
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="children",
        db_index=True,
    )
    order        = models.PositiveIntegerField(default=0, db_index=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "resource_modules"
        ordering = ["order", "created_at"]
        indexes  = [models.Index(fields=["order"], name="idx_resource_modules_order")]

    def __str__(self):
        return self.name


class ResourceSection(models.Model):
    """A section inside a dynamic resource module — leads to file uploads."""
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module       = models.ForeignKey(ResourceModule, on_delete=models.CASCADE, related_name="sections", db_index=True)
    name         = models.CharField(max_length=200)
    is_published = models.BooleanField(default=False)
    order        = models.PositiveIntegerField(default=0, db_index=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "resource_sections"
        ordering = ["order", "created_at"]
        indexes  = [models.Index(fields=["module"], name="idx_resource_sections_module")]

    def __str__(self):
        return self.name


RESOURCE_UPLOAD_TYPE_CHOICES = [
    ("pdf",           "PDF"),
    ("audio",         "Audio"),
    ("video",         "Video"),
    ("image",         "Image"),
    ("video_link",    "Video Link"),
    ("external_link", "External Link"),
]


class ResourceUpload(models.Model):
    """A file or link uploaded to a resource section."""
    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource_section  = models.ForeignKey(ResourceSection, on_delete=models.CASCADE, related_name="uploads", db_index=True)
    upload_type       = models.CharField(max_length=20, choices=RESOURCE_UPLOAD_TYPE_CHOICES)
    file_url          = models.TextField()
    original_filename = models.CharField(max_length=500, blank=True, null=True)
    file_size_bytes   = models.BigIntegerField(blank=True, null=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "resource_uploads"
        ordering = ["created_at"]
        indexes  = [models.Index(fields=["resource_section"], name="idx_resource_uploads_section")]

    def __str__(self):
        return f"{self.upload_type}: {self.original_filename or self.file_url[:50]}"


class Student(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student_id = models.CharField(max_length=100, unique=True, db_index=True)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    fullname = models.CharField(max_length=255, blank=True, null=True)
    college_email_id = models.EmailField(blank=True, null=True)
    department = models.CharField(max_length=255)
    batch = models.ForeignKey(
        Batch,
        on_delete=models.PROTECT,
        related_name="students",
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    is_profile_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "students"
        indexes = [
            models.Index(fields=["student_id"], name="idx_students_student_id"),
            models.Index(fields=["batch"], name="idx_students_batch_id"),
            models.Index(fields=["department"], name="idx_students_department"),
            models.Index(fields=["is_active"], name="idx_students_is_active"),
        ]

    def __str__(self):
        return self.student_id


class Inquiry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="inquiries",
        db_index=True,
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "student_inquiries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_read"], name="idx_inquiries_is_read"),
            models.Index(fields=["student"], name="idx_inquiries_student"),
        ]

    def __str__(self):
        return f"Inquiry from {self.student.student_id} at {self.created_at:%Y-%m-%d}"
