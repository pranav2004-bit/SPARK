from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0003_force_password_change_token_version"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
    ]
