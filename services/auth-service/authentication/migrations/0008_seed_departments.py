# Generated 2026-08-20 — one-off data migration.
#
# The Departments module replaces the frontend's hardcoded DEPARTMENTS list
# with real backend-managed data. Seed every institution currently present
# in the users table with the 11 codes the frontend constant used to hold,
# so existing dropdowns keep working unchanged the moment this ships — IT
# can then rename/add/deactivate from here going forward. Idempotent: skips
# any (institution_id, code) pair that already exists.
from django.db import migrations

DEPARTMENT_NAMES = {
    "CSD": "Computer Science and Design",
    "CSM": "Computer Science and Machine Learning",
    "CSE": "Computer Science and Engineering",
    "CSC": "Computer Science and Cyber Security",
    "ECE": "Electronics and Communication Engineering",
    "IT": "Information Technology",
    "EEE": "Electrical and Electronics Engineering",
    "MECH": "Mechanical Engineering",
    "CIVIL": "Civil Engineering",
    "CHEM": "Chemical Engineering",
    "BIOTECHNOLOGY": "Biotechnology",
}


def seed_departments(apps, schema_editor):
    User = apps.get_model("authentication", "User")
    Department = apps.get_model("authentication", "Department")

    institution_ids = set(User.objects.values_list("institution_id", flat=True).distinct())
    for institution_id in institution_ids:
        if not institution_id:
            continue
        existing_codes = set(
            Department.objects.filter(institution_id=institution_id).values_list("code", flat=True)
        )
        for code, name in DEPARTMENT_NAMES.items():
            if code in existing_codes:
                continue
            Department.objects.create(
                code=code, name=name, institution_id=institution_id, is_active=True,
            )


def noop_reverse(apps, schema_editor):
    # Not reversible — can't distinguish seeded rows from ones IT has since
    # created/edited by hand.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0007_department'),
    ]

    operations = [
        migrations.RunPython(seed_departments, noop_reverse),
    ]
