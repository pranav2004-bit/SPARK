import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

app = Celery("assessment-service")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# control_exchange defaults to the literal string "celery" for every Celery
# app regardless of its own name — since all 8 services on this platform
# share one Redis broker, and Celery's remote-control/pidbox mechanism
# (control.ping() etc.) routes through a Redis pub/sub channel keyed off
# control_exchange, not the app's own name, every service's worker replies
# to every OTHER service's control.ping(). Found live on essay-service
# (LIVETRACKER3_V1.md Task 17.2, services/essay-service/core/celery.py has
# the full investigation/reasoning): a control.ping() there returned 5
# distinct container hostnames before this fix. No control.ping()-based
# health check exists in this service today (grepped, none found), so this
# is a latent-but-real correctness fix, not an active-bug fix — scoping it
# now so any future celery_workers_online-style metric here is correct
# from day one rather than silently wrong the way essay-service's was.
app.conf.control_exchange = "assessment-service"

# worker_hijack_root_logger defaults to True — the real `celery worker`
# process installs its own plain-text root logger handler on startup,
# silently overriding core/settings.py's LOGGING dict (the JSON formatter
# that gives every log line its request_id). Confirmed live: this
# service's own bind_request_id(self.request.id) calls in assessments/
# tasks.py have been computing the correct value the whole time, but it
# was never actually visible in assessment-worker's real log output —
# `docker logs infra-assessment-worker-1` showed Celery's bare
# "[timestamp: LEVEL/Worker] message" with no request_id anywhere, despite
# core/logging_utils.py's own operations-doc claim that Celery task logs
# carry it. Found via the same essay-service investigation that found the
# control_exchange gap above (LIVETRACKER3_V1.md Task 17.2) but not
# propagated here until this same pass caught it live too. Setting this to
# False is the whole fix — Django's own LOGGING config was already
# correct and just needed to not be silently discarded.
app.conf.worker_hijack_root_logger = False
