import django.db.models.deletion
from django.db import migrations, models
from django_migration_linter import IgnoreMigration


class Migration(migrations.Migration):

    dependencies = [
        ('assessments', '0018_backfill_question_sections'),
    ]

    operations = [
        # Already applied before django-migration-linter was adopted
        # (2026-09-08) — grandfathered, not a statement that this
        # migration's pattern is safe to repeat. See
        # PRODUCTION_CHECKLIST.md 'Items Added During Development'.
        IgnoreMigration(),
        migrations.AlterField(
            model_name='question',
            name='section',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='questions',
                to='assessments.questionsection',
            ),
        ),
    ]
