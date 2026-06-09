"""
Management command: cleanup_ghost_students

PURPOSE
-------
Finds every Student record that is marked inactive (is_active=False).
These records fall into one of two categories:

  A) Legacy ghost records — students that were "deleted" via the old trash-icon
     path BEFORE the hard-delete fix was applied.  The record was never truly
     removed; only is_active was set to False.  Their auth accounts are also
     still present in auth-service with is_active=False.

  B) Intentionally disabled students — records toggled off via the enable/
     disable switch.  These should NOT be deleted.

Because both categories share the same is_active=False state, this command
cannot auto-distinguish them.  It prints the full list for manual review and
requires an explicit --execute flag to actually delete anything.

USAGE
-----
  # Safe dry-run (default) — lists all inactive students, touches nothing:
  python manage.py cleanup_ghost_students

  # Actually delete — back up your database first:
  python manage.py cleanup_ghost_students --execute

WHAT --execute DOES
-------------------
For each inactive student record:
  1. Calls delete_student_auth(student_id) — removes the orphan auth account
     from auth-service (non-fatal: logs a warning if auth-service is
     unreachable but continues with the DB deletion).
  2. Deletes the Student row from the user-service database.

WARNING
-------
  --execute is IRREVERSIBLE.  Review the dry-run output carefully and ensure
  that no intentionally-disabled students are in the list before running with
  --execute.  Back up the database before proceeding in production.
"""

import logging
from django.core.management.base import BaseCommand
from django.db import transaction

from users.models import Student
from core.auth_client import delete_student_auth

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "List (dry-run) or permanently delete student records marked "
        "is_active=False.  These may be legacy soft-delete ghosts OR "
        "intentionally disabled students — review carefully before --execute."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            default=False,
            help=(
                "Actually delete the listed records and their auth accounts. "
                "Omit this flag for a safe dry-run listing."
            ),
        )

    def handle(self, *args, **options):
        execute = options["execute"]

        ghosts = (
            Student.objects
            .filter(is_active=False)
            .order_by("institution_id", "created_at")
        )
        count = ghosts.count()

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS("No inactive student records found. Nothing to do.")
            )
            return

        # ── Print the list ─────────────────────────────────────────────────────
        self.stdout.write(
            self.style.WARNING(
                f"\nFound {count} inactive student record(s).\n"
                f"\n"
                f"  IMPORTANT: These may be LEGACY GHOST RECORDS (soft-deleted before\n"
                f"  the hard-delete fix) OR INTENTIONALLY DISABLED students (toggled\n"
                f"  off via the admin UI).  Review the list below carefully.\n"
            )
        )

        header = f"{'#':<5} {'Student ID':<22} {'Department':<15} {'Institution':<38} {'Created':<20}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for idx, s in enumerate(ghosts, start=1):
            self.stdout.write(
                f"{idx:<5} {s.student_id:<22} {s.department:<15} "
                f"{str(s.institution_id):<38} {str(s.created_at)[:19]:<20}"
            )

        if not execute:
            self.stdout.write(
                self.style.WARNING(
                    f"\nDRY RUN — no records were changed.\n"
                    f"Re-run with --execute to permanently delete all {count} record(s) above.\n"
                    f"WARNING: --execute is irreversible.  Back up your database first.\n"
                )
            )
            return

        # ── Execute: delete each ghost ─────────────────────────────────────────
        self.stdout.write(
            self.style.WARNING(
                f"\nDeleting {count} record(s) and their auth accounts...\n"
            )
        )

        deleted = 0
        errors = 0

        # Snapshot the list before iterating so DB changes don't shift the cursor.
        snapshot = list(ghosts.values_list("pk", "student_id"))

        for pk, student_id in snapshot:
            try:
                with transaction.atomic():
                    Student.objects.filter(pk=pk).delete()
                # Auth cleanup is best-effort (delete_student_auth catches all errors).
                delete_student_auth(student_id)
                deleted += 1
                self.stdout.write(f"  [OK]    {student_id}")
            except Exception as exc:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(f"  [ERROR] {student_id}: {exc}")
                )
                logger.error(
                    "cleanup_ghost_students: failed to delete student_id=%s: %s",
                    student_id, exc, exc_info=True,
                )

        style = self.style.SUCCESS if errors == 0 else self.style.WARNING
        self.stdout.write(
            style(
                f"\nDone. {deleted} deleted, {errors} error(s).\n"
            )
        )
