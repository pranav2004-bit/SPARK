import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _require_env(name: str, min_length: int = 0) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"Required environment variable '{name}' is missing or empty. "
            f"See services/assessment-service/.env.example for reference."
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
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost 127.0.0.1").split()

if ENVIRONMENT == "production":
    _require_env("DB_PASSWORD")
    _require_env("JWT_SIGNING_KEY", min_length=32)
    _require_env("AWS_ACCESS_KEY_ID")
    _require_env("AWS_SECRET_ACCESS_KEY")
    _require_env("AWS_S3_CDN_DOMAIN")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "rest_framework_simplejwt",
    "django_celery_beat",
    "assessments",
]

MIDDLEWARE = [
    # First in the chain — rejects an oversized request before any other
    # middleware or view code touches it. See core/middleware.py's module
    # docstring for why this is here instead of relying on Django's own
    # DATA_UPLOAD_MAX_MEMORY_SIZE (Task 12.2).
    "core.middleware.MaxBodySizeMiddleware",
    # Second — every log line for the rest of this request's lifecycle
    # (including ones emitted by SecurityMiddleware/CommonMiddleware
    # themselves) should carry the correlation ID (Task 13.2).
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
        "NAME": os.environ.get("DB_NAME", "assessment_db"),
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
    # Defense-in-depth: nginx (gateway/nginx.conf, nginx.dev.conf) is the
    # primary rate limiter. These DRF-level throttles exist for the case
    # where a request reaches this service WITHOUT going through nginx
    # (internal network access, a misrouted request, a future gateway
    # misconfig) — not as the main control. Uses the "default" cache, which
    # is Redis (see CACHES below), so counts are shared across all worker
    # processes/replicas rather than each process keeping its own counter.
    # There is exactly one trusted reverse proxy in front of this service
    # (nginx — see gateway/proxy_params.conf, which sets X-Forwarded-For).
    # Without this, DRF's throttle IP-extraction trusts the *entire* XFF
    # header value as sent, so a client could bypass per-IP throttling just
    # by sending a different fake X-Forwarded-For prefix on every request
    # (nginx appends its own $remote_addr rather than overwriting a
    # client-supplied header). NUM_PROXIES=1 tells DRF to take the second-to
    # -last entry (i.e. what nginx itself appended) as the real client IP.
    "NUM_PROXIES": 1,
    # Resilient*RateThrottle (core/throttling_resilience.py), not DRF's raw
    # classes (Task 13.1): DRF's SimpleRateThrottle.allow_request() has no
    # exception handling around its own cache.get() call, so a Redis outage
    # would otherwise 500 almost every request in the service instead of
    # just serving it unthrottled — a dependency failure cascading into a
    # near-total outage, which is exactly what this task's objective rules
    # out. Same throttle behavior in the normal case, fails open (allows
    # the request) instead of raising when Redis specifically is down.
    "DEFAULT_THROTTLE_CLASSES": (
        "core.throttling_resilience.ResilientAnonRateThrottle",
        "core.throttling_resilience.ResilientUserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "300/min",
        # Task 11.2 — per-student (assessments.throttling.AnswerSubmitRateThrottle),
        # its own budget separate from the generic "user" bucket above. See
        # that class's docstring for the full rationale behind 120/min.
        "answer_submit": "120/min",
        # Task 6.2 — per-session (assessments.throttling.ActivityLogRateThrottle),
        # not per-user. Client batches events rather than firing one call
        # per event, so this caps *batches*, not individual events — a
        # legitimate client posting every ~5-10s stays well under it.
        "activity_log": "20/min",
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
        # socket_timeout/socket_connect_timeout (Task 13.1): redis-py
        # defaults both to None (no timeout) — a fully *down* Redis fails
        # fast (connection refused), but a *hung*/unresponsive one would
        # otherwise block a request indefinitely, which is exactly the
        # "no unbounded wait on a hung dependency" case this task calls
        # out by name. core/cache_utils.py's/core/throttling_resilience.py's
        # graceful-degradation only helps once an exception is actually
        # raised — a hang that never raises would bypass all of it without
        # this.
        "OPTIONS": {
            "socket_connect_timeout": 2,
            "socket_timeout": 2,
        },
    }
}

# AWS S3 (question and option images). Deliberately named to match boto3's
# own standard credential/region env vars (AWS_ACCESS_KEY_ID,
# AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION) — storage.py's boto3.client("s3")
# call passes none of these explicitly, letting boto3's own default
# credential chain pick them up. That's what makes the later move to EC2 a
# zero-code-change swap: an IAM role attached to the instance is just
# another rung on that same chain, ahead of the explicit env vars, so the
# exact same boto3.client("s3") call keeps working — see
# PRODUCTION_CHECKLIST.md's "Items Added During Development" for the
# retirement plan.
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-south-2")
AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "spark-app-media-2026")
AWS_S3_CDN_DOMAIN = os.environ.get("AWS_S3_CDN_DOMAIN", "")
AWS_S3_PRESIGNED_URL_EXPIRY = 3600

