import os

os.environ.setdefault("SECRET_KEY", "test-only-insecure-key-replace-before-production-xxxxxxxxxxxxxxxxxxxxxxx")
os.environ.setdefault("JWT_SIGNING_KEY", "test-jwt-key-32chars-minimum-length-ok")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "True")

from .settings import *  # noqa: E402, F401, F403

INSTALLED_APPS = list(INSTALLED_APPS) + ["django_migration_linter"]

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

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Django's own test-capture backend — populates django.core.mail.outbox so
# tests can assert on sent report-delivery emails without a real SMTP call.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

if os.environ.get("TEST_USE_POSTGRES"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "essay_db"),
            "USER": os.environ.get("DB_USER", "essay_db_user"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "essay-postgres"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
