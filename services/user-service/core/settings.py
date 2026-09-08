import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _require_env(name: str, min_length: int = 0) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"Required environment variable '{name}' is missing or empty. "
            f"See services/user-service/.env.example for reference."
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

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "rest_framework_simplejwt",
    "users",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

APPEND_SLASH = False

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "user_db"),
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
    "DEFAULT_THROTTLE_CLASSES": (
        "core.throttling_resilience.ResilientAnonRateThrottle",
        "core.throttling_resilience.ResilientUserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "300/min",
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
    }
}

# Internal service-to-service config
# AUTH_SERVICE_URL: direct Docker-network address, bypasses nginx entirely.
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://auth-service:8000")
SERVICE_KEY = os.environ.get("SERVICE_KEY", "")

# Tuning knobs for auth-service HTTP calls.
# AUTH_SERVICE_TIMEOUT    — seconds to wait for a single attempt before giving up.
# AUTH_SERVICE_RETRIES    — total number of attempts (1 = no retry).
# AUTH_SERVICE_RETRY_BACKOFF — base seconds for exponential backoff between retries
#                              (attempt 1 waits backoff*1, attempt 2 waits backoff*2, …).
# Trimmed from the original 5s/3 (2026-08-17): a stale connection to
# auth-service should fail fast rather than hang the calling request for a
# full 5 seconds — see assessment-service/core/settings.py's
# AUTH_SERVICE_TIMEOUT comment for the incident this responds to.
AUTH_SERVICE_TIMEOUT = int(os.environ.get("AUTH_SERVICE_TIMEOUT", "3"))
AUTH_SERVICE_RETRIES = int(os.environ.get("AUTH_SERVICE_RETRIES", "2"))
AUTH_SERVICE_RETRY_BACKOFF = float(os.environ.get("AUTH_SERVICE_RETRY_BACKOFF", "0.3"))

OUTBOX_POLL_INTERVAL = int(os.environ.get("OUTBOX_POLL_INTERVAL", "30"))

# ── Email — Gmail SMTP for dead-letter outbox alerts ──────────────────────────
# Credentials come from environment variables (App Password, never committed).
# EMAIL_BACKEND can be overridden in test_settings.py to use locmem backend.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False  # mutually exclusive with TLS; always False
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
SERVER_EMAIL = EMAIL_HOST_USER or "noreply@spark.local"
EMAIL_SUBJECT_PREFIX = "[SPARK] "
# ALERT_EMAIL_RECIPIENTS — comma-separated list of addresses that receive
# dead-letter alerts via mail_admins().  Example: "ops@example.com,cto@example.com"
_alert_recipients = [
    addr.strip()
    for addr in os.environ.get("ALERT_EMAIL_RECIPIENTS", "").split(",")
    if addr.strip()
]
ADMINS = [("SPARK Admin", addr) for addr in _alert_recipients]

R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "")
R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL", "")
R2_PUBLIC_ENDPOINT_URL = os.environ.get("R2_PUBLIC_ENDPOINT_URL", R2_ENDPOINT_URL)
R2_CDN_DOMAIN = os.environ.get("R2_CDN_DOMAIN", "")
R2_PRESIGNED_URL_EXPIRY = int(os.environ.get("R2_PRESIGNED_URL_EXPIRY", "900"))

# ── Sentry ────────────────────────────────────────────────────────────────────
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=ENVIRONMENT,
            traces_sample_rate=0.1,
            send_default_pii=False,
        )
    except ImportError:
        pass
