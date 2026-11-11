import os
from pathlib import Path
from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _require_env(name: str, min_length: int = 0) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"Required environment variable '{name}' is missing or empty. "
            f"See services/essay-service/.env.example for reference."
        )
    if min_length and len(value) < min_length:
        raise ImproperlyConfigured(
            f"Environment variable '{name}' is too short "
            f"(got {len(value)} chars, minimum is {min_length})."
        )
    return value


ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
DEBUG = os.environ.get("DEBUG", "True") == "True"

if DEBUG and ENVIRONMENT == "production":
    raise ImproperlyConfigured(
        "DEBUG=True cannot be used when ENVIRONMENT=production. "
        "Set DEBUG=False before starting in production."
    )

SECRET_KEY = _require_env("SECRET_KEY", min_length=50)
# In production, this MUST also include the internal Docker hostname
# "essay-service" if any other service ever calls this one directly over
# the Docker network (bypassing nginx) — see PRODUCTION_CHECKLIST.md and
# the real 2026-09-16 incident where this exact omission (for auth-service
# and user-service) silently broke internal service-to-service calls with
# a generic 400, before ever reaching a view. Not needed yet in Phase 1
# (nothing calls into essay-service internally so far) — add it the moment
# a Task in a later phase introduces such a call, not after it breaks.
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost 127.0.0.1").split()

if ENVIRONMENT == "production":
    _require_env("DB_PASSWORD")
    _require_env("JWT_SIGNING_KEY", min_length=32)

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "rest_framework_simplejwt",
    "django_celery_beat",
    "essays",
]

MIDDLEWARE = [
    # First in the chain — rejects an oversized request before any other
    # middleware or view code touches it (mirrors assessment-service's
    # Task 12.2 finding: Django's own DATA_UPLOAD_MAX_MEMORY_SIZE guard does
    # not actually engage under this stack's uvicorn/ASGI deployment).
    "core.middleware.MaxBodySizeMiddleware",
    # Second — every log line for the rest of this request's lifecycle
    # should carry the correlation ID.
    "core.logging_utils.CorrelationIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

APPEND_SLASH = False

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "essay_db"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": int(os.environ.get("CONN_MAX_AGE", "0")),
        "OPTIONS": {"connect_timeout": 10},
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "core.authentication.ServiceJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
    # Defense-in-depth: nginx is the primary rate limiter (gateway/nginx.conf,
    # nginx.dev.conf). These DRF-level throttles exist for the case where a
    # request reaches this service WITHOUT going through nginx — not as the
    # main control. NUM_PROXIES=1 matches every other service on this
    # platform: there is exactly one trusted reverse proxy (nginx) in front,
    # and without this DRF's throttle IP-extraction would trust a
    # client-spoofed X-Forwarded-For prefix.
    "NUM_PROXIES": 1,
    # Resilient*RateThrottle (core/throttling_resilience.py), not DRF's raw
    # classes — fails open on a Redis outage instead of 500ing almost every
    # request, mirroring assessment-service's Task 13.1 fix.
    "DEFAULT_THROTTLE_CLASSES": (
        "core.throttling_resilience.ResilientAnonRateThrottle",
        "core.throttling_resilience.ResilientUserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "300/min",
        # ADR 004 Section 4 — autosave endpoint, sized like
        # assessment-service's per-student answer-submit throttle (generous
        # headroom for a single-question autosave cadence).
        "essay_autosave": "120/min",
        # ADR 004 Section 4 — submit endpoint, deliberately tight: a genuine
        # submit happens once per assignment, this only needs to absorb a
        # handful of legitimate client retries on a flaky network.
        "essay_submit": "10/min",
        # Task 4.3 — malpractice-event batch ingestion, matching
        # assessment-service's own activity_log rate exactly (not in ADR
        # 004, added now that this task genuinely needs it).
        "essay_malpractice_event": "20/min",
        # ADR 004 Section 5 — submission-creation ceilings (Phase 5), both
        # fail-CLOSED (essays/throttling.py), CLAP's own defaults adopted
        # as-is per that section's reasoning: already generous relative to
        # this service's realistic per-assignment volume.
        "essay_submit_hourly_student": "500/hour",
        "essay_submit_hourly_institution": "5000/hour",
    },
}

