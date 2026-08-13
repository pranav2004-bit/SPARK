import os

os.environ.setdefault("SECRET_KEY", "test-only-insecure-key-replace-before-production-xxxxxxxxxxxxxxxxxxxxxxx")
os.environ.setdefault("JWT_SIGNING_KEY", "test-jwt-key-32chars-minimum-length-ok")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "True")

from .settings import *  # noqa: E402, F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

R2_ACCESS_KEY_ID = ""
R2_SECRET_ACCESS_KEY = ""
R2_BUCKET_NAME = ""
R2_ENDPOINT_URL = ""
R2_PUBLIC_ENDPOINT_URL = ""
R2_CDN_DOMAIN = ""

# Auth-service client — fast failure in tests; auth-service is not running.
AUTH_SERVICE_TIMEOUT = 1
AUTH_SERVICE_RETRIES = 1       # single attempt, no retry loop
AUTH_SERVICE_RETRY_BACKOFF = 0

# Email — in-memory backend so tests never hit a real SMTP server.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_HOST_USER = "test-sender@example.com"
SERVER_EMAIL = "test-sender@example.com"
ADMINS = [("Test Admin", "testadmin@example.com")]
