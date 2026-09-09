"""
Task 5.1 — Database isolation tests.

Requires the full stack running:
  docker-compose -f infra/docker-compose.dev.yml up --build -d
  pip install pytest
  pytest tests/integration/test_task51.py -v

Gateway tests use raw sockets (HTTP/1.1 + Connection: close) to work around
Docker Desktop WSL relay keep-alive issues on Windows.

PostgreSQL has no host-published port (matches production; see
infra/docker-compose.dev.yml's "No host port — DB is internal only" comment
on the postgres service). This file's whole purpose is verifying real
per-service credential isolation — wrong passwords rejected, cross-database
access denied — which requires a genuine network + pg_hba.conf password
authentication attempt, not just "can we reach Postgres somehow". A
docker-exec straight into the Postgres container would use local-socket
trust auth, which never checks a password at all and would make every test
in this file trivially pass regardless of whether isolation is actually
configured correctly. Instead, connections are made via `docker exec` into
an already-running Django service container (PY_EXEC_CONTAINER below) —
it's already on the same internal docker network as Postgres and already
has psycopg2-binary installed, so it stands in for "a real client" making a
real TCP connection to postgres:5432, subject to the real pg_hba.conf rules.
"""
import json
import os
import socket
import subprocess
import time

import pytest

GATEWAY_HOST = os.environ.get("GATEWAY_HOST", "localhost")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "80"))
POSTGRES_HOST = "postgres"       # internal docker network hostname (spark-internal)
POSTGRES_PORT = 5432
POSTGRES_CONTAINER = "infra-postgres-1"
PY_EXEC_CONTAINER = "infra-auth-service-1"  # any Django service container — already has psycopg2-binary + network route to postgres:5432
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
    {
        "name": "assessment",
        "db": "assessment_db",
        "user": "assessment_db_user",
        "password": "assessment_dev_password_2024",
        "health_path": "/api/assessments/health/",
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


def _docker_exec(container, *args):
    cmd = ["docker", "exec", container, *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def _pg_script(dbname, user, password, body):
    """Run `body` (raw, module-level Python source) inside PY_EXEC_CONTAINER
    with a ready `conn` — a real psycopg2 connection to postgres:5432 over
    the internal docker network, authenticated with exactly the given
    user/password. A bad password or a cross-database access denial makes
    the `psycopg2.connect()` call itself raise, so the whole script exits
    non-zero with the real Postgres error on stderr — check
    `result.returncode` and `result.stderr` for those cases; `body` never
    even runs. See the module docstring for why this can't just be a
    docker-exec into the Postgres container instead.
    """
    preamble = (
        "import psycopg2\n"
        f"conn = psycopg2.connect(host={POSTGRES_HOST!r}, port={POSTGRES_PORT}, "
        f"dbname={dbname!r}, user={user!r}, password={password!r}, connect_timeout=5)\n"
    )
    return _docker_exec(PY_EXEC_CONTAINER, "python3", "-c", preamble + body)


def _is_postgres_up():
    result = subprocess.run(
        ["docker", "exec", POSTGRES_CONTAINER, "pg_isready", "-U", PG_SUPERUSER],
        capture_output=True, text=True, timeout=10,
    )
    return result.returncode == 0


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
        pytest.skip(f"PostgreSQL not reachable in container {POSTGRES_CONTAINER} — start the stack first")


@pytest.fixture(scope="session", autouse=True)
def require_gateway():
    if not _is_gateway_up():
        pytest.skip("Gateway not reachable — start the stack first")


# ── Smoke: each service user connects to its own DB and runs SELECT 1 ──────────

class TestSmoke:
    @pytest.mark.parametrize("svc", SERVICES, ids=[s["name"] for s in SERVICES])
    def test_service_user_can_connect_and_select_1(self, svc):
        result = _pg_script(svc["db"], svc["user"], svc["password"], (
            "cur = conn.cursor()\n"
            "cur.execute('SELECT 1')\n"
            "assert cur.fetchone() == (1,)\n"
            "conn.close()\n"
        ))
        assert result.returncode == 0, f"{svc['name']}: {result.stderr}"


# ── Sanity: Django tables present in each database ─────────────────────────────

class TestSanity:
    @pytest.mark.parametrize("svc", SERVICES, ids=[s["name"] for s in SERVICES])
    def test_django_tables_exist(self, svc):
        result = _pg_script(svc["db"], svc["user"], svc["password"], (
            "cur = conn.cursor()\n"
            "cur.execute(\"SELECT tablename FROM pg_tables WHERE schemaname = 'public'\")\n"
            "tables = [r[0] for r in cur.fetchall()]\n"
            "assert 'django_migrations' in tables, tables\n"
            "assert 'django_content_type' in tables, tables\n"
            "conn.close()\n"
        ))
        assert result.returncode == 0, f"{svc['name']}: {result.stderr}"


# ── Functionality: CRUD with service user ─────────────────────────────────────

class TestFunctionality:
    @pytest.mark.parametrize("svc", SERVICES, ids=[s["name"] for s in SERVICES])
    def test_service_user_can_crud(self, svc):
        try:
            result = _pg_script(svc["db"], svc["user"], svc["password"], (
                "conn.autocommit = False\n"
                "cur = conn.cursor()\n"
                "cur.execute('CREATE TABLE IF NOT EXISTS _task51_crud_test "
                "(id serial PRIMARY KEY, val text NOT NULL)')\n"
                "cur.execute('INSERT INTO _task51_crud_test (val) VALUES (%s) RETURNING id', ('hello',))\n"
                "row_id = cur.fetchone()[0]\n"
                "cur.execute('SELECT val FROM _task51_crud_test WHERE id = %s', (row_id,))\n"
                "assert cur.fetchone()[0] == 'hello'\n"
                "cur.execute('UPDATE _task51_crud_test SET val = %s WHERE id = %s', ('world', row_id))\n"
                "cur.execute('SELECT val FROM _task51_crud_test WHERE id = %s', (row_id,))\n"
                "assert cur.fetchone()[0] == 'world'\n"
                "cur.execute('DELETE FROM _task51_crud_test WHERE id = %s', (row_id,))\n"
                "cur.execute('SELECT COUNT(*) FROM _task51_crud_test WHERE id = %s', (row_id,))\n"
                "assert cur.fetchone()[0] == 0\n"
                "conn.rollback()\n"
                "conn.close()\n"
            ))
            assert result.returncode == 0, f"{svc['name']}: {result.stderr}"
        finally:
            _pg_script(svc["db"], PG_SUPERUSER, PG_SUPERPASS, (
                "conn.autocommit = True\n"
                "conn.cursor().execute('DROP TABLE IF EXISTS _task51_crud_test')\n"
                "conn.close()\n"
            ))


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
        result = _pg_script("user_db", "auth_db_user", "auth_dev_password_2024", "conn.close()\n")
        assert result.returncode != 0, "Expected cross-database connection to be denied"
        err = result.stderr.lower()
        assert any(k in err for k in ["permission denied", "password", "fatal"]), (
            f"Expected auth-denied error, got: {result.stderr}"
        )

    def test_user_user_cannot_connect_to_auth_db(self):
        result = _pg_script("auth_db", "user_db_user", "user_dev_password_2024", "conn.close()\n")
        assert result.returncode != 0, "Expected cross-database connection to be denied"
        err = result.stderr.lower()
        assert any(k in err for k in ["permission denied", "password", "fatal"]), (
            f"Expected auth-denied error, got: {result.stderr}"
        )

    @pytest.mark.parametrize("svc", SERVICES, ids=[s["name"] for s in SERVICES])
    def test_wrong_password_rejected(self, svc):
        result = _pg_script(svc["db"], svc["user"], "wrong_password_xxxxx", "conn.close()\n")
        assert result.returncode != 0, f"{svc['name']}: expected wrong password to be rejected"


# ── Edge: reconnect resilience and PostgreSQL config ──────────────────────────

class TestEdge:
    def test_reconnect_after_connection_close(self):
        svc = SERVICES[0]
        r1 = _pg_script(svc["db"], svc["user"], svc["password"], "conn.close()\n")
        assert r1.returncode == 0, r1.stderr
        # A second, separate connection — proves the server accepts a fresh
        # reconnect, not just one long-lived session.
        r2 = _pg_script(svc["db"], svc["user"], svc["password"], (
            "cur = conn.cursor()\n"
            "cur.execute('SELECT 1')\n"
            "assert cur.fetchone() == (1,)\n"
            "conn.close()\n"
        ))
        assert r2.returncode == 0, r2.stderr

    def test_max_connections_setting(self):
        result = _pg_script("postgres", PG_SUPERUSER, PG_SUPERPASS, (
            "cur = conn.cursor()\n"
            "cur.execute('SHOW max_connections')\n"
            "print(cur.fetchone()[0])\n"
            "conn.close()\n"
        ))
        assert result.returncode == 0, result.stderr
        val = int(result.stdout.strip())
        assert val == 200, f"Expected max_connections=200, got {val}"


# ── Regression: all health endpoints return db: ok ────────────────────────────

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
