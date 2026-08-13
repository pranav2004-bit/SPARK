import uuid
import pytest
from rest_framework.test import APIClient

INSTITUTION_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
INSTITUTION_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
ADMIN_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
STUDENT_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ADMIN_B_USER_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


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
def admin_client(db):
    token = _make_token(ADMIN_USER_ID, "admin", INSTITUTION_A)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def student_client(db):
    token = _make_token(STUDENT_USER_ID, "student", INSTITUTION_A)
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


@pytest.fixture
def company(db):
    from resources.models import Company
    return Company.objects.create(company_name="TCS", institution_id=INSTITUTION_A)


@pytest.fixture
def published_company(db):
    from resources.models import Company
    return Company.objects.create(company_name="Infosys", institution_id=INSTITUTION_A, is_published=True)


@pytest.fixture
def section(db, company):
    from resources.models import Section
    return Section.objects.create(company=company, section_name="Aptitude")


@pytest.fixture
def upload(db, section):
    from resources.models import Upload
    return Upload.objects.create(
        section=section,
        upload_type="pdf",
        file_url="uploads/pdf/test-file.pdf",
        original_filename="test.pdf",
        file_size_bytes=1024,
        scan_status="clean",
    )
