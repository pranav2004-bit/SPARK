"""
Task 5.1 — Database isolation tests.

Requires the full stack running:
  docker-compose -f infra/docker-compose.dev.yml up --build -d
  pip install psycopg2-binary pytest
  pytest tests/integration/test_task51.py -v

Tests connect to PostgreSQL via the exposed port 5433 (localhost).
Gateway tests use raw sockets (HTTP/1.1 + Connection: close) to work around
Docker Desktop WSL relay keep-alive issues on Windows.
"""
import json
import os
import socket
import time

import pytest

GATEWAY_HOST = os.environ.get("GATEWAY_HOST", "localhost")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "80"))
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5433"))
PG_SUPERUSER = "postgres"
PG_SUPERPASS = "dev_password"

# Per-service credentials matching docker-compose.dev.yml
SERVICES = [
    {
        "name": "auth",
        "db": "auth_db",
        "user": "auth_db_user",
        "password": "auth_dev_password_2024",
        "health_path": "/api/auth/health/",
    },
    {
        "name": "user",
        "db": "user_db",
        "user": "user_db_user",
        "password": "user_dev_password_2024",
        "health_path": "/api/users/health/",
    },
    {
        "name": "resource",
        "db": "resource_db",
        "user": "resource_db_user",
        "password": "resource_dev_password_2024",
        "health_path": "/api/resources/health/",
    },
    {
        "name": "practice",
        "db": "practice_db",
        "user": "practice_db_user",
        "password": "practice_dev_password_2024",
        "health_path": "/api/practice/health/",
    },
    {
        "name": "notification",
        "db": "notification_db",
        "user": "notification_db_user",
        "password": "notification_dev_password_2024",
        "health_path": "/api/notifications/health/",
    },
    {
        "name": "analytics",
        "db": "analytics_db",
        "user": "analytics_db_user",
        "password": "analytics_dev_password_2024",
        "health_path": "/api/analytics/health/",
    },
]


# ── HTTP helper using raw socket (avoids urllib3 keep-alive WSL relay issue) ──

class _HTTPResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.text = body

    def json(self):
        return json.loads(self.text)


def _http_get(path, host=None, port=None, timeout=10):
    """Raw-socket HTTP/1.1 GET with Connection: close — works through Docker WSL relay."""
    h = host or GATEWAY_HOST
    p = port or GATEWAY_PORT
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect((h, p))
    request = f"GET {path} HTTP/1.1\r\nHost: {h}\r\nConnection: close\r\n\r\n"
    s.sendall(request.encode())
    raw = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        raw += chunk
    s.close()
    header_end = raw.find(b"\r\n\r\n")
    header_bytes = raw[:header_end].decode("latin-1")
    body = raw[header_end + 4:].decode("utf-8", errors="replace")
    status_line = header_bytes.split("\r\n")[0]
    status_code = int(status_line.split(" ")[1])
    return _HTTPResponse(status_code, body)


def _pg_connect(dbname, user, password, connect_timeout=5):
    import psycopg2
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=dbname,
        user=user,
        password=password,
        connect_timeout=connect_timeout,
    )


def _is_postgres_up():
    try:
        conn = _pg_connect("postgres", PG_SUPERUSER, PG_SUPERPASS)
        conn.close()
        return True
    except Exception:
        return False


def _is_gateway_up():
    for _ in range(3):
        try:
            r = _http_get("/api/auth/health/", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


@pytest.fixture(scope="session", autouse=True)
def require_postgres():
    if not _is_postgres_up():
        pytest.skip("PostgreSQL not reachable on localhost:5433 — start the stack first")


@pytest.fixture(scope="session", autouse=True)
def require_gateway():
    if not _is_gateway_up():
        pytest.skip("Gateway not reachable — start the stack first")


# ── Smoke: each service user connects to its own DB and runs SELECT 1 ──────────

class TestSmoke:
    @pytest.mark.parametrize("svc", SERVICES, ids=[s["name"] for s in SERVICES])
    def test_service_user_can_connect_and_select_1(self, svc):
        conn = _pg_connect(svc["db"], svc["user"], svc["password"])
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            result = cur.fetchone()
            assert result == (1,), f"{svc['name']}: SELECT 1 returned {result}"
        finally:
            conn.close()


# ── Sanity: Django tables present in each database ─────────────────────────────

class TestSanity:
    @pytest.mark.parametrize("svc", SERVICES, ids=[s["name"] for s in SERVICES])
    def test_django_tables_exist(self, svc):
        conn = _pg_connect(svc["db"], svc["user"], svc["password"])
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            )
            tables = [row[0] for row in cur.fetchall()]
            assert "django_migrations" in tables, (
                f"{svc['name']}: django_migrations missing. Tables: {tables}"
            )
            assert "django_content_type" in tables, (
                f"{svc['name']}: django_content_type missing"
            )
        finally:
            conn.close()


