import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PracticeModule",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=200)),
                ("is_published", models.BooleanField(default=False)),
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
                        to="practice.practicemodule",
                    ),
                ),
            ],
            options={"db_table": "practice_modules", "ordering": ["order", "created_at"]},
        ),
        migrations.CreateModel(
            name="PracticeSection",
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
                        blank=True,
                        db_index=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sections",
                        to="practice.practicemodule",
                    ),
                ),
            ],
            options={"db_table": "practice_sections", "ordering": ["order", "created_at"]},
        ),
        migrations.CreateModel(
            name="PracticeQuestion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(help_text="Question display title / preview text", max_length=500)),
                ("is_published", models.BooleanField(default=False)),
                ("order", models.PositiveIntegerField(db_index=True, default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "section",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="questions",
                        to="practice.practicesection",
                    ),
                ),
            ],
            options={"db_table": "practice_questions", "ordering": ["order", "created_at"]},
        ),
    ]
