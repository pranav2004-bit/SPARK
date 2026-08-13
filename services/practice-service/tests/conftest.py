import uuid
import pytest
from rest_framework.test import APIClient

INSTITUTION_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
INSTITUTION_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
ADMIN_USER_ID   = uuid.UUID("11111111-1111-1111-1111-111111111111")
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
def module(db):
    from practice.models import PracticeModule
    return PracticeModule.objects.create(
        name="Quantitative Aptitude",
        institution_id=INSTITUTION_A,
        is_published=True,
    )


@pytest.fixture
def section(db, module):
    from practice.models import PracticeSection
    return PracticeSection.objects.create(
        name="Number Systems",
        module=module,
        institution_id=INSTITUTION_A,
        is_published=True,
    )


@pytest.fixture
def question(db, section):
    from practice.models import PracticeQuestion
    return PracticeQuestion.objects.create(
        section=section,
        title="What is 2 + 2?",
        question_type="mcq",
        mcq_type="single",
        question_text="What is 2 + 2?",
        is_published=True,
    )


@pytest.fixture
def option_correct(db, question):
    from practice.models import PracticeQuestionOption
    return PracticeQuestionOption.objects.create(
        question=question,
        label="A",
        text="4",
        is_correct=True,
        order=1,
    )


@pytest.fixture
def option_wrong(db, question):
    from practice.models import PracticeQuestionOption
    return PracticeQuestionOption.objects.create(
        question=question,
        label="B",
        text="3",
        is_correct=False,
        order=2,
    )


@pytest.fixture
def fib_question(db, section):
    from practice.models import PracticeQuestion
    return PracticeQuestion.objects.create(
        section=section,
        title="FIB question",
        question_type="fib",
        question_text="The capital of France is ___.",
        fib_answer="Paris",
        is_published=True,
    )
