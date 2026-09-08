from django.db import migrations, models
from django_migration_linter import IgnoreMigration


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0002_add_name_department_to_user"),
    ]

    operations = [
        # Already applied before django-migration-linter was adopted
        # (2026-09-08) — grandfathered, not a statement that this
        # migration's pattern is safe to repeat. See
        # PRODUCTION_CHECKLIST.md 'Items Added During Development'.
        IgnoreMigration(),
        migrations.AddField(
            model_name="user",
            name="force_password_change",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="token_version",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
