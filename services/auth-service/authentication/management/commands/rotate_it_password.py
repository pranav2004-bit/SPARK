import getpass
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Rotate the IT account's password and invalidate all existing tokens "
        "in a single atomic step. Logs the rotation for audit purposes. "
        "Replaces rotate_superadmin_password now that IT is the bootstrapped "
        "root account (2026-08-20)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "email",
            nargs="?",
            default=None,
            help="Email of the IT account to rotate. Defaults to IT_EMAIL.",
        )

    def handle(self, *args, **options):
        email = options["email"] or settings.IT_EMAIL

        try:
            user = User.objects.get(email=email, role="it")
        except User.DoesNotExist:
            raise CommandError(f"IT account '{email}' does not exist.")

        self.stdout.write(f"Rotating password for IT account '{email}'")

        MAX_TRIES = 3
        count = 0
        p1, p2 = 1, 2  # initially mismatched so the loop runs at least once
        validated = False
        while (p1 != p2 or not validated) and count < MAX_TRIES:
            p1 = getpass.getpass("New password: ")
            p2 = getpass.getpass("New password (again): ")
            if p1 != p2:
                self.stdout.write("Passwords do not match. Please try again.")
                count += 1
                continue
            try:
                validate_password(p2, user)
            except ValidationError as err:
                self.stderr.write("\n".join(err.messages))
                count += 1
            else:
                validated = True

        if count == MAX_TRIES:
            raise CommandError(f"Aborting password rotation for '{email}' after {count} failed attempts.")

        old_token_version = user.token_version
        user.set_password(p1)
        user.token_version += 1
        user.save(update_fields=["password", "token_version", "updated_at"])

        logger.warning(
            "SECURITY AUDIT: IT account password rotated for email=%s — "
            "token_version %s -> %s (all prior tokens invalidated). "
            "Performed via rotate_it_password management command.",
            email, old_token_version, user.token_version,
        )

        self.stdout.write(self.style.SUCCESS(
            f"Password rotated and all existing tokens invalidated for '{email}'."
        ))
