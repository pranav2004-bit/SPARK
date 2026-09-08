import uuid
import pytest
from unittest.mock import patch
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

INSTITUTION_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
INSTITUTION_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

ADMIN_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
STUDENT_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
SUPER_ADMIN_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
ADMIN_B_USER_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
IT_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
IT_B_USER_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")


def _make_token(user_id, role, institution_id=None):
    """Generate a JWT with custom claims for a stateless JWTUser."""
    from rest_framework_simplejwt.tokens import RefreshToken as RT

    class FakeUser:
        pk = user_id
        id = user_id

    refresh = RT.for_user(FakeUser())
    refresh["role"] = role
    refresh["email"] = f"{role}@test.com"
    refresh["institution_id"] = str(institution_id) if institution_id else None
    refresh["student_id"] = None
    refresh["is_profile_completed"] = False
    return str(refresh.access_token)


@pytest.fixture
def admin_token():
    return _make_token(ADMIN_USER_ID, "admin", INSTITUTION_A)


@pytest.fixture
def student_token():
    return _make_token(STUDENT_USER_ID, "student", INSTITUTION_A)


@pytest.fixture
def super_admin_token():
    return _make_token(SUPER_ADMIN_USER_ID, "super_admin", None)


@pytest.fixture
def admin_b_token():
    return _make_token(ADMIN_B_USER_ID, "admin", INSTITUTION_B)


@pytest.fixture
def it_token():
    return _make_token(IT_USER_ID, "it", INSTITUTION_A)


@pytest.fixture
def it_b_token():
    return _make_token(IT_B_USER_ID, "it", INSTITUTION_B)


@pytest.fixture
def admin_client(admin_token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
    return client


@pytest.fixture
def student_client(student_token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {student_token}")
    return client


@pytest.fixture
def super_admin_client(super_admin_token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {super_admin_token}")
    return client


@pytest.fixture
def admin_b_client(admin_b_token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_b_token}")
    return client


@pytest.fixture
def it_client(it_token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {it_token}")
    return client


@pytest.fixture
def it_b_client(it_b_token):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {it_b_token}")
    return client


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture(autouse=True)
def mock_auth_client():
    """
    Prevent every test from making real HTTP calls to auth-service.

    auth-service is not running in the local test environment.  All functions
    in core.auth_client are patched to no-ops so that:
      - Tests that exercise student creation / deletion pass without a live
        auth-service.
      - Tests that specifically need to verify auth_client behaviour can
        override individual functions via unittest.mock.patch in their own
        scope (the autouse patch is the outermost layer).
    """
    with patch("core.auth_client.create_student_auth"), \
         patch("core.auth_client.delete_student_auth"), \
         patch("core.auth_client.set_student_active"), \
         patch("core.auth_client.delete_student_auth_by_user_id"):
        yield


@pytest.fixture
def batch(db):
    from users.models import Batch
    return Batch.objects.create(batch_name="Batch 2024", institution_id=INSTITUTION_A)


@pytest.fixture
def batch_b(db):
    from users.models import Batch
    return Batch.objects.create(batch_name="Batch B 2024", institution_id=INSTITUTION_B)


@pytest.fixture
def student(db, batch):
    from users.models import Student
    return Student.objects.create(
        user_id=STUDENT_USER_ID,
        student_id="STU001",
        department="CSE",
        batch=batch,
        institution_id=INSTITUTION_A,
    )
