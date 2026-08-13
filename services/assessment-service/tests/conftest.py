import uuid
import pytest
from rest_framework.test import APIClient

INSTITUTION_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
INSTITUTION_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
ADMIN_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
STUDENT_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ADMIN_B_USER_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


def _make_token(user_id, role, institution_id=None, student_id=None):
    from rest_framework_simplejwt.tokens import RefreshToken

    class FakeUser:
        pk = user_id
        id = user_id

    refresh = RefreshToken.for_user(FakeUser())
    refresh["role"] = role
    refresh["email"] = f"{role}@test.com"
    refresh["institution_id"] = str(institution_id) if institution_id else None
    refresh["student_id"] = str(student_id) if student_id else None
    refresh["is_profile_completed"] = True
    return str(refresh.access_token)


@pytest.fixture
def admin_client(db):
    token = _make_token(ADMIN_USER_ID, "admin", INSTITUTION_A)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def student_client(db):
    token = _make_token(STUDENT_USER_ID, "student", INSTITUTION_A, student_id=STUDENT_USER_ID)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def admin_b_client(db):
    token = _make_token(ADMIN_B_USER_ID, "admin", INSTITUTION_B)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture(autouse=True)
def clear_cache():
    from django.core.cache import cache
    cache.clear()
    yield
