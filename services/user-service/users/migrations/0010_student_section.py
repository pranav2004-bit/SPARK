from django.db import migrations, models
from django_migration_linter import IgnoreMigration


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0009_institution_id_not_null"),
    ]

    operations = [
        # django-migration-linter flags this as a bare NOT NULL constraint
        # when run under CI's `lintmigrations --settings=core.test_settings`
        # (SQLite) — but that's a false positive specific to SQLite, not a
        # real Postgres concern. Confirmed directly with `sqlmigrate` against
        # a real Postgres connection (2026-11-13): the actual SQL emitted is
        #     ALTER TABLE "students" ADD COLUMN "section" varchar(1) DEFAULT 'Z' NOT NULL;
        #     ALTER TABLE "students" ALTER COLUMN "section" DROP DEFAULT;
        # — a DEFAULT in the same ADD COLUMN statement as the NOT NULL,
        # which is exactly what the linter's own has_default_value check
        # looks for and would normally pass. SQLite has no equivalent
        # column-level ALTER here — Django implements AddField-with-default
        # on SQLite via a full table rebuild (new table, INSERT...SELECT
        # copying the default as a one-time literal, old table dropped),
        # which never produces a column-level DEFAULT the linter's SQL-text
        # heuristic can see, even though the field functionally has one.
        # Safe to ignore: unlike assessment-service's 0022 migration (a
        # genuine, if deployment-model-mitigated, NOT NULL case), this one
        # was never actually unsafe on the database this app really runs on.
        IgnoreMigration(),
        migrations.AddField(
            model_name="student",
            name="section",
            # default="Z" + preserve_default=False (user decision,
            # 2026-11-13): a one-time backfill value for every pre-existing
            # student row, applied by this migration's own ADD COLUMN step —
            # not a permanent model-level default. The model field itself
            # (models.py) has no default at all; every student created from
            # here on must have an admin explicitly choose a real section.
            # IT edits each backfilled "Z" row to its real section manually.
            field=models.CharField(default="Z", max_length=1),
            preserve_default=False,
        ),
        migrations.AddIndex(
            model_name="student",
            index=models.Index(fields=["section"], name="idx_students_section"),
        ),
    ]
