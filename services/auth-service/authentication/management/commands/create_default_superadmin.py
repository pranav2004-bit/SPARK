import os
import uuid
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()


class Command(BaseCommand):
    help = "Seed the default SPARK super-admin account if it does not already exist."

    def handle(self, *args, **options):
        # Gap 3: Fail loudly if INSTITUTION_ID is missing — do not start with null institution
        raw_institution_id = os.environ.get("INSTITUTION_ID", "").strip()
        if not raw_institution_id:
            raise CommandError(
                "INSTITUTION_ID environment variable is not set or empty. "
                "auth-service cannot start without it. "
                "Set INSTITUTION_ID in auth-service/.env before deploying."
            )

        # Validate UUID format
        try:
            institution_id = uuid.UUID(raw_institution_id)
        except ValueError:
            raise CommandError(
                f"INSTITUTION_ID='{raw_institution_id}' is not a valid UUID. "
                "Generate one with: python -c \"import uuid; print(uuid.uuid4())\""
            )

        # Gap 1: Credentials from settings (which read from env), never hardcoded
        email = settings.SUPERADMIN_EMAIL
        password = settings.SUPERADMIN_PASSWORD

        existing = User.objects.filter(email=email).first()
        if existing:
            # Gap 4: Detect INSTITUTION_ID mismatch — refuse to start silently wrong
            if existing.institution_id != institution_id:
                raise CommandError(
                    f"INSTITUTION_ID mismatch detected.\n"
                    f"  .env value : {institution_id}\n"
                    f"  DB value   : {existing.institution_id}\n"
                    "These must match. Either restore the original INSTITUTION_ID in .env, "
                    "or run the migrate_institution_id management command to update the DB."
                )

            # Detect SUPERADMIN_PASSWORD drift — editing .env does NOT change an existing
            # account's password (only used at first-time creation). If the env value no
            # longer matches the live password, fail loudly instead of silently ignoring it,
            # so nobody walks away believing they rotated the password when they didn't.
            if not existing.check_password(password):
                raise CommandError(
                    "SUPERADMIN_PASSWORD in .env does not match the live database password.\n"
                    "Editing .env has NO EFFECT on an existing account's password.\n"
                    "To actually rotate the password, run: python manage.py rotate_superadmin_password\n"
                    "Then update .env to match the new password, and restart."
                )

            # institution_id is a NOT NULL database column — an existing account can never
            # lack it, so there is nothing to backfill here. The mismatch check above is the
            # only remaining guard against a wrong value.
            self.stdout.write(
                self.style.WARNING(f"Super-admin '{email}' already exists — skipping.")
            )
            return

        User.objects.create_user(
            email=email,
            password=password,
            role="super_admin",
            institution_id=institution_id,
            is_staff=True,
            is_superuser=True,
            force_password_change=True,  # Gap 2: force password change on first login
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Super-admin '{email}' created with institution_id={institution_id}. "
                "Password change will be required on first login."
            )
        )