SIMPLE_JWT = {
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.environ.get("JWT_SIGNING_KEY", SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_CLAIM": "user_id",
}

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        # socket_timeout/socket_connect_timeout: a fully down Redis fails
        # fast, but a hung/unresponsive one would otherwise block a request
        # indefinitely without this (mirrors assessment-service Task 13.1).
        "OPTIONS": {
            "socket_connect_timeout": 2,
            "socket_timeout": 2,
        },
    }
}

# Celery — every service in this stack shares one Redis instance as its
# broker; without an explicit per-service queue, this service's worker
# could silently steal and drop another service's task. The worker process
# must be started with `-Q essay-service` (see docker-compose) to only
# consume from this queue.
CELERY_BROKER_URL = REDIS_URL
# Redis-outage-at-dispatch gap follow-up — real gap found via live testing:
# with a result backend configured, celery.backends.redis runs its OWN
# separate reconnect loop (hardcoded 20 retries, ~1s apart, ~20-25s total)
# completely independent of broker_connection_max_retries/timeout below —
# confirmed live: a single evaluate_essay.delay() call during a real Redis
# outage blocked for ~25s inside celery.backends.redis before the broker
# side (the actual dispatch, wrapped by scoring.py's _BROKER_ERRORS) ever
# got a chance to fail fast. A real 6-call admin-close request took 171s
# end-to-end because of this. No code anywhere in essay-service calls
# AsyncResult/.get()/.result on a dispatched task, and no task uses
# chains/chords/groups that need result tracking (confirmed via a repo-wide
# grep, zero matches) — every task here is fire-and-forget by design. The
# result backend is therefore pure overhead with no reader, and removing it
# eliminates this entire retry loop rather than tuning a mechanism nothing
# uses.
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_DEFAULT_QUEUE = "essay-service"
# Task 18.2 — real gap found via live chaos testing: evaluate_essay's own
# acks_late=True (essays/tasks.py) only causes prompt redelivery if the
# Redis transport's own visibility_timeout is shorter than the default
# 3600s (1 hour) — confirmed live: with acks_late alone and no override
# here, a worker killed mid-task left its submission stuck at
# LLM_PROCESSING for the full duration of this test (15s+, nowhere near
# the default hour, but the mechanism was clearly not firing promptly)
# until this setting was added. 600s (10 minutes) is comfortably above
# every task's own hard time_limit in this file (90s is the longest,
# evaluate_essay's own) — long enough that a task legitimately still
# running is never mistaken for lost and redelivered prematurely (which
# would risk a genuine double-run), short enough that a real crash's
# worst-case stuck duration is minutes, not an hour.
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": int(os.environ.get("CELERY_VISIBILITY_TIMEOUT_SECONDS", "600"))}

# Redis-outage-at-dispatch gap follow-up — real gap found via live testing:
# with no override, Celery's own default (broker_connection_max_retries=100,
# each attempt backing off) made a single evaluate_essay.delay() call spend
# ~20-25s retrying an unreachable broker before finally raising
# kombu.exceptions.OperationalError (which scoring.py's _BROKER_ERRORS
# handler catches). A real admin-close request that dispatches 6 such calls
# (3 evaluate_essay + 3 check_text_similarity) therefore took ~4 real
# minutes end-to-end even though it no longer crashed — confirmed live via
# a full Redis-stopped test. These two settings bound that to a few seconds:
# a genuine outage is detected and handed off to sweep_undispatched_submissions
# (which recovers it later) quickly, instead of blocking the request. 2
# retries at a short timeout is enough to ride out a momentary blip (a
# Redis failover, a brief network hiccup) without materially slowing down
# the normal, broker-reachable case.
CELERY_BROKER_CONNECTION_TIMEOUT = 2
CELERY_BROKER_CONNECTION_MAX_RETRIES = 2

