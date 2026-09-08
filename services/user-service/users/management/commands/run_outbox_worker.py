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
from django.db import close_old_connections

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
                # This loop never goes through Django's WSGI request/response
                # cycle (or Celery's task_prerun/postrun signals, which the
                # rest of this platform's beat/worker processes rely on) —
                # neither of which ever fires here, so nothing else in Django
                # ever closes a connection this loop broke. Without this,
                # once the DB connection to pgbouncer drops (idle timeout,
                # network blip, a postgres restart), Django's own error
                # wrapper marks it unusable, but that state is only ever
                # inspected here — the exact same connection keeps getting
                # reused and keeps raising the exact same error, forever,
                # on every subsequent poll, until this process is manually
                # restarted (found live, 2026-08-17: a stale connection from
                # hours earlier was still failing every single poll).
                # close_old_connections() is Django's own idiom for exactly
                # this "long-running process outside a request/task cycle"
                # case — closes the connection only if it's already unusable
                # or has exceeded CONN_MAX_AGE, so a healthy connection is
                # left alone and reused as normal.
                close_old_connections()
                recover_stuck_events()
                count = process_batch()
                if count:
                    logger.info("Outbox worker processed %d event(s).", count)
            except Exception as exc:
                # Log and keep running — a transient DB or network error must
                # not kill the worker process permanently. The
                # close_old_connections() call above on the *next* iteration
                # is what actually recovers from a connection-level failure
                # here; this handler's job is only to survive until then.
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
