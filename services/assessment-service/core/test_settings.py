import os

os.environ.setdefault("SECRET_KEY", "test-only-insecure-key-replace-before-production-xxxxxxxxxxxxxxxxxxxxxxx")
os.environ.setdefault("JWT_SIGNING_KEY", "test-jwt-key-32chars-minimum-length-ok")
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

AWS_ACCESS_KEY_ID = ""
AWS_SECRET_ACCESS_KEY = ""
# Non-empty (2026-09-12): storage.py's _get_client() guard now checks this
# instead of AWS_ACCESS_KEY_ID (production uses an EC2 instance role, so
# that var is deliberately empty there too) — tests that mock boto3.client
# directly still need this truthy to get past the guard at all.
AWS_STORAGE_BUCKET_NAME = "test-bucket"
AWS_DEFAULT_REGION = "ap-south-2"
AWS_S3_CDN_DOMAIN = ""