# Auto-submit/auto-close sweep (Task 4.1) — 20s matches ADR 001's 15-30s
# window, reused as-is (Task 0.1's decision). The DLQ sweeper (Task 5.3 /
# ADR 003 Decision 6) runs every 5 minutes, not 20s — its own grace-period
# filter (tasks.py's DLQ_GRACE_PERIOD_MINUTES) is a defensive floor, but
# the schedule interval itself is what actually paces automatic retries;
# a 20s sweep interval would hammer a still-failing entry roughly 15x
# within one 5-minute grace window instead of once.
# Phase 13, Task 13.1 — the hour (UTC, 0-23) the automatic daily
# pipeline-health summary email is dispatched. Read here, ahead of
# CELERY_BEAT_SCHEDULE below, so that block can reference it directly.
PIPELINE_DAILY_SUMMARY_HOUR_UTC = int(os.environ.get("PIPELINE_DAILY_SUMMARY_HOUR_UTC", "6"))

CELERY_BEAT_SCHEDULE = {
    "sweep-expired-assignments": {
        "task": "essays.tasks.sweep_expired_assignments",
        "schedule": 20.0,
    },
    "sweep-expired-attempts": {
        "task": "essays.tasks.sweep_expired_attempts",
        "schedule": 20.0,
    },
    "sweep-dlq-entries": {
        "task": "essays.tasks.sweep_dlq_entries",
        "schedule": 300.0,
    },
    # Real gap found live: a submission whose evaluate_essay dispatch
    # itself failed (Redis unreachable at the exact moment a student
    # submitted — essays/scoring.py's _create_and_dispatch_submissions)
    # has no EssayFailedJob row for sweep-dlq-entries above to ever find,
    # since _record_dlq is only ever called from inside evaluate_essay's
    # own exception handling, which never got to run. 60s (tighter than
    # the DLQ sweep's own 5 minutes, looser than the 20s expiry sweeps) —
    # nothing has even started for these submissions yet, so recovery
    # should be prompt, but this is a rare outage-triggered edge case, not
    # routine work needing a tight loop.
    "sweep-undispatched-submissions": {
        "task": "essays.tasks.sweep_undispatched_submissions",
        "schedule": 60.0,
    },
    # Phase 13, Task 13.1 — "optional": harmless to always schedule, since
    # the task itself no-ops (logs, doesn't send) when
    # ALERT_EMAIL_RECIPIENTS is empty, matching that "optional" framing
    # without needing conditional beat-schedule registration.
    "send-daily-pipeline-summary": {
        "task": "essays.tasks.send_pipeline_health_summary_email",
        "schedule": crontab(hour=PIPELINE_DAILY_SUMMARY_HOUR_UTC, minute=0),
    },
}

# ── LLM Evaluation Pipeline (Phase 5, ADR 003) ──────────────────────────────
# OPENAI_QUOTA_* default to CLAP's own verified numbers (essays/quota_tracker.py's
# own docstring) — a placeholder, not this platform's real tier. ADR 004
# Section 3 names substituting the real provisioned tier's actual RPM/TPM
# limits here as a blocking prerequisite before this pipeline goes to
# production; local dev/test never makes a real call (every test mocks
# essays.llm_client.call_openai_evaluate), so building against the
# placeholder does not block Phase 5's own implementation or testing.
OPENAI_API_KEYS = [k.strip() for k in os.environ.get("OPENAI_API_KEYS", "").split(",") if k.strip()]
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
OPENAI_QUOTA_RPM_LIMIT = int(os.environ.get("OPENAI_QUOTA_RPM_LIMIT", "500"))
OPENAI_QUOTA_RPD_LIMIT = int(os.environ.get("OPENAI_QUOTA_RPD_LIMIT", "10000"))
OPENAI_QUOTA_TPM_LIMIT = int(os.environ.get("OPENAI_QUOTA_TPM_LIMIT", "800000"))
OPENAI_QUOTA_TPD_LIMIT = int(os.environ.get("OPENAI_QUOTA_TPD_LIMIT", "10000000"))
OPENAI_QUOTA_SAFETY_MARGIN = float(os.environ.get("OPENAI_QUOTA_SAFETY_MARGIN", "0.90"))

