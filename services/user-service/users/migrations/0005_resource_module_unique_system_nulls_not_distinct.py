from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_resource_module_unique_system_per_institution"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="resourcemodule",
            name="unique_system_module_per_institution",
        ),
        migrations.AddConstraint(
            model_name="resourcemodule",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_system=True),
                fields=["institution_id"],
                nulls_distinct=False,
                name="unique_system_module_per_institution",
            ),
        ),
    ]
