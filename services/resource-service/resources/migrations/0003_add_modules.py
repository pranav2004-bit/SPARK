import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0002_add_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="Module",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("institution_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("is_published", models.BooleanField(default=False)),
                ("is_system", models.BooleanField(default=False)),
                ("order", models.PositiveIntegerField(db_index=True, default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        db_index=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="children",
                        to="resources.module",
                    ),
                ),
            ],
            options={
                "db_table": "modules",
                "ordering": ["order", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="ModuleSection",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("is_published", models.BooleanField(default=False)),
                ("order", models.PositiveIntegerField(db_index=True, default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "module",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="module_sections",
                        to="resources.module",
                    ),
                ),
            ],
            options={
                "db_table": "module_sections",
                "ordering": ["order", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="ModuleUpload",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "upload_type",
                    models.CharField(
                        choices=[
                            ("pdf", "PDF"),
                            ("audio", "Audio"),
                            ("video", "Video"),
                            ("image", "Image"),
                            ("video_link", "Video Link"),
                            ("external_link", "External Link"),
                        ],
                        max_length=20,
                    ),
                ),
                ("file_url", models.TextField()),
                ("original_filename", models.CharField(blank=True, max_length=500, null=True)),
                ("file_size_bytes", models.BigIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "section",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="uploads",
                        to="resources.modulesection",
                    ),
                ),
            ],
            options={
                "db_table": "module_uploads",
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="module",
            index=models.Index(fields=["order"], name="idx_modules_order"),
        ),
        migrations.AddIndex(
            model_name="module",
            index=models.Index(fields=["institution_id"], name="idx_modules_institution_id"),
        ),
        migrations.AddConstraint(
            model_name="module",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_system=True),
                fields=["institution_id"],
                nulls_distinct=False,
                name="unique_system_module_per_institution",
            ),
        ),
        migrations.AddIndex(
            model_name="modulesection",
            index=models.Index(fields=["module"], name="idx_module_sections_module"),
        ),
        migrations.AddIndex(
            model_name="moduleupload",
            index=models.Index(fields=["section"], name="idx_module_uploads_section"),
        ),
    ]
