import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

app = Celery("notification-service")
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
app.conf.control_exchange = "notification-service"

# worker_hijack_root_logger defaults to True, which silently overrides a
# JSON-formatted root logger with Celery's own plain-text one — the real
# bug found and fixed on essay-service/assessment-service
# (LIVETRACKER3_V1.md Task 17.2). Set to False here too for consistency
# and because it's the objectively correct value — but unlike those two
# services, this one has **no LOGGING dict or core/logging_utils.py at
# all** (confirmed: grepped, neither exists here), so there is currently
# no JSON formatter for this setting to protect — it is a harmless no-op
# today, not a live fix. Confirmed live: notification-worker's real log
# output is still plain Celery text after this change, because there was
# never a JSON formatter here to begin with, not because this setting
# failed. Porting the actual JSON-logging/correlation-ID infrastructure to
# this service is a separate, larger gap, out of scope here.
app.conf.worker_hijack_root_logger = False
