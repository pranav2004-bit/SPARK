from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("practice", "0002_practicequestion_question_type"),
    ]

    operations = [
        # Add question_number — default 0 for any pre-existing rows;
        # new rows get auto-assigned via model.save()
        migrations.AddField(
            model_name="practicequestion",
            name="question_number",
            field=models.PositiveIntegerField(default=0, db_index=True),
        ),
        # Make title optional (blank + default "")
        migrations.AlterField(
            model_name="practicequestion",
            name="title",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Question display text — authored in the question editor",
                max_length=500,
            ),
        ),
    ]
