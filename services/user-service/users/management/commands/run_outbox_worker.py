"""
Management command: run_outbox_worker

Runs the outbox processor in a continuous loop.  This is the entrypoint for
the outbox-worker Docker Compose service.

Graceful shutdown
-----------------
SIGTERM or SIGINT (Ctrl-C) sets a flag; the worker finishes the current batch
and then exits cleanly rather than being killed mid-event.

Configuration (Django settings / env vars)
------------------------------------------
  OUTBOX_POLL_INTERVAL — seconds between polls when no events are found
                          (default: 30)

Usage
-----
  # Docker entrypoint
  python manage.py run_outbox_worker

  # Manual (development)
  python manage.py run_outbox_worker
"""

import logging
import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from users.outbox import process_batch, recover_stuck_events

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the outbox worker continuously (polls every OUTBOX_POLL_INTERVAL seconds)."

    def handle(self, *args, **options):
        poll_interval = int(getattr(settings, "OUTBOX_POLL_INTERVAL", 30))

        self._running = True
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self.stdout.write(
            self.style.SUCCESS(
                f"Outbox worker started (poll interval: {poll_interval}s)."
            )
        )
        logger.info("Outbox worker started.")

        while self._running:
            try:
                recover_stuck_events()
                count = process_batch()
                if count:
                    logger.info("Outbox worker processed %d event(s).", count)
            except Exception as exc:
                # Log and keep running — a transient DB or network error must
                # not kill the worker process permanently.
                logger.exception(
                    "Unexpected error in outbox worker main loop: %s", exc
                )

            # Sleep in 1-second increments so SIGTERM is handled promptly.
            for _ in range(poll_interval):
                if not self._running:
                    break
                time.sleep(1)

        self.stdout.write(self.style.SUCCESS("Outbox worker stopped gracefully."))
        logger.info("Outbox worker stopped.")

    def _handle_signal(self, signum, frame):
        logger.info(
            "Outbox worker received signal %d — finishing current batch then stopping.",
            signum,
        )
        self._running = False
