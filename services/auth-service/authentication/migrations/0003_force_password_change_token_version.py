from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0002_add_name_department_to_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="force_password_change",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="token_version",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
