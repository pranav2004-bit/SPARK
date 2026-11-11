import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

app = Celery("essay-service")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Task 17.2 — real gap found via live verification: Celery's own
# worker_hijack_root_logger defaults to True, so the real `celery worker`
# process installs its own plain-text root logger handler on startup,
# silently overriding core/settings.py's LOGGING dict (the JSON formatter
# + CorrelationIdLogFilter that gives every log line its request_id).
# Every task in this file dutifully calls bind_request_id(...), and the
# value is computed correctly, but it was never actually visible in the
# real worker container's own log output — confirmed live: every
# essays.llm/essays.sweep log line came out as Celery's bare
# "[timestamp: LEVEL/Worker] message" with no request_id anywhere, despite
# looking correct under `manage.py shell` (which never starts a real
# Celery worker, so nothing ever hijacked the root logger there). Setting
# this to False here is the whole fix — Django's own LOGGING config is
# already correct and just needs to not be silently discarded. Inherited
# verbatim from assessment-service's own core/celery.py, which has the
# identical gap (same default, never overridden there either) — out of
# this task's own scope to fix, flagged separately.
app.conf.worker_hijack_root_logger = False

# Task 17.2 — second real gap found via live verification of this task's
# own operational queries: control_exchange defaults to the literal string
# "celery" for EVERY Celery app regardless of its own name (confirmed
# live: celery_app.conf.control_exchange == "celery" here despite
# app.main == "essay-service"). Since all 8 services share one Redis
# broker, and Celery's remote-control/pidbox mechanism routes broadcasts
# and replies through a Redis pub/sub channel keyed off control_exchange
# — not off the app's own name — every service's worker was replying to
# every OTHER service's control.ping(). Confirmed live: essay-service's
# own control.ping() returned 5 distinct container hostnames, not just
# essay-worker's own. This directly breaks the correctness of
# AdminSubmissionsPipelineHealthView's celery_workers_online metric
# (essays/views.py) — it would report workers online even if essay-worker
# itself had crashed, as long as any OTHER service's worker was still up,
# exactly the failure mode a health check exists to catch. Scoping this
# to essay-service's own name fixes it the same way task queue names
# (`-Q essay-service`) are already scoped — this is the one remaining
# unscoped shared-broker surface. The identical gap exists in every other
# service's own core/celery.py (none of them override this either); out
# of this task's own scope to fix platform-wide, flagged separately.
app.conf.control_exchange = "essay-service"
