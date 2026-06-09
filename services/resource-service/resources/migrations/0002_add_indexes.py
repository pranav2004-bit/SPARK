from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="company",
            index=models.Index(
                fields=["-created_at"],
                name="idx_companies_created_desc",
            ),
        ),
        migrations.AddIndex(
            model_name="upload",
            index=models.Index(
                fields=["-created_at"],
                name="idx_uploads_created_desc",
            ),
        ),
    ]
