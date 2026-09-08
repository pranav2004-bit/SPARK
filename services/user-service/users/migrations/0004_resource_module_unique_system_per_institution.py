from django.db import migrations, models
from django_migration_linter import IgnoreMigration


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_add_outbox_event"),
    ]

    operations = [
        # Already applied before django-migration-linter was adopted
        # (2026-09-08) — grandfathered, not a statement that this
        # migration's pattern is safe to repeat. See
        # PRODUCTION_CHECKLIST.md 'Items Added During Development'.
        IgnoreMigration(),
        migrations.AddConstraint(
            model_name="resourcemodule",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_system=True),
                fields=["institution_id"],
                name="unique_system_module_per_institution",
            ),
        ),
    ]
