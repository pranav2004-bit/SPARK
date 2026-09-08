from django.db import migrations, models
from django_migration_linter import IgnoreMigration


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0008_institution_id_scroll"),
    ]

    operations = [
        # Already applied before django-migration-linter was adopted
        # (2026-09-08) — grandfathered, not a statement that this
        # migration's pattern is safe to repeat. See
        # PRODUCTION_CHECKLIST.md 'Items Added During Development'.
        IgnoreMigration(),
        migrations.AlterField(
            model_name="batch",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="student",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="scrollconfig",
            name="institution_id",
            field=models.UUIDField(db_index=True, unique=True),
        ),
        migrations.AlterField(
            model_name="scrollupdate",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
    ]
