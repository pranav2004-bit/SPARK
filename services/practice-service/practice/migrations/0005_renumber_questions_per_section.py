from django.db import migrations


def renumber_per_section(apps, schema_editor):
    """
    question_number used to be a single table-wide counter (see models.py
    PracticeQuestion.save()) — a new section's first question could end up
    displayed as e.g. "Question #847" instead of "#1". Renumber every
    existing question 1, 2, 3... within its own section, preserving current
    relative order (order, then created_at) so nothing visibly reshuffles —
    only the displayed number changes to what it should have been.
    """
    PracticeQuestion = apps.get_model("practice", "PracticeQuestion")
    PracticeSection = apps.get_model("practice", "PracticeSection")

    for section in PracticeSection.objects.all():
        questions = list(
            PracticeQuestion.objects.filter(section=section).order_by("order", "created_at")
        )
        for index, question in enumerate(questions, start=1):
            if question.question_number != index:
                question.question_number = index
                question.save(update_fields=["question_number"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("practice", "0004_institution_id_not_null"),
    ]

    operations = [
        migrations.RunPython(renumber_per_section, noop_reverse),
    ]