# ── Text-Similarity / Plagiarism (Task 5.4, ADR 002 Decision 4) ────────────
# Algorithm: word 5-gram containment (essays/tasks.py::_shingle_containment),
# not difflib.SequenceMatcher. Two earlier whole-text sequence-alignment
# attempts were both wrong for this use: the default (autojunk=True) scored
# a realistic partial copy at 1.1% (accuracy bug), and disabling autojunk
# made every comparison ~100x slower (~600ms each, ~1 hour per 2,000 peers).
# Shingle containment is order-independent and ~0.02ms per comparison at
# 2,000 peers.
#
# Threshold 0.30 = share of the student's own 5-word runs also found in a
# peer's essay. Measured on synthetic essays (not real student data):
# honest independent writing on the same topic scored 0%, a weak partial
# copy (2 of 5 sentences, with own intro/outro) scored 34%, a stronger one
# (3 of 5) scored 62%, a full copy with reordered paragraphs scored 79%.
# 0.30 catches the weak partial copy with a wide margin above the honest
# baseline. Explicitly NOT a settled number — synthetic data only, and
# common 5-word phrases on a narrow prompt could produce false positives on
# real essays. Tune against real submissions before trusting it; a flag is
# a review trigger for a human, not a verdict.
ESSAY_TEXT_SIMILARITY_THRESHOLD = float(os.environ.get("ESSAY_TEXT_SIMILARITY_THRESHOLD", "0.30"))
ESSAY_TEXT_SIMILARITY_MIN_LENGTH = int(os.environ.get("ESSAY_TEXT_SIMILARITY_MIN_LENGTH", "50"))

# ── User Service Client (Phase 3 — roster snapshot at assignment creation) ──
# Not present in Phase 1/2 (no user-service dependency existed yet) — added
# now that Task 3.1 genuinely needs it, mirroring assessment-service's own
# settings exactly (core/user_service_client.py is a verbatim copy of theirs).
USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://user-service:8000")
USER_SERVICE_TIMEOUT = int(os.environ.get("USER_SERVICE_TIMEOUT", "3"))
USER_SERVICE_RETRIES = int(os.environ.get("USER_SERVICE_RETRIES", "2"))
USER_SERVICE_RETRY_BACKOFF = float(os.environ.get("USER_SERVICE_RETRY_BACKOFF", "0.3"))

# ── Email Delivery (Phase 11, Tasks 11.1/11.2 — report delivery) ───────────
# The Phase 11 tracker's own text names reusing notification-service's
# "existing outbox/delivery integration" — verified directly against that
# service's real code (Task 11 research pass) and found factually wrong:
# notification-service's Notification model is purely in-app (user_id,
# institution_id, type, title, body, is_read); nothing there sends email,
# there is no EMAIL_BACKEND/SMTP config, and no other service calls it for
# email. The only real SMTP precedent anywhere in this monorepo is
# user-service's own settings (core/settings.py there) — mirrored here
# verbatim rather than inventing a new pattern, and used directly via
# Django's own mail framework instead of a nonexistent notification-service
# integration.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "False") == "True"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
# SERVER_EMAIL — Django's own convention for mail_admins()/mail_managers()
# alerts specifically, mirrored from user-service verbatim (its only use
# there). NOT used for send_essay_report_email (essays/tasks.py): a real
# user-facing email, which correctly uses DEFAULT_FROM_EMAIL below instead
# — a real gap found by Phase 11's own final-audit round: the first
# version of that task passed SERVER_EMAIL as its own from_email, borrowing
# the "server error alert" identity for a genuine student-facing email.
# Django's own send_mail() already defaults to DEFAULT_FROM_EMAIL when no
# from_email is given — essay-service simply never needed the setting to
# exist before this phase introduced its first real outbound email.
SERVER_EMAIL = EMAIL_HOST_USER or "noreply@spark.local"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "noreply@spark.local")
EMAIL_SUBJECT_PREFIX = "[SPARK] "

