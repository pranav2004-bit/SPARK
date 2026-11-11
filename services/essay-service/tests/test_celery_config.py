"""Regression coverage for two real bugs found via live verification
(LIVETRACKER3_V1.md Task 17.2), both fixed in core/celery.py, neither
previously covered by any automated test — only live-verified, which is
why they were never caught before and could silently regress again
without these:

1. control_exchange left at Celery's own "celery" default meant every
   service's worker replied to every OTHER service's control.ping()
   (all 8 services share one Redis broker) — confirmed live via 5
   distinct container hostnames replying to essay-service's own ping.
2. worker_hijack_root_logger left at its own True default meant the real
   `celery worker` process silently discarded core/settings.py's JSON
   logging config on startup — confirmed live via essay-worker's actual
   log output being plain Celery text with no request_id anywhere.
"""
from core.celery import app as celery_app


class TestCeleryConfig:
    def test_control_exchange_is_scoped_to_this_service(self):
        assert celery_app.conf.control_exchange == "essay-service"

    def test_worker_does_not_hijack_the_root_logger(self):
        assert celery_app.conf.worker_hijack_root_logger is False
