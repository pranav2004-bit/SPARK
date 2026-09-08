import uuid

from django.db import migrations


def backfill_default_sections(apps, schema_editor):
    """Every existing set-with-questions gets one default "Section 1" so no
    pre-existing Question is left orphaned once `section` becomes required
    (see 0019, which tightens the field — split into its own migration
    because Postgres can't ALTER a table in the same transaction right after
    a bulk update() against it)."""
    QuestionSet = apps.get_model("assessments", "QuestionSet")
    QuestionSection = apps.get_model("assessments", "QuestionSection")

    for qset in QuestionSet.objects.filter(questions__isnull=False).distinct():
        section = QuestionSection.objects.create(
            id=uuid.uuid4(), set=qset, title="Section 1", order=1,
        )
        qset.questions.update(section=section)


def noop_reverse(apps, schema_editor):
    # Data-only forward step — nothing to reverse (0019's AlterField reverses
    # on its own; leaving created sections in place on rollback is harmless
    # and avoids re-orphaning questions).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('assessments', '0017_questionsection_question_section'),
    ]

    operations = [
        migrations.RunPython(backfill_default_sections, noop_reverse),
    ]
