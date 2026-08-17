import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

INSTITUTION_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
INSTITUTION_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
ADMIN_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
STUDENT_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ADMIN_B_USER_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
# Same institution as ADMIN_USER_ID (unlike ADMIN_B_USER_ID, which is a
# different institution) — a colleague faculty account, for paper-ownership
# tests (a paper's creator vs. any other admin at the same college).
COLLEAGUE_ADMIN_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
SUPER_ADMIN_USER_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")


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
def colleague_admin_client(db):
    """A different admin at the SAME institution as admin_client — for
    paper-ownership tests (institution-scoped access already works; this
    checks the narrower "another faculty member at my own college" case)."""
    token = _make_token(COLLEAGUE_ADMIN_USER_ID, "admin", INSTITUTION_A)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def super_admin_client(db):
    token = _make_token(SUPER_ADMIN_USER_ID, "super_admin", INSTITUTION_A)
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


@pytest.fixture(autouse=True)
def _mock_resolve_user_names():
    """AdminPaperListCreateView.get enriches each paper with a "Created by
    <name>" via a real HTTP call to auth-service (auth_service_client.
    resolve_user_names). This suite's fixture JWTs (ADMIN_USER_ID etc.) are
    fake ids that don't exist in any real auth-service database, so every
    unmocked call would genuinely round-trip over the network and 401 —
    resolve_user_names degrades gracefully (returns {}) so no test breaks,
    but it doubled full-suite runtime for zero test value across every
    paper-listing test in the file, not just ones testing this feature.
    Same reasoning fetch_batch_roster is always mocked rather than hitting
    a live user-service: a unit suite shouldn't depend on a sibling
    service's liveness. Tests that specifically exercise the real
    enrichment wiring override this with their own @patch."""
    with patch("assessments.views.resolve_user_names", return_value={}):
        yield
