"""
Task 5.1 — Database isolation tests.

Requires the full stack running:
  docker-compose -f infra/docker-compose.dev.yml up --build -d
  pip install pytest psycopg2-binary
  pytest tests/integration/test_task51.py -v

Gateway tests use raw sockets (HTTP/1.1 + Connection: close) to work around
Docker Desktop WSL relay keep-alive issues on Windows.

Database is real AWS RDS (spark-primary-db) — this file's whole purpose is
verifying real per-service credential isolation (wrong passwords rejected,
cross-database access denied), which requires a genuine network + password
authentication attempt, not just "can we reach Postgres somehow". Connections
are made via `docker exec` into an already-running Django service container
(PY_EXEC_CONTAINER below) — it's already on the same Docker network,
already has psycopg2-binary installed, and already has a real route to the
internet, so it stands in for "a real client" making a real TCP+TLS
connection to RDS, subject to the real per-database GRANT/REVOKE rules
(see infra/init-db.sql, replicated identically on RDS).

No RDS master credential is used anywhere in this file, on purpose — every
test operates as one of the 7 per-service users, which already have
everything they need (their own schema's CREATE privilege covers creating
*and* dropping their own test tables; SHOW max_connections needs no special
privilege at all). Never add the master password here.
"""
import json
import os
import socket
import subprocess
import time

import pytest

GATEWAY_HOST = os.environ.get("GATEWAY_HOST", "localhost")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "80"))
RDS_HOST = os.environ.get(
    "RDS_HOST", "spark-primary-db.c5y2w486ef6p.ap-south-2.rds.amazonaws.com"
)
RDS_PORT = 5432
PY_EXEC_CONTAINER = "infra-auth-service-1"  # any Django service container — already has psycopg2-binary + a real route to RDS

# Per-service credentials matching docker-compose.dev.yml / infra/pgbouncer/userlist.txt
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
    with a ready `conn` — a real psycopg2 connection to RDS over the
    internet, authenticated with exactly the given user/password, with SSL
    required (RDS enforces this server-side via rds.force_ssl). A bad
    password or a cross-database access denial makes the `psycopg2.connect()`
    call itself raise, so the whole script exits non-zero with the real
    Postgres error on stderr — check `result.returncode` and `result.stderr`
    for those cases; `body` never even runs.
    """
    preamble = (
        "import psycopg2\n"
        f"conn = psycopg2.connect(host={RDS_HOST!r}, port={RDS_PORT}, "
        f"dbname={dbname!r}, user={user!r}, password={password!r}, "
        "sslmode='require', connect_timeout=10)\n"
    )
    return _docker_exec(PY_EXEC_CONTAINER, "python3", "-c", preamble + body)


def _is_rds_up():
    svc = SERVICES[0]
    result = _pg_script(svc["db"], svc["user"], svc["password"], "conn.close()\n")
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
def require_rds():
    if not _is_rds_up():
        pytest.skip(f"RDS not reachable at {RDS_HOST} — start the stack first")


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
        # Cleanup uses the SAME per-service user, not a superuser — a user
        # with CREATE on a schema can also DROP tables it owns there.
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
            _pg_script(svc["db"], svc["user"], svc["password"], (
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
        """SHOW max_connections needs no special privilege — any authenticated
        user can read it, so this uses an ordinary per-service credential,
        never the RDS master user. RDS auto-tunes this based on instance
        class (currently ~1700 for db.m7g.xlarge) rather than a fixed value
        a local Postgres command-line flag used to set, so this checks for
        a sane floor rather than pinning an exact number that would break
        every time the instance is resized."""
        svc = SERVICES[0]
        result = _pg_script(svc["db"], svc["user"], svc["password"], (
            "cur = conn.cursor()\n"
            "cur.execute('SHOW max_connections')\n"
            "print(cur.fetchone()[0])\n"
            "conn.close()\n"
        ))
        assert result.returncode == 0, result.stderr
        val = int(result.stdout.strip())
        assert val >= 200, f"Expected max_connections >= 200, got {val}"


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
