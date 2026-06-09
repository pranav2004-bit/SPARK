from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="student",
            index=models.Index(
                fields=["college_email_id"],
                name="idx_students_college_email",
            ),
        ),
    ]
