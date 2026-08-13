from django.db import migrations, models


class Migration(migrations.Migration):
    """Add named composite indexes for hot query paths not covered by field-level db_index."""

    dependencies = [
        ("practice", "0001_initial"),
    ]

    operations = [
        # institution_id + is_published covering index for student module/section list queries
        migrations.AddIndex(
            model_name="practicemodule",
            index=models.Index(
                fields=["institution_id", "is_published"],
                name="idx_pmodule_inst_published",
            ),
        ),
        migrations.AddIndex(
            model_name="practicesection",
            index=models.Index(
                fields=["institution_id", "is_published"],
                name="idx_psection_inst_published",
            ),
        ),
    ]
