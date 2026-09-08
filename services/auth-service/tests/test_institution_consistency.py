"""
Tests for audit_institution_consistency — catches institution_id drift across
ALL super_admin/admin/student accounts, not just the IT account's own record
(which create_default_it already validates on every startup). IT is the
bootstrapped root (2026-08-20), replacing super_admin in that role.

Note: institution_id is a NOT NULL database column (see
authentication/migrations/0004_institution_id_not_null.py), so a NULL-institution_id
scenario can no longer be represented in the database at all — no test is needed
for an impossible state.
"""

import uuid
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

User = get_user_model()


# ── Cross-account consistency audit ────────────────────────────────────────────

@pytest.mark.django_db
def test_audit_passes_when_all_accounts_match(it_user, super_admin_user, admin_user, student_user):
    """No CommandError when every account's institution_id matches the IT account's."""
    institution_id = it_user.institution_id
    super_admin_user.institution_id = institution_id
    super_admin_user.save(update_fields=["institution_id"])
    admin_user.institution_id = institution_id
    admin_user.save(update_fields=["institution_id"])
    student_user.institution_id = institution_id
    student_user.save(update_fields=["institution_id"])

    call_command("audit_institution_consistency", stdout=StringIO())  # must not raise


@pytest.mark.django_db
def test_audit_detects_mismatched_account(it_user, admin_user):
    """CommandError raised, listing the offending account, when one differs."""
    admin_user.institution_id = uuid.uuid4()  # deliberately different
    admin_user.save(update_fields=["institution_id"])

    with pytest.raises(CommandError, match="admin@test.com"):
        call_command("audit_institution_consistency", stdout=StringIO())


@pytest.mark.django_db
def test_audit_raises_if_it_account_missing():
    with pytest.raises(CommandError, match="No IT account exists"):
        call_command("audit_institution_consistency", stdout=StringIO())