# ── Notifications Module (Phase 13, Task 13.1) — pipeline-health alerts ────
# Task 13.1's own tracker text says the daily summary should "reuse
# notification-service's existing send mechanism (per Non-Negotiable
# Constraint §5's spirit: don't build a second email-sending path)" — a
# claim checked directly against real code/text before writing anything
# here, and found doubly wrong: (1) notification-service has no
# email-sending capability at all — already verified once for Phase 11's
# own delivery tracking (see essays/reports.py's own module docstring),
# unchanged since; (2) Non-Negotiable Constraint §5 itself says something
# completely unrelated ("No LLM call is ever made synchronously in a
# student-facing request") — it has nothing to do with email at all, so
# the tracker's own citation doesn't even support its own claim.
#
# Also researched whether essay-service could dynamically email the
# platform's real super-admin users instead of a static list: auth-service
# (not user-service) is the only service that owns User/role=super_admin/
# email; its own GET /api/auth/super-admins/ requires an IT-role JWT a
# Celery beat task has no session to forward, and no internal
# (X-Service-Key) endpoint anywhere exposes this list to another service —
# building one would be new, unplanned cross-service work on auth-service,
# outside this phase's own essay-service-only scope. The one real,
# already-proven precedent anywhere on this platform for "alert admins by
# email" is user-service's own dead-letter outbox (core/settings.py
# there): a static, env-var-configured recipient list, not a dynamic
# lookup. Followed here for the same reason, same variable name for
# cross-service consistency — a plain list of addresses (not user-service's
# own (name, email) ADMINS tuples, since this uses send_mail() directly
# for richer HTML content, not mail_admins()).
ALERT_EMAIL_RECIPIENTS = [
    addr.strip() for addr in os.environ.get("ALERT_EMAIL_RECIPIENTS", "").split(",") if addr.strip()
]

# Tiered alert thresholds — Task 13.1's own explicit instruction: CLAP's
# example numbers (DLQ >50=P1/>10=P2, oldest-unresolved >30min=P1/>5min=P2,
# >25 failure-events=P2 in the window) are "a starting reference, not a
# mandate", to be re-derived against this service's own expected volume.
# Kept as settings (Task 0.3's own established discipline — "a
# configurable setting, not a hardcoded literal"), not literals.
#
# DLQ unresolved count — re-derived using the same ~2x single-domain
# scale-down already used for DLQ_BULK_RETRY_CAP=50 vs CLAP's own 100
# (Phase 12): 50/2=25 (P1), 10/2=5 (P2).
PIPELINE_ALERT_DLQ_UNRESOLVED_P1 = int(os.environ.get("PIPELINE_ALERT_DLQ_UNRESOLVED_P1", "25"))
PIPELINE_ALERT_DLQ_UNRESOLVED_P2 = int(os.environ.get("PIPELINE_ALERT_DLQ_UNRESOLVED_P2", "5"))

# Oldest-unresolved age — NOT a ratio of CLAP's own 30min/5min (those
# reflect CLAP's own sweep timing, never verified to match this service's
# — Task 13.1 asks for re-derivation against THIS service's own real
# behavior). Derived instead from essay-service's own actual DLQ sweep
# mechanics (essays/tasks.py): a 5-minute grace period
# (DLQ_GRACE_PERIOD_MINUTES), a 5-minute sweep interval, and a
# DLQ_RETRY_CEILING of 5 mean an evaluate_essay entry always
# self-resolves — retried to success, or circuit-broken — within roughly
# 5 + 5*5 = ~30 minutes worst-case, with zero admin action. P2 sits
# comfortably above that natural ceiling (45min) so a healthy pipeline
# running only its own automatic cycle never trips it; P1 (180min/3h) is
# a "silently broken for hours" signal. Anything that exceeds even P2 is
# therefore either a non-evaluate_essay task — generate_essay_report,
# sweep_expired_*, check_text_similarity, none of which the automatic
# sweeper ever retries by design (see sweep_dlq_entries's own docstring)
# — genuinely awaiting manual attention, or evaluate_essay stuck for a
# reason outside its own normal cycle. Either way, genuinely alert-worthy.
PIPELINE_ALERT_DLQ_OLDEST_AGE_P1_MINUTES = int(os.environ.get("PIPELINE_ALERT_DLQ_OLDEST_AGE_P1_MINUTES", "180"))
PIPELINE_ALERT_DLQ_OLDEST_AGE_P2_MINUTES = int(os.environ.get("PIPELINE_ALERT_DLQ_OLDEST_AGE_P2_MINUTES", "45"))

