from django.db import migrations, models
from django_migration_linter import IgnoreMigration


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0004_remove_stale_indexes"),
    ]

    operations = [
        # Already applied before django-migration-linter was adopted
        # (2026-09-08) — grandfathered, not a statement that this
        # migration's pattern is safe to repeat. See
        # PRODUCTION_CHECKLIST.md 'Items Added During Development'.
        IgnoreMigration(),
        migrations.AlterField(
            model_name="module",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="company",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
    ]
