"""
Tests for the rotate_it_password management command.

Replaces test_rotate_superadmin_password.py (2026-08-20) — IT is now the
platform's bootstrapped root account, replacing super_admin in that role.

Covers the audit-trail gap: changing the IT account's password must
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
def test_rotate_password_updates_hash_and_token_version(it_user):
    initial_version = it_user.token_version

    with mock.patch("getpass.getpass", side_effect=["NewRotated@99", "NewRotated@99"]):
        call_command("rotate_it_password", "it@test.com", stdout=StringIO())

    it_user.refresh_from_db()
    assert it_user.check_password("NewRotated@99")
    assert not it_user.check_password("It@pass123")
    assert it_user.token_version == initial_version + 1


@pytest.mark.django_db
def test_rotate_password_logs_security_audit_warning(it_user, caplog):
    with mock.patch("getpass.getpass", side_effect=["NewRotated@99", "NewRotated@99"]):
        with caplog.at_level(logging.WARNING, logger="authentication.management.commands.rotate_it_password"):
            call_command("rotate_it_password", "it@test.com", stdout=StringIO())

    assert any("SECURITY AUDIT" in record.message for record in caplog.records)
    assert any("it@test.com" in record.message for record in caplog.records)


@pytest.mark.django_db
def test_rotate_password_mismatch_aborts_after_max_tries(it_user):
    with mock.patch("getpass.getpass", side_effect=["aaa", "bbb", "ccc", "ddd", "eee", "fff"]):
        with pytest.raises(CommandError, match="Aborting"):
            call_command("rotate_it_password", "it@test.com", stdout=StringIO(), stderr=StringIO())

    it_user.refresh_from_db()
    assert it_user.check_password("It@pass123")


@pytest.mark.django_db
def test_rotate_password_nonexistent_account_raises():
    with pytest.raises(CommandError, match="does not exist"):
        call_command("rotate_it_password", "nobody@test.com", stdout=StringIO())


@pytest.mark.django_db
def test_rotate_password_defaults_to_settings_email(it_user, settings):
    settings.IT_EMAIL = "it@test.com"
    with mock.patch("getpass.getpass", side_effect=["NewRotated@99", "NewRotated@99"]):
        call_command("rotate_it_password", stdout=StringIO())

    it_user.refresh_from_db()
    assert it_user.check_password("NewRotated@99")
