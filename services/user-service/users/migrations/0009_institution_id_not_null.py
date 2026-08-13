from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0008_institution_id_scroll"),
    ]

    operations = [
        migrations.AlterField(
            model_name="batch",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="student",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="scrollconfig",
            name="institution_id",
            field=models.UUIDField(db_index=True, unique=True),
        ),
        migrations.AlterField(
            model_name="scrollupdate",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
    ]
