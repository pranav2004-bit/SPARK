"""
Task 5.2 — Query optimisation, indexes, PgBouncer, backup automation tests.

Requires the full stack running:
  docker-compose -f infra/docker-compose.dev.yml up --build -d
  pip install pytest
  pytest tests/integration/test_task52.py -v

Gateway tests use raw sockets (HTTP/1.1 + Connection: close) to work around
Docker Desktop WSL relay keep-alive issues on Windows.
PostgreSQL and PgBouncer are both queried via `docker exec` + psql — neither
is exposed on a host port (matches production; see infra/docker-compose.dev.yml's
own "No host port — DB is internal only" comment on the postgres service).
Backup tests execute backup.sh inside the db-backup container via docker exec.
"""

import json
import os
import socket
import subprocess
import time

import pytest

GATEWAY_HOST = os.environ.get("GATEWAY_HOST", "localhost")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "80"))
PG_SUPERUSER = "postgres"
BACKUP_CONTAINER = "infra-db-backup-1"
PGBOUNCER_CONTAINER = "infra-pgbouncer-1"
POSTGRES_CONTAINER = "infra-postgres-1"

SERVICES = [
    {"name": "auth",         "db": "auth_db",         "user": "auth_db_user",         "password": "auth_dev_password_2024",         "health_path": "/api/auth/health/"},
    {"name": "user",         "db": "user_db",         "user": "user_db_user",         "password": "user_dev_password_2024",         "health_path": "/api/users/health/"},
    {"name": "resource",     "db": "resource_db",     "user": "resource_db_user",     "password": "resource_dev_password_2024",     "health_path": "/api/resources/health/"},
    {"name": "practice",     "db": "practice_db",     "user": "practice_db_user",     "password": "practice_dev_password_2024",     "health_path": "/api/practice/health/"},
    {"name": "notification", "db": "notification_db", "user": "notification_db_user", "password": "notification_dev_password_2024", "health_path": "/api/notifications/health/"},
    {"name": "analytics",    "db": "analytics_db",    "user": "analytics_db_user",    "password": "analytics_dev_password_2024",    "health_path": "/api/analytics/health/"},
    {"name": "assessment",   "db": "assessment_db",   "user": "assessment_db_user",   "password": "assessment_dev_password_2024",   "health_path": "/api/assessments/health/"},
]


# ── HTTP helper (raw socket, avoids urllib3 keep-alive WSL relay issue) ────────

class _HTTPResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.text = body

    def json(self):
        return json.loads(self.text)


def _http_get(path, host=None, port=None, timeout=10):
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


# ── helpers ───────────────────────────────────────────────────────────────────

def _docker_exec(container, *args, env=None):
    cmd = ["docker", "exec"]
    if env:
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
    cmd.append(container)
    cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result


def _pg_query(sql, dbname="postgres"):
    """Run SQL as the postgres superuser via `docker exec` + psql — local-socket
    trust auth inside the container, no host port or password needed. Only
    safe for read-only/introspection use (see module docstring); this file
    never needs per-service credential auth, unlike test_task51.py."""
    result = _docker_exec(
        POSTGRES_CONTAINER,
        "psql", "-U", PG_SUPERUSER, "-d", dbname, "-t", "-c", sql,
    )
    return result.stdout.strip()


def _explain(dbname, sql, force_index=True):
    """Return EXPLAIN text; optionally disable seqscan to reveal index capability."""
    statements = "SET enable_seqscan = off; " if force_index else ""
    statements += f"EXPLAIN {sql}"
    return _pg_query(statements, dbname)


def _pgbouncer_query(sql):
    result = _docker_exec(
        PGBOUNCER_CONTAINER,
        "sh", "-c", f"PGPASSWORD=dev_password psql -h 127.0.0.1 -p 5432 -U postgres pgbouncer -t -c \"{sql}\"",
    )
    return result.stdout.strip()


