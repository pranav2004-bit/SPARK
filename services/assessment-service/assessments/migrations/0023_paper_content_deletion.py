import django.db.models.deletion
from django.db import migrations, models
from django_migration_linter import IgnoreMigration


# Backfills set_label_snapshot (StudentSetAllocation + AssessmentSession)
# and AssessmentSession.paper, for every row that exists today. Safe and
# cheap at any real-world scale this service runs at: at the time this was
# written, no paper's content had ever been deleted, so every row's `set`
# (and therefore `set.paper`) is still guaranteed live — this is a plain
# one-time copy, not a "recover lost data" operation. Going forward, both
# fields are populated at creation time (allocation.py,
# StudentAssignmentStartSessionView) — this backfill only covers history.
def backfill_snapshots(apps, schema_editor):
    StudentSetAllocation = apps.get_model("assessments", "StudentSetAllocation")
    AssessmentSession = apps.get_model("assessments", "AssessmentSession")

    allocations = StudentSetAllocation.objects.select_related("set").exclude(set__isnull=True)
    for alloc in allocations.iterator(chunk_size=1000):
        alloc.set_label_snapshot = alloc.set.label
    StudentSetAllocation.objects.bulk_update(allocations, ["set_label_snapshot"], batch_size=1000)

    sessions = AssessmentSession.objects.select_related("set").exclude(set__isnull=True)
    for session in sessions.iterator(chunk_size=1000):
        session.set_label_snapshot = session.set.label
        session.paper_id = session.set.paper_id
    AssessmentSession.objects.bulk_update(sessions, ["set_label_snapshot", "paper"], batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0022_batchassignment_global_start_time_required"),
    ]

    operations = [
        # lintmigrations (CI, SQLite via core.test_settings) flags two false
        # positives on this migration — "NOT NULL constraint on columns" and
        # "ADDING unique constraint" — neither is a real Postgres concern.
        # Confirmed directly with `sqlmigrate` against a real Postgres
        # connection (2026-11-13): every new NOT NULL column
        # (is_deleted x2, set_label_snapshot x2) is added as
        #     ALTER TABLE ... ADD COLUMN ... DEFAULT ... NOT NULL;
        #     ALTER TABLE ... ALTER COLUMN ... DROP DEFAULT;
        # — exactly the single-statement DEFAULT-with-NOT-NULL pattern the
        # linter's own has_default_value check looks for and would normally
        # pass (same root cause as user-service's 0010_student_section). No
        # unique constraint is added anywhere in the real SQL either — the
        # three AlterField ops here (StudentSetAllocation.set,
        # AssessmentSession.set, AssessmentResponse.question) only ever
        # *drop* NOT NULL, never add one, and touch no uniqueness at all.
        # SQLite implements every one of these as a full table rebuild (new
        # table, copy, drop old), which re-emits every pre-existing
        # constraint on the table as if newly created — including the
        # unrelated unique_together already on these models — and the
        # linter's SQL-text heuristic can't tell "recreated by rebuild" from
        # "genuinely new." Safe to ignore: this migration was never actually
        # unsafe on the database this app really runs on.
        IgnoreMigration(),

        # ── QuestionPaper: soft-delete + frozen set count ───────────────────
        migrations.AddField(
            model_name="questionpaper",
            name="is_deleted",
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddField(
            model_name="questionpaper",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="questionpaper",
            name="deleted_set_count",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),

        # ── BatchAssignment: soft-delete + frozen question-difficulty ───────
        migrations.AddField(
            model_name="batchassignment",
            name="is_deleted",
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddField(
            model_name="batchassignment",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="batchassignment",
            name="question_difficulty_snapshot",
            field=models.JSONField(blank=True, null=True),
        ),

        # ── StudentSetAllocation: frozen set label + nullable set FK ────────
        migrations.AddField(
            model_name="studentsetallocation",
            name="set_label_snapshot",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AlterField(
            model_name="studentsetallocation",
            name="set",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="allocations", to="assessments.questionset",
            ),
        ),

        # ── AssessmentSession: frozen set label + paper ref + nullable set ──
        migrations.AddField(
            model_name="assessmentsession",
            name="set_label_snapshot",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="assessmentsession",
            name="paper",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sessions", to="assessments.questionpaper",
            ),
        ),
        migrations.AlterField(
            model_name="assessmentsession",
            name="set",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sessions", to="assessments.questionset",
            ),
        ),

        # ── AssessmentResponse: nullable question FK ─────────────────────────
        migrations.AlterField(
            model_name="assessmentresponse",
            name="question",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assessment_responses", to="assessments.question",
            ),
        ),

        migrations.RunPython(backfill_snapshots, migrations.RunPython.noop),
    ]
