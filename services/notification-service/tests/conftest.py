import uuid
import pytest
from rest_framework.test import APIClient

INSTITUTION_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
INSTITUTION_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
STUDENT_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
STUDENT_B_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ADMIN_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
TEST_SERVICE_KEY = "test-service-key-32chars-minimum-ok"


def _make_token(user_id, role, institution_id=None):
    from rest_framework_simplejwt.tokens import RefreshToken

    class FakeUser:
        pk = user_id
        id = user_id

    refresh = RefreshToken.for_user(FakeUser())
    refresh["role"] = role
    refresh["email"] = f"{role}@test.com"
    refresh["institution_id"] = str(institution_id) if institution_id else None
    refresh["student_id"] = None
    refresh["is_profile_completed"] = False
    return str(refresh.access_token)


@pytest.fixture
def student_client(db):
    token = _make_token(STUDENT_USER_ID, "student", INSTITUTION_A)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def student_b_client(db):
    token = _make_token(STUDENT_B_USER_ID, "student", INSTITUTION_A)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def admin_client(db):
    token = _make_token(ADMIN_USER_ID, "admin", INSTITUTION_A)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture
def service_client():
    """Client with X-Service-Key header for internal endpoints."""
    client = APIClient()
    client.credentials(HTTP_X_SERVICE_KEY=TEST_SERVICE_KEY)
    return client


@pytest.fixture(autouse=True)
def clear_cache():
    from django.core.cache import cache
    cache.clear()
    yield


@pytest.fixture
def notification(db):
    from notifications.models import Notification
    return Notification.objects.create(
        user_id=STUDENT_USER_ID,
        institution_id=INSTITUTION_A,
        type="announcement",
        title="Test Notification",
        body="Test body",
    )


@pytest.fixture
def read_notification(db):
    from notifications.models import Notification
    return Notification.objects.create(
        user_id=STUDENT_USER_ID,
        institution_id=INSTITUTION_A,
        type="announcement",
        title="Read Notification",
        body="Already read",
        is_read=True,
    )