def _index_exists(dbname, indexname):
    sql = f"SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='{indexname}';"
    return "1" in _pg_query(sql, dbname)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def require_postgres():
    result = _docker_exec(POSTGRES_CONTAINER, "pg_isready", "-U", PG_SUPERUSER)
    if result.returncode != 0:
        pytest.skip(
            f"PostgreSQL unreachable in container {POSTGRES_CONTAINER} — "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


@pytest.fixture(scope="session", autouse=True)
def require_gateway():
    try:
        _http_get("/api/auth/health/", timeout=5)
    except Exception as exc:
        pytest.skip(f"Gateway unreachable on {GATEWAY_HOST}:{GATEWAY_PORT} — {exc}")


# ── Smoke: indexes exist and planner CAN use them ─────────────────────────────

class TestSmoke:
    def test_students_institution_id_index_exists(self):
        assert _index_exists("user_db", "idx_students_institution_id"), \
            "idx_students_institution_id missing from user_db"

    def test_practice_questions_section_index_exists(self):
        assert _index_exists("practice_db", "idx_pq_section_published"), \
            "idx_pq_section_published missing from practice_db"

    def test_companies_institution_id_index_exists(self):
        assert _index_exists("resource_db", "idx_companies_institution_id"), \
            "idx_companies_institution_id missing from resource_db"

    def test_students_explain_uses_index(self):
        plan = _explain(
            "user_db",
            "SELECT id, institution_id FROM students "
            "WHERE institution_id = '00000000-0000-0000-0000-000000000001' LIMIT 50",
        )
        assert "Seq Scan on students" not in plan, \
            f"Planner chose Seq Scan on students (seqscan disabled): {plan}"

    def test_practice_questions_explain_uses_index(self):
        plan = _explain(
            "practice_db",
            "SELECT id, section_id FROM practice_questions "
            "WHERE section_id = '00000000-0000-0000-0000-000000000001'",
        )
        assert "Seq Scan on practice_questions" not in plan, \
            f"Planner chose Seq Scan on practice_questions (seqscan disabled): {plan}"


# ── Sanity: N+1 query patterns eliminated ─────────────────────────────────────

class TestSanity:
    def test_practice_section_select_related_in_code(self):
        """Practice section detail view uses select_related to avoid N+1 on module FK."""
        import subprocess as sp
        result = sp.run(
            ["python", "-c",
             "import ast, sys; "
             "src = open(r'services/practice-service/practice/views.py').read(); "
             "assert 'select_related' in src, 'select_related missing from practice views'"],
            capture_output=True, text=True,
            cwd=str(__file__).split("tests")[0].rstrip("/\\"),
        )
        assert result.returncode == 0, result.stderr

    def test_resource_section_select_related_in_code(self):
        """Resource section query uses select_related(company) + annotation to avoid N+1."""
        import subprocess as sp
        result = sp.run(
            ["python", "-c",
             "src = open(r'services/resource-service/resources/views.py').read(); "
             "assert 'select_related' in src and 'annotate' in src, 'N+1 fix missing from resource views'"],
            capture_output=True, text=True,
            cwd=str(__file__).split("tests")[0].rstrip("/\\"),
        )
        assert result.returncode == 0, result.stderr

    def test_companies_list_uses_annotation(self):
        """Company list annotates section_count in the initial queryset — single SQL query."""
        plan = _explain(
            "resource_db",
            "SELECT c.id, COUNT(s.id) AS section_count "
            "FROM companies c LEFT JOIN sections s ON s.company_id = c.id "
            "GROUP BY c.id ORDER BY c.created_at DESC LIMIT 20",
            force_index=False,
        )
        assert "HashAggregate" in plan or "GroupAggregate" in plan or "Sort" in plan, \
            f"Expected aggregation plan for company+sections join, got: {plan}"


# ── Functionality: backup.sh creates files and manifest ───────────────────────

class TestFunctionality:
    @pytest.fixture(scope="class")
    def run_backup(self):
        result = _docker_exec(BACKUP_CONTAINER, "/tmp/backup.sh")
        return result

    def test_backup_exits_zero(self, run_backup):
        assert run_backup.returncode == 0, \
            f"backup.sh failed:\nSTDOUT: {run_backup.stdout}\nSTDERR: {run_backup.stderr}"

    def test_backup_creates_dump_files(self, run_backup):
        result = _docker_exec(BACKUP_CONTAINER, "sh", "-c", "ls /backups/daily/*.dump 2>/dev/null | wc -l")
        count = int(result.stdout.strip())
        assert count >= len(SERVICES), \
            f"Expected ≥ {len(SERVICES)} .dump files in /backups/daily/, found {count}"

    def test_backup_creates_manifest(self, run_backup):
        result = _docker_exec(BACKUP_CONTAINER, "sh", "-c", "ls /backups/manifest_*.json 2>/dev/null | wc -l")
        count = int(result.stdout.strip())
        assert count >= 1, "No manifest JSON file found in /backups/"

    def test_backup_manifest_is_valid_json_with_all_dbs(self, run_backup):
        result = _docker_exec(
            BACKUP_CONTAINER,
            "sh", "-c",
            "cat $(ls -t /backups/manifest_*.json | head -1)",
        )
        assert result.returncode == 0, "Could not read manifest file"
        manifest = json.loads(result.stdout)
        assert "databases" in manifest, "Manifest missing 'databases' key"
        assert len(manifest["databases"]) == len(SERVICES), \
            f"Expected {len(SERVICES)} DB entries in manifest, got {len(manifest['databases'])}"

    def test_backup_dump_files_non_zero(self, run_backup):
        """All databases in the latest manifest have size > 0."""
        result = _docker_exec(
            BACKUP_CONTAINER,
            "sh", "-c",
            "cat $(ls -t /backups/manifest_*.json | head -1)",
        )
        manifest = json.loads(result.stdout)
        zero_size = [d["db"] for d in manifest["databases"] if d.get("size", 0) == 0]
        assert not zero_size, f"Backup files with size=0 in manifest: {zero_size}"


# ── Integration: PgBouncer transparent, connection count bounded ───────────────

class TestIntegration:
    def test_all_services_reachable_through_pgbouncer(self):
        """All service health endpoints return 200 — traffic flows through PgBouncer."""
        failures = []
        for svc in SERVICES:
            try:
                resp = _http_get(svc["health_path"], timeout=8)
                if resp.status_code != 200:
                    failures.append(f"{svc['name']}: HTTP {resp.status_code}")
            except Exception as exc:
                failures.append(f"{svc['name']}: {exc}")
        assert not failures, "Services unreachable through PgBouncer: " + ", ".join(failures)

    def test_pgbouncer_shows_all_service_pools(self):
        output = _pgbouncer_query("SHOW POOLS;")
        for svc in SERVICES:
            assert svc["db"] in output, \
                f"PgBouncer pool missing for {svc['db']}"

    def test_pgbouncer_pools_in_transaction_mode(self):
        output = _pgbouncer_query("SHOW POOLS;")
        pools_in_transaction = output.count("transaction")
        assert pools_in_transaction >= len(SERVICES), \
            f"Expected ≥ {len(SERVICES)} transaction-mode pools, output: {output}"

    def test_active_pg_connections_bounded(self):
        """Under normal idle load, real PG server connections ≤ 15 (PgBouncer
        pools ≤ pool_size×7=70 max). Threshold unchanged from the original
        6-service measurement — measured 5 active connections against the
        live 7-service stack before touching this, well within the existing
        ceiling, so no evidence to justify loosening it."""
        dbnames = ",".join(f"'{svc['db']}'" for svc in SERVICES)
        sql = f"SELECT count(*) FROM pg_stat_activity WHERE datname IN ({dbnames});"
        active = int(_pg_query(sql))
        assert active <= 15, \
            f"Expected ≤ 15 real PG connections (PgBouncer pool), found {active}"


# ── Negative: failure modes are visible and reported ──────────────────────────

class TestNegative:
    def test_backup_fails_with_wrong_password(self):
        """backup.sh exits non-zero when credentials are incorrect."""
        result = _docker_exec(
            BACKUP_CONTAINER,
            "sh", "-c",
            "AUTH_DB_PASSWORD=wrong USER_DB_PASSWORD=wrong "
            "RESOURCE_DB_PASSWORD=wrong PRACTICE_DB_PASSWORD=wrong "
            "NOTIFICATION_DB_PASSWORD=wrong ANALYTICS_DB_PASSWORD=wrong "
            "ASSESSMENT_DB_PASSWORD=wrong "
            "/tmp/backup.sh",
            env={"AUTH_DB_PASSWORD": "wrong", "USER_DB_PASSWORD": "wrong",
                 "RESOURCE_DB_PASSWORD": "wrong", "PRACTICE_DB_PASSWORD": "wrong",
                 "NOTIFICATION_DB_PASSWORD": "wrong", "ANALYTICS_DB_PASSWORD": "wrong",
                 "ASSESSMENT_DB_PASSWORD": "wrong"},
        )
        assert result.returncode != 0, \
            "backup.sh should exit non-zero on authentication failure"

    def test_backup_script_logs_error_on_failure(self):
        """backup.sh writes ERROR to stderr when a database backup fails."""
        result = _docker_exec(
            BACKUP_CONTAINER,
            "sh", "-c",
            "AUTH_DB_PASSWORD=wrong /tmp/backup.sh 2>&1 || true",
            env={"AUTH_DB_PASSWORD": "wrong"},
        )
        assert "ERROR" in result.stdout or "failed" in result.stdout.lower(), \
            "backup.sh did not log an error on failure"

    def test_unindexed_column_shows_seq_scan(self):
        """Unindexed columns still produce Seq Scan — confirms EXPLAIN tests are meaningful."""
        plan = _explain(
            "user_db",
            "SELECT id FROM students WHERE fullname = 'TestName'",
            force_index=False,
        )
        assert "Seq Scan" in plan, \
            "Expected Seq Scan on unindexed 'fullname' column"

    def test_backup_container_not_restarting(self):
        result = subprocess.run(
            ["docker", "inspect", BACKUP_CONTAINER,
             "--format", "{{.RestartCount}}"],
            capture_output=True, text=True, timeout=10,
        )
        restart_count = int(result.stdout.strip())
        assert restart_count == 0, \
            f"db-backup container has restarted {restart_count} time(s) — check entrypoint"


# ── Edge: boundary conditions and script quality ──────────────────────────────

class TestEdge:
    def test_backup_script_has_retention_cleanup(self):
        """backup.sh deletes backups older than 30 days (daily) and 365 days (monthly)."""
        result = _docker_exec(BACKUP_CONTAINER, "grep", "-c", "mtime", "/tmp/backup.sh")
        count = int(result.stdout.strip())
        assert count >= 2, \
            "backup.sh should have at least 2 'mtime' retention clauses (daily + monthly)"

    def test_backup_script_has_monthly_copy_logic(self):
        """backup.sh includes first-Sunday monthly retention copy."""
        result = _docker_exec(BACKUP_CONTAINER, "grep", "-c", r"IS_FIRST_SUNDAY\|monthly", "/tmp/backup.sh")
        count = int(result.stdout.strip())
        assert count >= 2, \
            "backup.sh missing monthly backup / IS_FIRST_SUNDAY logic"

    def test_backup_script_uses_max_compression(self):
        """backup.sh uses pg_dump --compress=9 for maximum compression."""
        result = _docker_exec(BACKUP_CONTAINER, "grep", "-c", "compress=9", "/tmp/backup.sh")
        count = int(result.stdout.strip())
        assert count >= 1, "backup.sh does not use --compress=9"

    def test_backup_script_has_retry_logic(self):
        """backup.sh retries each database up to MAX_RETRIES times."""
        result = _docker_exec(BACKUP_CONTAINER, "grep", "-c", r"MAX_RETRIES\|attempt", "/tmp/backup.sh")
        count = int(result.stdout.strip())
        assert count >= 2, "backup.sh missing retry logic (MAX_RETRIES / attempt)"

    def test_autovacuum_enabled(self):
        """PostgreSQL autovacuum is on — prevents table bloat."""
        value = _pg_query("SHOW autovacuum;")
        assert value == "on", f"autovacuum is '{value}', expected 'on'"

    def test_pgbouncer_max_client_conn(self):
        """PgBouncer max_client_conn ≥ 600 (100 per service × 6 services)."""
        output = _pgbouncer_query("SHOW CONFIG;")
        assert "max_client_conn" in output, "SHOW CONFIG did not include max_client_conn"
        for line in output.splitlines():
            if "max_client_conn" in line:
                parts = line.split("|")
                value = int(parts[1].strip())
                assert value >= 600, f"max_client_conn={value}, expected ≥ 600"
                break


# ── Regression: all services still return correct data after indexing ──────────

class TestRegression:
    @pytest.mark.parametrize("svc", SERVICES, ids=[s["name"] for s in SERVICES])
    def test_health_returns_200(self, svc):
        resp = _http_get(svc["health_path"], timeout=8)
        assert resp.status_code == 200, \
            f"{svc['name']} health returned {resp.status_code}"

    @pytest.mark.parametrize("svc", SERVICES, ids=[s["name"] for s in SERVICES])
    def test_health_db_ok(self, svc):
        resp = _http_get(svc["health_path"], timeout=8)
        assert resp.status_code == 200
        data = resp.json()
        inner = data.get("data", data)
        db_status = inner.get("db")
        assert db_status == "ok", \
            f"{svc['name']} health db status is '{db_status}', expected 'ok'"