# ── Functionality: CRUD with service user ─────────────────────────────────────

class TestFunctionality:
    @pytest.mark.parametrize("svc", SERVICES, ids=[s["name"] for s in SERVICES])
    def test_service_user_can_crud(self, svc):
        conn = _pg_connect(svc["db"], svc["user"], svc["password"])
        conn.autocommit = False
        try:
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS _task51_crud_test "
                "(id serial PRIMARY KEY, val text NOT NULL)"
            )
            cur.execute("INSERT INTO _task51_crud_test (val) VALUES (%s) RETURNING id", ("hello",))
            row_id = cur.fetchone()[0]
            cur.execute("SELECT val FROM _task51_crud_test WHERE id = %s", (row_id,))
            assert cur.fetchone()[0] == "hello"
            cur.execute("UPDATE _task51_crud_test SET val = %s WHERE id = %s", ("world", row_id))
            cur.execute("SELECT val FROM _task51_crud_test WHERE id = %s", (row_id,))
            assert cur.fetchone()[0] == "world"
            cur.execute("DELETE FROM _task51_crud_test WHERE id = %s", (row_id,))
            cur.execute("SELECT COUNT(*) FROM _task51_crud_test WHERE id = %s", (row_id,))
            assert cur.fetchone()[0] == 0
            conn.rollback()
        finally:
            conn.rollback()
            conn.close()
            cleanup = _pg_connect(svc["db"], PG_SUPERUSER, PG_SUPERPASS)
            cleanup.autocommit = True
            cleanup.cursor().execute("DROP TABLE IF EXISTS _task51_crud_test")
            cleanup.close()


# ── Integration: REST-only inter-service communication ────────────────────────

class TestIntegration:
    def test_auth_service_health_via_gateway(self):
        r = _http_get("/api/auth/health/")
        assert r.status_code == 200
        data = r.json()
        assert data.get("data", {}).get("db") == "ok", f"auth health db != ok: {data}"

    def test_user_service_health_via_gateway(self):
        r = _http_get("/api/users/health/")
        assert r.status_code == 200
        data = r.json()
        assert data.get("data", {}).get("db") == "ok", f"user health db != ok: {data}"


# ── Negative: cross-service DB access is denied ───────────────────────────────

class TestNegative:
    def test_auth_user_cannot_connect_to_user_db(self):
        import psycopg2
        with pytest.raises(psycopg2.OperationalError) as exc_info:
            conn = _pg_connect("user_db", "auth_db_user", "auth_dev_password_2024")
            conn.close()
        err = str(exc_info.value).lower()
        assert any(k in err for k in ["permission denied", "password", "fatal"]), (
            f"Expected auth-denied error, got: {err}"
        )

    def test_user_user_cannot_connect_to_auth_db(self):
        import psycopg2
        with pytest.raises(psycopg2.OperationalError) as exc_info:
            conn = _pg_connect("auth_db", "user_db_user", "user_dev_password_2024")
            conn.close()
        err = str(exc_info.value).lower()
        assert any(k in err for k in ["permission denied", "password", "fatal"]), (
            f"Expected auth-denied error, got: {err}"
        )

    @pytest.mark.parametrize("svc", SERVICES, ids=[s["name"] for s in SERVICES])
    def test_wrong_password_rejected(self, svc):
        import psycopg2
        with pytest.raises(psycopg2.OperationalError):
            _pg_connect(svc["db"], svc["user"], "wrong_password_xxxxx")


# ── Edge: reconnect resilience and PostgreSQL config ──────────────────────────

class TestEdge:
    def test_reconnect_after_connection_close(self):
        svc = SERVICES[0]
        conn1 = _pg_connect(svc["db"], svc["user"], svc["password"])
        conn1.close()
        conn2 = _pg_connect(svc["db"], svc["user"], svc["password"])
        try:
            cur = conn2.cursor()
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
        finally:
            conn2.close()

    def test_max_connections_setting(self):
        conn = _pg_connect("postgres", PG_SUPERUSER, PG_SUPERPASS)
        try:
            cur = conn.cursor()
            cur.execute("SHOW max_connections")
            val = int(cur.fetchone()[0])
            assert val == 200, f"Expected max_connections=200, got {val}"
        finally:
            conn.close()


# ── Regression: all 6 health endpoints return db: ok ─────────────────────────

class TestRegression:
    @pytest.mark.parametrize("svc", SERVICES, ids=[s["name"] for s in SERVICES])
    def test_health_endpoint_returns_db_ok(self, svc):
        r = _http_get(svc["health_path"])
        assert r.status_code == 200, (
            f"{svc['name']} health returned {r.status_code}: {r.text[:200]}"
        )
        data = r.json()
        inner = data.get("data", data)
        assert inner.get("db") == "ok", (
            f"{svc['name']} health db != ok: {data}"
        )
