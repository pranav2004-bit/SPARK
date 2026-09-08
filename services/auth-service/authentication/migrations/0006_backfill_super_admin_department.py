# Generated 2026-08-20 — one-off data migration.
#
# The Department dropdown was just added to Super Admin account creation
# (frontend/src/app/it/super-admins/page.tsx). Every Super Admin account
# created BEFORE this feature existed has department="" (the model's
# default). Per explicit instruction, backfill those existing accounts with
# a randomly-assigned department rather than leaving them blank — this is a
# one-time data fix, not an ongoing behavior, so it lives here rather than
# in application code.
import random

from django.db import migrations

DEPARTMENTS = ["CSD", "CSM", "CSE", "CSC", "ECE", "IT", "EEE", "MECH", "CIVIL", "CHEM", "BIOTECHNOLOGY"]


def backfill_department(apps, schema_editor):
    User = apps.get_model("authentication", "User")
    rng = random.Random(20260820)  # fixed seed — deterministic, reproducible backfill
    for user in User.objects.filter(role="super_admin", department=""):
        user.department = rng.choice(DEPARTMENTS)
        user.save(update_fields=["department"])


def noop_reverse(apps, schema_editor):
    # Not reversible — we don't know which accounts were blank before this
    # ran. Reversing would have to blank every super_admin's department,
    # which could wipe real data entered after this migration ran.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0005_alter_user_role'),
    ]

    operations = [
        migrations.RunPython(backfill_department, noop_reverse),
    ]
