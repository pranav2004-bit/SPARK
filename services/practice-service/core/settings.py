import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _require_env(name: str, min_length: int = 0) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"Required environment variable '{name}' is missing or empty. "
            f"See services/practice-service/.env.example for reference."
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
    # AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY deliberately NOT required here
    # (2026-09-12) — production now runs on an EC2 instance with an attached
    # IAM role (spark-backend-ec2-role), and boto3's default credential chain
    # picks that up automatically with no explicit keys at all. Requiring
    # them here would force static keys back into production even though
    # storage.py's _get_client() never needs them. See storage.py's own
    # comment for the matching change on that side.
    _require_env("AWS_S3_CDN_DOMAIN")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "rest_framework_simplejwt",
    "practice",
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
        "NAME": os.environ.get("DB_NAME", "practice_db"),
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

# AWS S3 (question and explanation images). Deliberately named to match
# boto3's own standard credential/region env vars (AWS_ACCESS_KEY_ID,
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

# ClamAV — malware scanning for question/explanation images. Scanned
# synchronously at PATCH time (this service has no Celery worker, and
# images are small enough that a sync scan is fast). Empty CLAMAV_HOST
# disables scanning (local dev without the clamav container) — the PATCH
# then fails closed with a 503 rather than silently skipping the scan.
CLAMAV_HOST = os.environ.get("CLAMAV_HOST", "")
CLAMAV_PORT = int(os.environ.get("CLAMAV_PORT", "3310"))

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
