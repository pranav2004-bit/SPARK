import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0002_inquiry"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScrollConfig",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("is_enabled", models.BooleanField(default=False)),
                (
                    "direction",
                    models.CharField(
                        choices=[
                            ("left", "Left (RTL marquee)"),
                            ("right", "Right (LTR marquee)"),
                        ],
                        default="left",
                        max_length=5,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "scroll_config",
            },
        ),
        migrations.CreateModel(
            name="ScrollUpdate",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("text", models.CharField(max_length=300)),
                ("link", models.CharField(blank=True, default="", max_length=500)),
                ("show_new_badge", models.BooleanField(default=False)),
                ("order", models.PositiveIntegerField(db_index=True, default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "scroll_updates",
                "ordering": ["order", "created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="scrollupdate",
            index=models.Index(fields=["order"], name="idx_scroll_updates_order"),
        ),
    ]
