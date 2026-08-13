import uuid
from django.db import models


class PracticeEvent(models.Model):
    """Raw practice attempt event ingested from practice-service."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student_id = models.UUIDField(db_index=True)
    institution_id = models.UUIDField(db_index=True)
    module_id = models.UUIDField()
    question_id = models.UUIDField()
    topic = models.CharField(max_length=255, blank=True, default="")
    difficulty = models.CharField(max_length=20, blank=True, default="")
    is_correct = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["institution_id", "created_at"], name="pe_institution_created_idx"),
            models.Index(fields=["student_id", "topic"], name="pe_student_topic_idx"),
        ]
        # Partition key hint for future month-based partitioning (V2)


class ResourceViewEvent(models.Model):
    """Raw resource view event ingested from resource-service."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student_id = models.UUIDField(db_index=True)
    institution_id = models.UUIDField(db_index=True)
    company_id = models.UUIDField()
    resource_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["institution_id", "company_id"], name="rve_institution_company_idx"),
        ]


class DailyEngagementSnapshot(models.Model):
    """Pre-computed daily engagement per student — written by nightly Celery beat task."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student_id = models.UUIDField(db_index=True)
    institution_id = models.UUIDField(db_index=True)
    department = models.CharField(max_length=255, blank=True, default="")
    batch_id = models.UUIDField(null=True, blank=True)
    practice_attempts = models.PositiveIntegerField(default=0)
    correct_attempts = models.PositiveIntegerField(default=0)
    resource_views = models.PositiveIntegerField(default=0)
    snapshot_date = models.DateField(db_index=True)

    class Meta:
        unique_together = [("student_id", "snapshot_date")]
        indexes = [
            models.Index(fields=["institution_id", "snapshot_date"], name="des_institution_date_idx"),
        ]


class InstitutionSnapshot(models.Model):
    """Pre-computed daily institution-level KPIs — written by nightly Celery beat task."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_id = models.UUIDField(db_index=True)
    total_students = models.PositiveIntegerField(default=0)
    total_active = models.PositiveIntegerField(default=0)
    practice_completion_rate = models.FloatField(default=0.0)
    resource_utilization_rate = models.FloatField(default=0.0)
    snapshot_date = models.DateField(db_index=True)

    class Meta:
        unique_together = [("institution_id", "snapshot_date")]
        indexes = [
            models.Index(fields=["institution_id", "snapshot_date"], name="is_institution_date_idx"),
        ]
