from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0004_remove_stale_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="module",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="company",
            name="institution_id",
            field=models.UUIDField(db_index=True),
        ),
    ]
