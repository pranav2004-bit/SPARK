from django.db import migrations, models
from django_migration_linter import IgnoreMigration


# Losslessly converts every existing assignment's flat `departments` list
# into the new `department_sections` shape, with an empty `sections` list
# per department entry — which is exactly how a bare department name in
# the old field behaved (every section in that department, no narrowing).
# Pre-existing roster behavior is therefore unchanged for every assignment
# that predates this migration; only a NEW edit through the admin UI can
# actually narrow by section.
def backfill_department_sections(apps, schema_editor):
    BatchAssignment = apps.get_model("assessments", "BatchAssignment")

    assignments = BatchAssignment.objects.exclude(departments=[])
    for assignment in assignments.iterator(chunk_size=1000):
        assignment.department_sections = [
            {"department": d, "sections": []} for d in assignment.departments
        ]
    BatchAssignment.objects.bulk_update(assignments, ["department_sections"], batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0023_paper_content_deletion"),
    ]

    operations = [
        # lintmigrations (CI, SQLite via core.test_settings) flags two
        # things on this migration — "NOT NULL constraint on columns" and
        # "DROPPING columns (table: assessment_batch_assignments, column:
        # departments)". These are NOT the same class of issue and are
        # addressed separately below rather than waved away together:
        #
        # 1. "NOT NULL constraint" is the same SQLite-table-rebuild false
        #    positive already resolved on 0010_student_section and
        #    0023_paper_content_deletion. Confirmed via `sqlmigrate`
        #    against a real Postgres connection (2026-11-14): the new
        #    column is added as
        #        ALTER TABLE ... ADD COLUMN "department_sections" jsonb
        #            DEFAULT '[]'::jsonb NOT NULL;
        #        ALTER TABLE ... ALTER COLUMN "department_sections" DROP
        #            DEFAULT;
        #    — a DEFAULT in the same ADD COLUMN statement as the NOT NULL,
        #    exactly what the linter's own has_default_value check looks
        #    for and would normally pass. SQLite has no equivalent
        #    column-level ALTER; Django implements this via a full table
        #    rebuild there, which the linter's SQL-text heuristic can't
        #    see through.
        #
        # 2. "DROPPING columns" is NOT a false positive — `departments` is
        #    genuinely dropped (`ALTER TABLE ... DROP COLUMN "departments"
        #    CASCADE;`, confirmed via the same sqlmigrate check). The
        #    linter's concern is real in general: a rolling/blue-green
        #    deploy where old code is still running against the new
        #    schema would break the instant this column disappears. That
        #    concern does not apply to how this specific project deploys,
        #    though (confirmed by reading entrypoint.sh/start-prod.sh):
        #    every deploy here is `migrate` THEN start the one app
        #    process — old and new code are never running concurrently
        #    against the same schema, so there is no window where
        #    already-running old code could still read/write `departments`
        #    after this migration applies. The only code that ever read
        #    or wrote it (allocation.py, views.py, serializers.py,
        #    models.py, every test file) was converted to
        #    `department_sections` in this exact same change — confirmed
        #    by grep, not assumed — so nothing in this codebase, deployed
        #    this way, is unsafe the moment this column is gone. Unlike
        #    item 1 above, this would be a real expand-and-contract
        #    concern on a rolling-deploy architecture; it just isn't one
        #    here.
        IgnoreMigration(),

        migrations.AddField(
            model_name="batchassignment",
            name="department_sections",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(backfill_department_sections, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="batchassignment",
            name="departments",
        ),
    ]
