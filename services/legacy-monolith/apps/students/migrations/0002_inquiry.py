import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Inquiry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("message", models.TextField()),
                ("is_read", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "student",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inquiries",
                        to="students.student",
                    ),
                ),
            ],
            options={
                "db_table": "student_inquiries",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="inquiry",
            index=models.Index(fields=["is_read"], name="idx_inquiries_is_read"),
        ),
        migrations.AddIndex(
            model_name="inquiry",
            index=models.Index(fields=["student"], name="idx_inquiries_student"),
        ),
    ]
