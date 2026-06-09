from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("practice", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="practicequestion",
            name="question_type",
            field=models.CharField(
                choices=[("mcq", "Multiple Choice"), ("fib", "Fill in the Blank")],
                default="mcq",
                max_length=10,
            ),
        ),
    ]
