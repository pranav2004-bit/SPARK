from django.db import migrations, models
from django_migration_linter import IgnoreMigration


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0003_force_password_change_token_version"),
    ]

    operations = [
        # Already applied before django-migration-linter was adopted
        # (2026-09-08) — grandfathered, not a statement that this
        # migration's pattern is safe to repeat. See
        # PRODUCTION_CHECKLIST.md 'Items Added During Development'.
        IgnoreMigration(),
        migrations.AlterField(
            model_name="user",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
    ]
