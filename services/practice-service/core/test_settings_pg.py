import os

from .test_settings import *  # noqa: F401,F403

# Integration runs only: real PostgreSQL for row locks and transaction behavior
# (LIVETRACKER4 section 3 / H3). Connection details come from the environment.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("TEST_PG_NAME", "practice_test"),
        "USER": os.environ.get("TEST_PG_USER", "postgres"),
        "PASSWORD": os.environ.get("TEST_PG_PASSWORD", ""),
        "HOST": os.environ.get("TEST_PG_HOST", "localhost"),
        "PORT": os.environ.get("TEST_PG_PORT", "5432"),
    }
}
