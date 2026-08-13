"""
Tests for the rotate_superadmin_password management command.

Covers the audit-trail gap: changing a super-admin's password must
(1) actually update the password hash, (2) invalidate all existing
tokens via token_version, and (3) emit a WARNING-level log entry.
"""

import logging
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_rotate_password_updates_hash_and_token_version(super_admin_user):
    initial_version = super_admin_user.token_version

    with mock.patch("getpass.getpass", side_effect=["NewRotated@99", "NewRotated@99"]):
        call_command("rotate_superadmin_password", "superadmin@test.com", stdout=StringIO())

    super_admin_user.refresh_from_db()
    assert super_admin_user.check_password("NewRotated@99")
    assert not super_admin_user.check_password("Super@pass1")
    assert super_admin_user.token_version == initial_version + 1


@pytest.mark.django_db
def test_rotate_password_logs_security_audit_warning(super_admin_user, caplog):
    with mock.patch("getpass.getpass", side_effect=["NewRotated@99", "NewRotated@99"]):
        with caplog.at_level(logging.WARNING, logger="authentication.management.commands.rotate_superadmin_password"):
            call_command("rotate_superadmin_password", "superadmin@test.com", stdout=StringIO())

    assert any("SECURITY AUDIT" in record.message for record in caplog.records)
    assert any("superadmin@test.com" in record.message for record in caplog.records)


@pytest.mark.django_db
def test_rotate_password_mismatch_aborts_after_max_tries(super_admin_user):
    with mock.patch("getpass.getpass", side_effect=["aaa", "bbb", "ccc", "ddd", "eee", "fff"]):
        with pytest.raises(CommandError, match="Aborting"):
            call_command("rotate_superadmin_password", "superadmin@test.com", stdout=StringIO(), stderr=StringIO())

    super_admin_user.refresh_from_db()
    assert super_admin_user.check_password("Super@pass1")


@pytest.mark.django_db
def test_rotate_password_nonexistent_account_raises():
    with pytest.raises(CommandError, match="does not exist"):
        call_command("rotate_superadmin_password", "nobody@test.com", stdout=StringIO())


@pytest.mark.django_db
def test_rotate_password_defaults_to_settings_email(super_admin_user, settings):
    settings.SUPERADMIN_EMAIL = "superadmin@test.com"
    with mock.patch("getpass.getpass", side_effect=["NewRotated@99", "NewRotated@99"]):
        call_command("rotate_superadmin_password", stdout=StringIO())

    super_admin_user.refresh_from_db()
    assert super_admin_user.check_password("NewRotated@99")
