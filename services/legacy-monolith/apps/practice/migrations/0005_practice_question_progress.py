import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("practice", "0004_fib_question_fields"),
        ("students", "0001_initial"),   # Student model lives in the students app
    ]

    operations = [
        migrations.CreateModel(
            name="PracticeQuestionProgress",
            fields=[
                ("id",      models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("student", models.ForeignKey(
                    to="students.Student",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="question_progress",
                    db_index=True,
                )),
                ("question", models.ForeignKey(
                    to="practice.PracticeQuestion",
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="student_progress",
                    db_index=True,
                )),
                ("status", models.CharField(
                    max_length=20,
                    choices=[
                        ("not_visited", "Not Visited"),
                        ("visited",     "Visited"),
                        ("attempted",   "Attempted"),
                    ],
                    default="not_visited",
                    db_index=True,
                )),
                ("first_visited_at",   models.DateTimeField(null=True, blank=True)),
                ("first_attempted_at", models.DateTimeField(null=True, blank=True)),
                ("updated_at",         models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "practice_question_progress",
            },
        ),
        migrations.AlterUniqueTogether(
            name="practicequestionprogress",
            unique_together={("student", "question")},
        ),
        migrations.AddIndex(
            model_name="practicequestionprogress",
            index=models.Index(fields=["student", "question"], name="idx_pqp_student_question"),
        ),
        migrations.AddIndex(
            model_name="practicequestionprogress",
            index=models.Index(fields=["student"], name="idx_pqp_student"),
        ),
    ]
