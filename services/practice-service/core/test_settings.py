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
R2_ENDPOINT_URL = "http://localhost:9000"
R2_CDN_DOMAIN = ""
