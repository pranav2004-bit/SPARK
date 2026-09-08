import os

# Set required env vars before importing settings (tests run without .env file)
os.environ.setdefault("SECRET_KEY", "test-only-insecure-key-replace-before-production-xxxxxxxxxxxxxxxxxxxxxxx")
os.environ.setdefault("JWT_SIGNING_KEY", "test-jwt-key-32chars-minimum-length-ok")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("INSTITUTION_ID", "1470350a-1765-41d1-92b9-bf7b040ddaf9")
os.environ.setdefault("IT_EMAIL", "it@spark.test")
os.environ.setdefault("IT_PASSWORD", "Test@000346")
os.environ.setdefault("SUPERADMIN_DEFAULT_PASSWORD", "spark@123")
os.environ.setdefault("ADMIN_DEFAULT_PASSWORD", "spark@123")
os.environ.setdefault("STUDENT_DEFAULT_PASSWORD", "ANITS@123")
os.environ.setdefault("SERVICE_KEY", "test-internal-service-key")

from .settings import *  # noqa: F401, F403

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
