"""
Migration: remove ResourceUpload, ResourceSection, ResourceModule from user-service.

These models have been migrated to resource-service (Module, ModuleSection, ModuleUpload).
Run the management command in resource-service BEFORE applying this migration:

    docker exec <resource-service-container> python manage.py migrate_resource_data \
        --source-db-host pgbouncer \
        --source-db-name user_db \
        --source-db-user user_db_user \
        --source-db-password user_dev_password_2024

After that, apply this migration to drop the old tables:

    docker exec <user-service-container> python manage.py migrate
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_resource_module_unique_system_nulls_not_distinct"),
    ]

    operations = [
        # Delete leaf first, then parent — respects FK constraints.
        migrations.DeleteModel(name="ResourceUpload"),
        migrations.DeleteModel(name="ResourceSection"),
        migrations.DeleteModel(name="ResourceModule"),
    ]
