"""
Management command: process_outbox

Processes one batch of pending outbox events.  Useful for manual runs and
for verifying worker behaviour in staging.  The production worker runs this
in a loop via run_outbox_worker.

Usage
-----
  python manage.py process_outbox
"""

import logging
from django.core.management.base import BaseCommand
from users.outbox import recover_stuck_events, process_batch

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process one batch of pending outbox events."

    def handle(self, *args, **options):
        recovered = recover_stuck_events()
        if recovered:
            self.stdout.write(
                self.style.WARNING(f"Recovered {recovered} stuck event(s).")
            )

        count = process_batch()
        if count:
            self.stdout.write(
                self.style.SUCCESS(f"Processed {count} outbox event(s).")
            )
        else:
            self.stdout.write("No pending events.")
