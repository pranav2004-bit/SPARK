import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_add_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="OutboxEvent",
            fields=[
                ("id", models.UUIDField(
                    default=uuid.uuid4, editable=False,
                    primary_key=True, serialize=False,
                )),
                ("event_type", models.CharField(
                    choices=[("delete_student_auth", "Delete Student Auth")],
                    max_length=100,
                )),
                ("payload", models.JSONField()),
                ("status", models.CharField(
                    choices=[
                        ("pending",     "Pending"),
                        ("processing",  "Processing"),
                        ("done",        "Done"),
                        ("dead_letter", "Dead Letter"),
                    ],
                    default="pending",
                    max_length=20,
                )),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("retry_after", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("last_attempted_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "outbox_events"},
        ),
        migrations.AddIndex(
            model_name="outboxevent",
            index=models.Index(
                fields=["status", "retry_after", "created_at"],
                name="idx_outbox_worker_query",
            ),
        ),
    ]
