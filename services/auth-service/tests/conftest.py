import uuid
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache

User = get_user_model()

INSTITUTION_ID = uuid.uuid4()


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """Reset between every test — LoginAttemptThrottle (5/min per-account,
    authentication/throttling.py) has no dedicated test of its own, and
    many tests across this suite call _login() against the same fixed
    accounts (admin@test.com, superadmin@test.com). Without this, their
    throttle counters accumulate across the whole pytest process (test
    settings use LocMemCache, which persists for the process's lifetime,
    not per-test) and later tests start failing with real 429s once the
    5/min budget for an account is exhausted — a real bug in the test
    suite's isolation, not in the throttle itself, found by running the
    full suite in one continuous pass instead of smaller chunks."""
    cache.clear()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="admin@test.com",
        password="Admin@pass1",
        role="admin",
        institution_id=INSTITUTION_ID,
    )


@pytest.fixture
def student_user(db):
    return User.objects.create_user(
        email="s001@aptlogic.internal",
        password=settings.STUDENT_DEFAULT_PASSWORD,
        role="student",
        student_id="S001",
        institution_id=INSTITUTION_ID,
    )


@pytest.fixture
def super_admin_user(db):
    return User.objects.create_user(
        email="superadmin@test.com",
        password="Super@pass1",
        role="super_admin",
        institution_id=INSTITUTION_ID,
    )


@pytest.fixture
def it_user(db):
    return User.objects.create_user(
        email="it@test.com",
        password="It@pass123",
        role="it",
        institution_id=INSTITUTION_ID,
    )
