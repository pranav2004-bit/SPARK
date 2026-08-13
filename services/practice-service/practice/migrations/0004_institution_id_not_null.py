from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("practice", "0003_institution_id_progress_attempt"),
    ]

    operations = [
        migrations.AlterField(
            model_name="practicemodule",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="practicesection",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="practicequestionprogress",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="practicequestionattempt",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
    ]
