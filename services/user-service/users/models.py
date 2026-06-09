import uuid
from django.db import models
from django.utils import timezone


class Batch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch_name = models.CharField(max_length=255, unique=True)
    institution_id = models.UUIDField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "batches"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["institution_id"], name="idx_batches_institution_id"),
        ]

    def __str__(self):
        return self.batch_name


class Student(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(unique=True, db_index=True)
    student_id = models.CharField(max_length=100, unique=True, db_index=True)
    institution_id = models.UUIDField(null=True, blank=True, db_index=True)
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
            models.Index(fields=["institution_id"], name="idx_students_institution_id"),
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


class ScrollConfig(models.Model):
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
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"ScrollConfig (enabled={self.is_enabled}, direction={self.direction})"


class ScrollUpdate(models.Model):
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


class OutboxEvent(models.Model):
    """
    Transactional outbox for cross-service operations.

    Written in the SAME database transaction as the triggering operation so the
    intent can never be lost due to a network failure between services.  A
    background worker (run_outbox_worker) polls this table and delivers each
    event to the target service with retries and exponential backoff.

    Payload schema (version 1):
        {
            "version": 1,
            "student_id": "<student ID string>",
            "user_id":    "<UUID of the auth User to delete>"
        }
    Including user_id prevents the worker from deleting a newly re-created auth
    account when the old student was deleted and immediately re-added.
    """

    class EventType(models.TextChoices):
        DELETE_STUDENT_AUTH = 'delete_student_auth', 'Delete Student Auth'

    class Status(models.TextChoices):
        PENDING     = 'pending',     'Pending'
        PROCESSING  = 'processing',  'Processing'
        DONE        = 'done',        'Done'
        DEAD_LETTER = 'dead_letter', 'Dead Letter'

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type       = models.CharField(max_length=100, choices=EventType.choices)
    payload          = models.JSONField()
    status           = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts         = models.PositiveSmallIntegerField(default=0)
    retry_after      = models.DateTimeField(null=True, blank=True)
    last_error       = models.TextField(blank=True, default='')
    created_at       = models.DateTimeField(auto_now_add=True)
    processed_at     = models.DateTimeField(null=True, blank=True)
    last_attempted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'outbox_events'
        indexes = [
            models.Index(
                fields=['status', 'retry_after', 'created_at'],
                name='idx_outbox_worker_query',
            ),
        ]

    def __str__(self):
        return f"OutboxEvent({self.event_type}, {self.status}, {self.id})"