# Failure-shaped audit events in the window — same single-domain
# scale-down reasoning as the DLQ count above, applied to CLAP's own 25.
# Matches the reference's own single-tier (P2-only) shape for this metric
# — not inventing an unrequested P1 tier for it.
PIPELINE_ALERT_FAILURE_EVENTS_P2 = int(os.environ.get("PIPELINE_ALERT_FAILURE_EVENTS_P2", "15"))

# Undispatched-submission oldest age (Post-18.2 follow-up, round 3) — real
# gap found auditing whether an admin would actually be PROACTIVELY
# notified of this failure mode, not just able to see a number if they
# happen to look: generate_pipeline_alerts() only ever checked DLQ/
# failure-event metrics, never this one. Deliberately age-only, no
# count-based tier at all (unlike DLQ's own count+age pair above) — a
# genuine design choice, not an oversight: this count is EXPECTED to
# spike into the hundreds or thousands during a mass-simultaneous exam
# expiry overlapping a brief outage (the exact scenario the round-2
# circuit-breaker fix made safe and bounded), and self-drains within
# minutes automatically once the broker recovers. Alerting on count alone
# would fire false alarms for exactly the case that's supposed to be
# unremarkable. Age is the metric that actually means something is wrong
# regardless of how many piled up. Derived from this service's own real
# mechanics (essays/tasks.py): UNDISPATCHED_GRACE_MINUTES=2 + a 60s sweep
# interval means a stuck submission normally self-heals within roughly
# 3 minutes of the broker recovering — P2 (10min) is triple that natural
# cycle (an early sign the broker hasn't actually come back yet); P1
# (30min) is a genuine, sustained outage, not a blip.
PIPELINE_ALERT_UNDISPATCHED_AGE_P1_MINUTES = int(os.environ.get("PIPELINE_ALERT_UNDISPATCHED_AGE_P1_MINUTES", "30"))
PIPELINE_ALERT_UNDISPATCHED_AGE_P2_MINUTES = int(os.environ.get("PIPELINE_ALERT_UNDISPATCHED_AGE_P2_MINUTES", "10"))

PIPELINE_SUMMARY_DEFAULT_WINDOW_HOURS = int(os.environ.get("PIPELINE_SUMMARY_DEFAULT_WINDOW_HOURS", "24"))

# Upper bound on the admin-controllable ?window_hours= query param
# (AdminPipelineHealthSummaryView). Without one, an arbitrarily large
# value reaches datetime.timedelta(hours=...) uncaught and raises a raw
# OverflowError ("Python int too large to convert to C int") well past
# its own documented int32-hours ceiling — an unhandled 500, not a clean
# 400, for an admin-facing operational-monitoring endpoint that already
# validates non-integer and non-positive input right next to this one.
# 8760h = 1 year, generous for any legitimate use of this tool.
PIPELINE_SUMMARY_MAX_WINDOW_HOURS = int(os.environ.get("PIPELINE_SUMMARY_MAX_WINDOW_HOURS", "8760"))

# ── Logging ──────────────────────────────────────────────────────────────────
# Structured JSON on every handler, correlation ID (core/logging_utils.py —
# nginx's own X-Request-ID) stamped on every record, mirroring the pattern
# already proven on assessment-service.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "correlation_id": {"()": "core.logging_utils.CorrelationIdLogFilter"},
    },
    "formatters": {
        "json": {"()": "core.logging_utils.JSONFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["correlation_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "botocore": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "urllib3": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# ── Sentry ────────────────────────────────────────────────────────────────────
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    try:
        import sentry_sdk

        def _attach_correlation_id(event, hint):
            from core.logging_utils import get_request_id
            request_id = get_request_id()
            if request_id:
                event.setdefault("tags", {})["request_id"] = request_id
            return event

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=ENVIRONMENT,
            traces_sample_rate=0.1,
            send_default_pii=False,
            before_send=_attach_correlation_id,
        )
    except ImportError:
        pass
