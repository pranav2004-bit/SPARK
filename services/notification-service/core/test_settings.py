import os

os.environ.setdefault("SECRET_KEY", "test-only-insecure-key-replace-before-production-xxxxxxxxxxxxxxxxxxxxxxx")
os.environ.setdefault("JWT_SIGNING_KEY", "test-jwt-key-32chars-minimum-length-ok")
# Force-assign SERVICE_KEY so it always matches TEST_SERVICE_KEY in conftest,
# even when a production value is already set in the container environment.
os.environ["SERVICE_KEY"] = "test-service-key-32chars-minimum-ok"
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "True")

from .settings import *  # noqa: E402, F401, F403

# CI-only — never installed in production settings.py. Backs the
# `lintmigrations` step in .github/workflows/ci.yml.
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
