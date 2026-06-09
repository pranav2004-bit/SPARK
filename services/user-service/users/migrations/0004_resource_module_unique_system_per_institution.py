from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_add_outbox_event"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="resourcemodule",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_system=True),
                fields=["institution_id"],
                name="unique_system_module_per_institution",
            ),
        ),
    ]
