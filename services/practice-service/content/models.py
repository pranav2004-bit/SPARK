import uuid

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

NODE_DRAFT = "draft"
NODE_PUBLISHED = "published"
NODE_RETIRED = "retired"
NODE_STATUSES = [NODE_DRAFT, NODE_PUBLISHED, NODE_RETIRED]

QUESTION_DRAFT = "draft"
QUESTION_PUBLISHED = "published"
QUESTION_RETIRED = "retired"
QUESTION_STATUSES = [QUESTION_DRAFT, QUESTION_PUBLISHED, QUESTION_RETIRED]

VERSION_DRAFT = "draft"
VERSION_IN_REVIEW = "in_review"
VERSION_PUBLISHED = "published"
VERSION_STATES = [VERSION_DRAFT, VERSION_IN_REVIEW, VERSION_PUBLISHED]
OPEN_VERSION_STATES = [VERSION_DRAFT, VERSION_IN_REVIEW]

AUDIT_ENTITY_NODE = "node"
AUDIT_ENTITY_QUESTION = "question"
AUDIT_ENTITY_VERSION = "version"


class ContentNode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_id = models.UUIDField(db_index=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children", db_index=True,
    )
    name = models.CharField(max_length=200)
    display_order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=[(s, s) for s in NODE_STATUSES], default=NODE_DRAFT)
    created_by = models.UUIDField()
    updated_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "content_node"
        ordering = ["display_order", "created_at"]
        indexes = [
            models.Index(fields=["institution_id", "parent", "display_order"], name="content_node_tree_idx"),
            models.Index(fields=["institution_id", "status"], name="content_node_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "institution_id", "parent",
                condition=Q(parent__isnull=False),
                name="content_node_unique_name_under_parent",
            ),
        ]


class ContentQuestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_id = models.UUIDField(db_index=True)
    node = models.ForeignKey(ContentNode, on_delete=models.PROTECT, related_name="questions")
    display_order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=[(s, s) for s in QUESTION_STATUSES], default=QUESTION_DRAFT)
    current_version_no = models.PositiveIntegerField(default=1)
    published_version_no = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.UUIDField()
    updated_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "content_question"
        ordering = ["display_order", "created_at"]
        indexes = [
            models.Index(fields=["institution_id", "node", "display_order"], name="content_q_node_order_idx"),
            models.Index(fields=["institution_id", "status"], name="content_q_status_idx"),
            models.Index(fields=["institution_id", "node", "status"], name="content_q_node_status_idx"),
        ]


class ContentQuestionVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(ContentQuestion, on_delete=models.CASCADE, related_name="versions")
    version_no = models.PositiveIntegerField()
    state = models.CharField(max_length=20, choices=[(s, s) for s in VERSION_STATES], default=VERSION_DRAFT)
    question_text = models.TextField()
    explanation = models.TextField(blank=True, default="")
    image_key = models.CharField(max_length=500, blank=True, default="")
    image_alt_text = models.CharField(max_length=300, blank=True, default="")
    created_by = models.UUIDField()
    updated_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_for_review_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "content_question_version"
        ordering = ["version_no"]
        constraints = [
            models.UniqueConstraint(fields=["question", "version_no"], name="content_version_unique_number"),
            models.UniqueConstraint(
                fields=["question"],
                condition=Q(state__in=OPEN_VERSION_STATES),
                name="content_one_open_version_per_question",
            ),
        ]


class ContentOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(ContentQuestionVersion, on_delete=models.CASCADE, related_name="options")
    label = models.CharField(max_length=1)
    option_text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "content_option"
        ordering = ["display_order"]


class ContentQuestionUsage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(ContentQuestion, on_delete=models.PROTECT, related_name="usages")
    version_no = models.PositiveIntegerField()
    usage_type = models.CharField(max_length=40)
    usage_ref_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "content_question_usage"
        indexes = [models.Index(fields=["question", "usage_type"], name="content_usage_q_idx")]


class ContentAuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution_id = models.UUIDField(db_index=True)
    actor_id = models.UUIDField()
    action = models.CharField(max_length=60)
    entity_type = models.CharField(max_length=20)
    entity_id = models.UUIDField()
    version_no = models.PositiveIntegerField(null=True, blank=True)
    summary = models.JSONField(default=dict)
    request_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "content_audit_event"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["institution_id", "entity_type", "entity_id"], name="content_audit_entity_idx")]


class ContentMediaOrphan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=500, unique=True)
    reason = models.CharField(max_length=60)
    created_at = models.DateTimeField(auto_now_add=True)
    cleaned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "content_media_orphan"
