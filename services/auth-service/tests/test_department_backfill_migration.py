"""
Tests for the one-off 0006_backfill_super_admin_department data migration —
randomly assigns a department to every pre-existing super_admin account that
still has department="" (created before the Department field existed).
"""

import importlib
import uuid
import pytest
from django.apps import apps
from django.contrib.auth import get_user_model

# Migration module names start with a digit, so they can't be imported with a
# normal `import` statement.
_migration = importlib.import_module(
    "authentication.migrations.0006_backfill_super_admin_department"
)
backfill_department = _migration.backfill_department
DEPARTMENTS = _migration.DEPARTMENTS

User = get_user_model()


def _make_super_admin(email, department=""):
    return User.objects.create_user(
        email=email, password="x", role="super_admin",
        institution_id=uuid.uuid4(), department=department,
    )


@pytest.mark.django_db
def test_backfill_assigns_a_department_to_blank_super_admins():
    sa = _make_super_admin("blank@test.com", department="")
    backfill_department(apps, None)
    sa.refresh_from_db()
    assert sa.department in DEPARTMENTS


@pytest.mark.django_db
def test_backfill_does_not_overwrite_existing_department():
    sa = _make_super_admin("has-dept@test.com", department="CSE")
    backfill_department(apps, None)
    sa.refresh_from_db()
    assert sa.department == "CSE"


@pytest.mark.django_db
def test_backfill_does_not_touch_other_roles():
    admin = User.objects.create_user(
        email="admin-blank@test.com", password="x", role="admin",
        institution_id=uuid.uuid4(), department="",
    )
    backfill_department(apps, None)
    admin.refresh_from_db()
    assert admin.department == ""
