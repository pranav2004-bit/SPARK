import os
from pathlib import Path
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _require_env(name: str, min_length: int = 0) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"Required environment variable '{name}' is missing or empty. "
            f"See services/auth-service/.env.example for reference."
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
    _require_env("INSTITUTION_ID")
    _require_env("IT_EMAIL")
    _require_env("IT_PASSWORD", min_length=8)
    _require_env("ADMIN_DEFAULT_PASSWORD", min_length=8)
    _require_env("STUDENT_DEFAULT_PASSWORD", min_length=6)
    _require_env("SUPERADMIN_DEFAULT_PASSWORD", min_length=8)

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "authentication",
]

AUTH_USER_MODEL = "authentication.User"

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
        "NAME": os.environ.get("DB_NAME", "auth_db"),
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
        "authentication.auth_backend.TokenVersionJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
    # Defense-in-depth: nginx (gateway/nginx.conf, nginx.dev.conf) is the
    # primary rate limiter and the only thing standing between the internet
    # and this service. These DRF-level throttles exist for the case where a
    # request reaches this service WITHOUT going through nginx (internal
    # network access, a misrouted request, a future gateway misconfig) — not
    # as the main control. They use the "default" cache, which is Redis (see
    # CACHES below), so counts are correctly shared across all worker
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
        # Per-account login throttle (authentication/throttling.py) — keyed
        # on the submitted student_id/email, not IP.
        "login": "5/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.environ.get("JWT_SIGNING_KEY", SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_CLAIM": "user_id",
}

# Shared secret used by other microservices for internal service-to-service calls.
# Never exposed to public clients — only sent from within the Docker network.
SERVICE_KEY = os.environ.get("SERVICE_KEY", "")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# ── Auth credentials (from env — never hardcoded) ─────────────────────────────
# IT is the platform's bootstrapped root (2026-08-20, replacing super_admin
# in that role) — IT_EMAIL/IT_PASSWORD seed the one IT account on first
# startup (create_default_it). Super Admin, Admin, and Student accounts are
# all created afterward by IT through the ordinary account-management UI,
# each assigned their own *_DEFAULT_PASSWORD on creation.
IT_EMAIL = os.environ.get("IT_EMAIL", "it@spark.test")
IT_PASSWORD = os.environ.get("IT_PASSWORD", "000346")
SUPERADMIN_DEFAULT_PASSWORD = os.environ.get("SUPERADMIN_DEFAULT_PASSWORD", "spark@123")
ADMIN_DEFAULT_PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD", "spark@123")
STUDENT_DEFAULT_PASSWORD = os.environ.get("STUDENT_DEFAULT_PASSWORD", "ANITS@123")

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
