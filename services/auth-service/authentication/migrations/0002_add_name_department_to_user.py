from django.db import migrations, models
from django_migration_linter import IgnoreMigration


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0001_initial"),
    ]

    operations = [
        # Already applied before django-migration-linter was adopted
        # (2026-09-08) — grandfathered, not a statement that this
        # migration's pattern is safe to repeat. See
        # PRODUCTION_CHECKLIST.md 'Items Added During Development'.
        IgnoreMigration(),
        migrations.AddField(
            model_name="user",
            name="name",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="user",
            name="department",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
