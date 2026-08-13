"""
Integration test suite — requires the full stack running via docker-compose.

  cd <repo-root>
  docker-compose -f infra/docker-compose.dev.yml up --build -d
  # Wait for all services to be healthy (~60s)
  pip install requests pytest
  pytest tests/integration/ -v

All tests are auto-skipped when the gateway is not reachable.
"""
import os
import uuid

import pytest
import requests

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost")
SERVICE_KEY = os.environ.get("SERVICE_KEY", "dev-service-key-32-chars-minimum-ok")
JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY", "dev-jwt-key-32-chars-minimum-length-ok")

INSTITUTION_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
STUDENT_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ADMIN_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _is_gateway_up():
    """Return True if the gateway responds with 200, retrying up to 5 seconds.

    Docker Desktop on Windows needs a brief moment after container (re)creation
    before port-80 forwarding is active. A single-attempt check would skip the
    entire suite immediately after `docker compose up`. Three retries with a
    short sleep handle that startup window without slowing the normal case.
    """
    import time
    for attempt in range(3):
        try:
            r = requests.get(f"{GATEWAY}/api/auth/health/", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        if attempt < 2:
            time.sleep(2)
    return False


@pytest.fixture(scope="session", autouse=True)
def require_gateway():
    if not _is_gateway_up():
        pytest.skip(
            "Gateway not reachable — start the stack first:\n"
            "  docker-compose -f infra/docker-compose.dev.yml up --build -d"
        )


def _make_jwt(user_id, role, institution_id=None):
    """Generate a valid JWT signed with the shared dev signing key.

    Includes token_type='access' and jti (JWT ID) because SimpleJWT
    validates both claims and returns 401 if either is missing.
    """
    try:
        import jwt as pyjwt  # PyJWT
    except ImportError:
        try:
            from jose import jwt as pyjwt  # python-jose
        except ImportError:
            pytest.skip("No JWT library available — install PyJWT or python-jose")

    import time
    payload = {
        "token_type": "access",          # required by SimpleJWT
        "jti": str(uuid.uuid4()),         # required by SimpleJWT (unique token ID)
        "user_id": str(user_id),
        "role": role,
        "email": f"{role}@test.com",
        "institution_id": str(institution_id) if institution_id else None,
        "student_id": None,
        "is_profile_completed": False,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(payload, JWT_SIGNING_KEY, algorithm="HS256")


@pytest.fixture(scope="session")
def student_headers():
    token = _make_jwt(STUDENT_USER_ID, "student", INSTITUTION_A)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def admin_headers():
    token = _make_jwt(ADMIN_USER_ID, "admin", INSTITUTION_A)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def service_headers():
    return {"X-Service-Key": SERVICE_KEY}
