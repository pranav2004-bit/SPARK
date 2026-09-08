"""
Tests for the one-off 0008_seed_departments data migration — seeds every
institution present in the users table with the 11 department codes the
frontend's hardcoded DEPARTMENTS constant used to hold, so existing
dropdowns keep working the moment the Departments module ships.
"""

import importlib
import uuid
import pytest
from django.apps import apps
from django.contrib.auth import get_user_model

_migration = importlib.import_module("authentication.migrations.0008_seed_departments")
seed_departments = _migration.seed_departments
DEPARTMENT_NAMES = _migration.DEPARTMENT_NAMES

User = get_user_model()

from authentication.models import Department


@pytest.mark.django_db
def test_seed_creates_11_departments_for_each_institution():
    inst_a = uuid.uuid4()
    inst_b = uuid.uuid4()
    User.objects.create_user(email="a@test.com", password="x", role="admin", institution_id=inst_a)
    User.objects.create_user(email="b@test.com", password="x", role="admin", institution_id=inst_b)

    seed_departments(apps, None)

    assert Department.objects.filter(institution_id=inst_a).count() == len(DEPARTMENT_NAMES)
    assert Department.objects.filter(institution_id=inst_b).count() == len(DEPARTMENT_NAMES)
    assert set(Department.objects.filter(institution_id=inst_a).values_list("code", flat=True)) == set(DEPARTMENT_NAMES.keys())


@pytest.mark.django_db
def test_seed_is_idempotent():
    inst = uuid.uuid4()
    User.objects.create_user(email="c@test.com", password="x", role="admin", institution_id=inst)

    seed_departments(apps, None)
    seed_departments(apps, None)  # run twice

    assert Department.objects.filter(institution_id=inst).count() == len(DEPARTMENT_NAMES)


@pytest.mark.django_db
def test_seed_skips_codes_that_already_exist():
    inst = uuid.uuid4()
    User.objects.create_user(email="d@test.com", password="x", role="admin", institution_id=inst)
    Department.objects.create(code="CSE", name="Custom Name", institution_id=inst, is_active=False)

    seed_departments(apps, None)

    cse = Department.objects.get(code="CSE", institution_id=inst)
    assert cse.name == "Custom Name"  # untouched, not overwritten
    assert cse.is_active is False
    assert Department.objects.filter(institution_id=inst).count() == len(DEPARTMENT_NAMES)