# ClamAV — malware scanning for question/option images, mirrors
# practice-service's synchronous scan-at-write-time pattern (closes AT14/T6:
# magic-byte + malware validation, not MIME-type-only). Empty CLAMAV_HOST
# disables scanning (local dev without the clamav container) — the write
# then fails closed with a 503 rather than silently skipping the scan.
CLAMAV_HOST = os.environ.get("CLAMAV_HOST", "")
CLAMAV_PORT = int(os.environ.get("CLAMAV_PORT", "3310"))

# Celery — the auto-submit/auto-close beat sweep (ADR 001, Task 4.1) and the
# batched activity-log ingestion path. Every service in this stack shares one
# Redis instance as its Celery broker; without an explicit per-service queue,
# this service's worker can silently steal and drop another service's task.
# The worker process must be started with `-Q assessment-service` (see
# docker-compose) to only consume from this queue.
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_DEFAULT_QUEUE = "assessment-service"

# Auto-submit/auto-close sweep (ADR 001, Task 4.1). DatabaseScheduler syncs
# these static entries into django_celery_beat's PeriodicTask table on
# assessment-beat's startup — no manual DB seeding needed. 20s sits inside
# the ADR's 15-30s window.
CELERY_BEAT_SCHEDULE = {
    "sweep-expired-assignments": {
        "task": "assessments.tasks.sweep_expired_assignments",
        "schedule": 20.0,
    },
    "sweep-expired-sessions": {
        "task": "assessments.tasks.sweep_expired_sessions",
        "schedule": 20.0,
    },
    # Storage housekeeping, not exam-timing enforcement — daily is plenty
    # (ACTIVITY_LOG_RETENTION_DAYS is a 15-day window, models.py).
    "purge-old-activity-logs": {
        "task": "assessments.tasks.purge_old_activity_logs",
        "schedule": 86400.0,
    },
}

# ── user-service (roster snapshot, Task 3.1) ───────────────────────────────────
# Direct Docker-network address, bypasses nginx entirely. Mirrors
# user-service's own core/auth_client.py → auth-service pattern, except the
# call is authenticated by forwarding the calling admin's own JWT (not a
# X-Service-Key shared secret) — see core/user_service_client.py for why.
#
# Timeout trimmed from the original 5s (2026-08-17, same incident as
# AUTH_SERVICE_TIMEOUT below): a stale connection to another service should
# fail fast, not hang for a full 5s per page of a multi-page roster fetch.
# Kept a little higher than AUTH_SERVICE_TIMEOUT's 2s since this one's
# result is a hard blocker for assignment creation (wrong to cut off an
# in-flight page fetch too eagerly), not a cosmetic label.
USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://user-service:8000")
USER_SERVICE_TIMEOUT = int(os.environ.get("USER_SERVICE_TIMEOUT", "3"))
USER_SERVICE_RETRIES = int(os.environ.get("USER_SERVICE_RETRIES", "2"))
USER_SERVICE_RETRY_BACKOFF = float(os.environ.get("USER_SERVICE_RETRY_BACKOFF", "0.3"))

# ── auth-service (resolve created_by → name/email for "Created by" labels) ─────
# Same JWT-forwarding pattern as USER_SERVICE_* above, just pointed at
# auth-service instead — see core/auth_service_client.py.
#
# Timeout deliberately much lower than USER_SERVICE_TIMEOUT: that one backs
# a roster fetch the assignment flow actually needs, worth waiting on. This
# one only fills in a "Created by <name>" cosmetic label on the papers list
# — resolve_user_names already degrades to {} on any failure rather than
# raising, but a live incident (2026-08-17: a stale connection after the
# containers sat idle ~31h) showed the old 5s-per-attempt default still let
# one slow/stuck call hold up the whole papers-list response long enough
# for it to read as a hard failure rather than "loaded, just no names yet."
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://auth-service:8000")
AUTH_SERVICE_TIMEOUT = int(os.environ.get("AUTH_SERVICE_TIMEOUT", "2"))
AUTH_SERVICE_RETRIES = int(os.environ.get("AUTH_SERVICE_RETRIES", "2"))
AUTH_SERVICE_RETRY_BACKOFF = float(os.environ.get("AUTH_SERVICE_RETRY_BACKOFF", "0.3"))

# ── Logging (Task 13.2) ──────────────────────────────────────────────────────
# Structured JSON on every handler, correlation ID (core/logging_utils.py —
# nginx's own X-Request-ID, not a locally-invented one) stamped on every
# record via CorrelationIdLogFilter, whether the line comes from a view, a
# Celery task, or Django's own request-handling machinery.
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
        # Below INFO for third-party libraries — DEBUG here would drown a
        # request's own log lines in botocore/urllib3 connection-pool
        # chatter on every S3/R2 call.
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
            # Task 13.2: "trigger a deliberate error -> appears in Sentry
            # with correlation ID and full context" — default_integrations
            # (on by default; not disabled below) already auto-instruments
            # Django/Celery/logging for the "full context" half, this
            # before_send hook is specifically the correlation-ID half, so
            # the exact same ID in this service's own JSON logs and
            # nginx's access log also shows up as a searchable Sentry tag.
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
