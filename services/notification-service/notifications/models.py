import uuid
from django.db import models


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ("resource_upload", "Resource Upload"),
        ("announcement", "Announcement"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True)
    institution_id = models.UUIDField(db_index=True)
    type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user_id", "is_read", "is_deleted"], name="notif_user_read_deleted_idx"),
            models.Index(fields=["-created_at"], name="notif_created_desc_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification({self.type}, user={self.user_id}, read={self.is_read})"
