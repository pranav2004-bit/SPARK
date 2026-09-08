from django.db import migrations, models
from django_migration_linter import IgnoreMigration


class Migration(migrations.Migration):

    dependencies = [
        ("practice", "0003_institution_id_progress_attempt"),
    ]

    operations = [
        # Already applied before django-migration-linter was adopted
        # (2026-09-08) — grandfathered, not a statement that this
        # migration's pattern is safe to repeat. See
        # PRODUCTION_CHECKLIST.md 'Items Added During Development'.
        IgnoreMigration(),
        migrations.AlterField(
            model_name="practicemodule",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="practicesection",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="practicequestionprogress",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="practicequestionattempt",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
    ]
