"""
Management command: cleanup_outbox

Deletes DONE outbox events older than RETENTION_DAYS to prevent the outbox
table from growing unboundedly.  Safe to schedule as a nightly cron job.

Dead-letter events are NEVER deleted automatically — they require manual
review and intervention before removal.

Usage
-----
  # Dry run (default) — shows count without deleting:
  python manage.py cleanup_outbox --dry-run

  # Actually delete (default retention: 30 days):
  python manage.py cleanup_outbox

  # Custom retention period:
  python manage.py cleanup_outbox --retention-days 7
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import OutboxEvent

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 30


class Command(BaseCommand):
    help = (
        f"Delete DONE outbox events older than RETENTION_DAYS "
        f"(default: {DEFAULT_RETENTION_DAYS}) to control table growth."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--retention-days",
            type=int,
            default=DEFAULT_RETENTION_DAYS,
            dest="retention_days",
            help=f"Delete DONE events older than this many days (default: {DEFAULT_RETENTION_DAYS}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Show the count that would be deleted without actually deleting.",
        )

    def handle(self, *args, **options):
        retention_days = options["retention_days"]
        dry_run = options["dry_run"]

        cutoff = timezone.now() - timedelta(days=retention_days)
        qs = OutboxEvent.objects.filter(
            status=OutboxEvent.Status.DONE,
            processed_at__lt=cutoff,
        )
        count = qs.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: {count} DONE event(s) older than {retention_days} days "
                    f"would be deleted.  Re-run without --dry-run to apply."
                )
            )
            return

        if count == 0:
            self.stdout.write("No expired outbox events to clean up.")
            return

        deleted, _ = qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted} DONE outbox event(s) older than {retention_days} days."
            )
        )
        logger.info(
            "cleanup_outbox: deleted %d DONE event(s) older than %d days.",
            deleted, retention_days,
        )
