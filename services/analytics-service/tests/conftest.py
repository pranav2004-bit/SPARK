import uuid
import pytest
from rest_framework.test import APIClient

INSTITUTION_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
INSTITUTION_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
STUDENT_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ADMIN_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
SUPER_ADMIN_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
MODULE_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
QUESTION_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
COMPANY_ID = uuid.UUID("88888888-8888-8888-8888-888888888888")
RESOURCE_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")
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
def admin_client(db):
    token = _make_token(ADMIN_USER_ID, "admin", INSTITUTION_A)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def admin_b_client(db):
    token = _make_token(uuid.UUID("44444444-4444-4444-4444-444444444444"), "admin", INSTITUTION_B)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def super_admin_client(db):
    token = _make_token(SUPER_ADMIN_USER_ID, "super_admin")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture
def service_client():
    client = APIClient()
    client.credentials(HTTP_X_SERVICE_KEY=TEST_SERVICE_KEY)
    return client


@pytest.fixture(autouse=True)
def clear_cache():
    from django.core.cache import cache
    cache.clear()
    yield


@pytest.fixture
def practice_event(db):
    from analytics.models import PracticeEvent
    return PracticeEvent.objects.create(
        student_id=STUDENT_USER_ID,
        institution_id=INSTITUTION_A,
        module_id=MODULE_ID,
        question_id=QUESTION_ID,
        topic="Number Systems",
        difficulty="medium",
        is_correct=True,
    )


@pytest.fixture
def resource_event(db):
    from analytics.models import ResourceViewEvent
    return ResourceViewEvent.objects.create(
        student_id=STUDENT_USER_ID,
        institution_id=INSTITUTION_A,
        company_id=COMPANY_ID,
        resource_id=RESOURCE_ID,
    )


@pytest.fixture
def institution_snapshot(db):
    from analytics.models import InstitutionSnapshot
    from django.utils import timezone
    return InstitutionSnapshot.objects.create(
        institution_id=INSTITUTION_A,
        total_students=100,
        total_active=60,
        practice_completion_rate=72.5,
        resource_utilization_rate=45.0,
        snapshot_date=timezone.now().date(),
    )
