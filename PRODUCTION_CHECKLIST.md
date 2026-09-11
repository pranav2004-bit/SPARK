# SPARK — Pre-Production Checklist

Every item here is a known dev shortcut or deferred decision.
Nothing gets deployed to the real server until every box is ticked.
Add new items as you discover them during development.

---

## 1. Secrets — Replace Every Dev Value

| Item | Dev value (current) | What to do |
|---|---|---|
| `JWT_SIGNING_KEY` | `dev-jwt-key-32-chars-minimum-length-ok` | Generate with `openssl rand -hex 32`, store in secrets manager |
| `SERVICE_KEY` | `dev-service-key-32-chars-minimum-ok` | Same as above |
| `SECRET_KEY` (each service) | `dev-{service}-secret-key-replace-...` | Generate separate key per service |
| `DB_PASSWORD` (each service) | `auth_dev_password_2024` etc. | Strong random passwords, never reuse across services |
| `POSTGRES_PASSWORD` | `dev_password` | Strong password, store in secrets manager |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | Replace with R2 credentials (access key + secret key) |
| Redis | No password set | Add `requirepass` in production Redis config |
| `EMAIL_HOST_USER` | *(blank)* | Gmail address used to send dead-letter alerts — set in outbox-worker secrets |
| `EMAIL_HOST_PASSWORD` | *(blank)* | Gmail App Password (16 chars) — **never** your regular Gmail password |
| `ALERT_EMAIL_RECIPIENTS` | *(blank)* | Comma-separated list of addresses that receive dead-letter alerts, e.g. `ops@example.com,cto@example.com` |

**Rule:** No secret should exist as a plaintext value in any file committed to git. Use environment variables injected at runtime from a secrets manager (AWS Secrets Manager, Doppler, Vault, etc.).

---

## 2. Django Settings — Per Service

- [ ] `DEBUG = False` in all 7 services (includes assessment-service, added Phase 3 of `LIVETRACKER2_V1.md` — this section predates it)
- [ ] `ALLOWED_HOSTS` locked to real domain(s) — remove `"*"`
- [ ] `CORS_ALLOWED_ORIGINS` locked to real frontend domain — remove wildcard
- [ ] `SECRET_KEY` loaded from environment variable, not hardcoded
- [ ] `CONN_MAX_AGE = 0` already set — keep it (required for PgBouncer transaction mode). Confirmed: assessment-service already follows this (`core/settings.py`).

---

## 3. Database Driver Migration — psycopg2 → psycopg3

psycopg2 is in maintenance mode. Do this once when building production Docker images.
Total files to change: **21 files** — 7 `requirements.txt` + 7 `core/settings.py` + 7 `Dockerfile` (updated to include assessment-service, added Phase 3 of `LIVETRACKER2_V1.md` after this section was originally written — it still uses `psycopg2-binary` like the other 6, confirmed via its `requirements.txt`, so it needs the exact same 3-file change, not a different one)

> **STRICT RULE: All 3 changes per service must be done together in one go.**
> Changing `requirements.txt` without the Dockerfile causes `psycopg[c]` to silently fall back
> to pure Python mode — no error, no warning, just slower. You will not notice until production
> is under load. There is no partial completion of this task.

---

**Change 1 — `requirements.txt` in each service:**
```
# Remove:
psycopg2-binary

# Add:
psycopg[c]
```

**Change 2 — `core/settings.py` DATABASES block in each service:**
```python
"OPTIONS": {"prepare_threshold": 0}
```
Mandatory. Without it, psycopg3's named prepared statements break under PgBouncer transaction mode.

**Change 3 — `Dockerfile` in each service (both stages):**
```dockerfile
# Build stage — where pip install runs:
RUN apt-get update && apt-get install -y libpq-dev gcc

# Runtime stage — the final image that runs the app:
RUN apt-get update && apt-get install -y libpq5
```
`libpq-dev gcc` compiles the C extension during build.
`libpq5` is the runtime library the compiled extension links against.
Missing either one causes the silent pure Python fallback described above.

---

**auth-service (3 files):**
- [ ] `services/auth-service/requirements.txt` — swap driver
- [ ] `services/auth-service/core/settings.py` — add `prepare_threshold: 0`
- [ ] `services/auth-service/Dockerfile` — add `libpq-dev gcc` in build stage, `libpq5` in runtime stage

**user-service (3 files):**
- [ ] `services/user-service/requirements.txt` — swap driver
- [ ] `services/user-service/core/settings.py` — add `prepare_threshold: 0`
- [ ] `services/user-service/Dockerfile` — add `libpq-dev gcc` in build stage, `libpq5` in runtime stage

**resource-service (3 files):**
- [ ] `services/resource-service/requirements.txt` — swap driver
- [ ] `services/resource-service/core/settings.py` — add `prepare_threshold: 0`
- [ ] `services/resource-service/Dockerfile` — add `libpq-dev gcc` in build stage, `libpq5` in runtime stage

**practice-service (3 files):**
- [ ] `services/practice-service/requirements.txt` — swap driver
- [ ] `services/practice-service/core/settings.py` — add `prepare_threshold: 0`
- [ ] `services/practice-service/Dockerfile` — add `libpq-dev gcc` in build stage, `libpq5` in runtime stage

**notification-service (3 files):**
- [ ] `services/notification-service/requirements.txt` — swap driver
- [ ] `services/notification-service/core/settings.py` — add `prepare_threshold: 0`
- [ ] `services/notification-service/Dockerfile` — add `libpq-dev gcc` in build stage, `libpq5` in runtime stage

**analytics-service (3 files):**
- [ ] `services/analytics-service/requirements.txt` — swap driver
- [ ] `services/analytics-service/core/settings.py` — add `prepare_threshold: 0`
- [ ] `services/analytics-service/Dockerfile` — add `libpq-dev gcc` in build stage, `libpq5` in runtime stage

**assessment-service (3 files):**
- [ ] `services/assessment-service/requirements.txt` — swap driver
- [ ] `services/assessment-service/core/settings.py` — add `prepare_threshold: 0`
- [ ] `services/assessment-service/Dockerfile` — add `libpq-dev gcc` in build stage, `libpq5` in runtime stage

**After all 21 files are changed:**
- [ ] Rebuild all 7 Docker images — `docker-compose up --build` (with no service names, this also rebuilds every worker/beat container — `outbox-worker`, `outbox-cleanup`, `resource-worker`, `notification-worker`/`notification-beat`, `analytics-worker`/`analytics-beat`, `assessment-worker`/`assessment-beat` — since each builds from the same Dockerfile/context as its parent service, just a different `entrypoint`; verified by inspecting `docker-compose.dev.yml`. Only a problem if someone rebuilds by naming services individually instead of using the bare `--build` flag.)
- [ ] Run all 413 pre-assessment-service tests + assessment-service's own 267 (680 total as of `LIVETRACKER2_V1.md` Phase 13 — re-check the live count before relying on this number, it will have moved) twice (200% Rule) before promoting to production

---

## 4. PostgreSQL — Harden the Instance

> **These 3 items are linked. Do them together and restart in the correct order (documented below).**

- [ ] Remove `POSTGRES_HOST_AUTH_METHOD: md5` from `infra/docker-compose.dev.yml` — md5 was added only to fix Docker Desktop WSL host connectivity on the dev Windows machine. Production PostgreSQL 15 defaults to `scram-sha-256` which is stronger.

- [ ] Update `infra/pgbouncer/pgbouncer.ini` — change `auth_type` to match:
  ```ini
  # Change from:
  auth_type = md5

  # Change to:
  auth_type = scram-sha-256
  ```
  Reason: when PostgreSQL enforces scram-sha-256, PgBouncer's client-facing auth must also use scram-sha-256. Leaving it as md5 keeps a weaker auth method on the Django → PgBouncer leg of the connection.

- [ ] Verify PgBouncer version is 1.16 or higher — scram-sha-256 support was added in PgBouncer 1.16. If the `edoburu/pgbouncer:latest` image pulls an older version, PgBouncer will silently fail to connect to PostgreSQL after the auth change. Verify with:
  ```
  docker exec infra-pgbouncer-1 pgbouncer --version
  ```
  If below 1.16, pin to a newer explicit version tag in docker-compose.

- [ ] Restart sequence after making the above changes — order matters:
  1. Restart PostgreSQL first: `docker-compose restart postgres`
  2. Restart PgBouncer second: `docker-compose restart pgbouncer`
  3. Restart all 7 services **and every dedicated worker/beat container** last — every one of these holds its own long-lived DB connection(s) that were opened under the old auth config, and a stale worker left running after a PgBouncer/Postgres auth change means its queries start failing with auth errors (or, worse, its connection sits idle until PgBouncer recycles it) until someone notices and restarts it separately. Audited against `infra/docker-compose.dev.yml` and `docker-compose.prod.yml` directly (not assumed) — not every service has a worker/beat pair, and the ones that do aren't symmetric (some have both, `resource-service` has only a worker, three services have neither):
     ```
     docker-compose restart auth-service user-service resource-service practice-service notification-service analytics-service assessment-service outbox-worker outbox-cleanup resource-worker notification-worker notification-beat analytics-worker analytics-beat assessment-worker assessment-beat
     ```
     | Service | Has worker? | Has beat? |
     |---|---|---|
     | auth-service | — | — |
     | user-service | `outbox-worker`, `outbox-cleanup` | — |
     | resource-service | `resource-worker` | — |
     | practice-service | — | — |
     | notification-service | `notification-worker` | `notification-beat` |
     | analytics-service | `analytics-worker` | `analytics-beat` |
     | assessment-service | `assessment-worker` | `assessment-beat` |

     **Gap noticed while auditing this, since fixed:** `pgbouncer`, `outbox-worker`, and `db-backup` were entirely absent from `docker-compose.prod.yml` — confirmed real (not just a naming difference) by checking every service's own `.env.example`, which already documents `DB_HOST=pgbouncer` as the expected production value, meaning `CONN_MAX_AGE=0` (Section 2) was pointing production at a connection pooler that didn't exist in this file. All three added, mirroring `docker-compose.dev.yml`'s structure (secrets via `env_file`/`${VAR}` substitution instead of dev's hardcoded values), plus `backup_data` added to the top-level `volumes:` block and the 7 per-service DB passwords `db-backup` needs added to `infra/.env.example`. Validated via `docker compose -f docker-compose.prod.yml config` — resolves cleanly, 21 services total, exactly matching `docker-compose.dev.yml`'s 24 minus `minio`/`minio-init`/`frontend` (correctly excluded from prod: R2 replaces MinIO, frontend deploys on Vercel, per Section 9 and the nginx section's own comment). `minio`'s absence from prod was never actually a gap.

     **Second gap noticed, since fixed (2026-09-08):** `cleanup_outbox` — a fully built and tested management command whose own docstring says "Safe to schedule as a nightly cron job" — had nothing actually scheduling it, in either compose file. `DONE` outbox events accumulated in `user_db` forever. Added `outbox-cleanup` as its own container (same image as `outbox-worker`, different entrypoint: `while true; do cleanup_outbox; sleep 86400; done`) to both `docker-compose.dev.yml` and `docker-compose.prod.yml`, deliberately kept separate from `run_outbox_worker`'s loop since that loop's 30s polling is a different concern from once-daily housekeeping. Verified live: built, started, confirmed the command actually ran against the real database (`"No expired outbox events to clean up."`) and the container sat stable afterward rather than crash-looping.
  4. Verify all health endpoints return `db: ok` after restart

- [ ] Remove port `5433:5432` exposure — PostgreSQL must not be reachable from outside the Docker network in production
- [ ] Verify `max_connections = 200` is sufficient for the server's RAM (128MB shared_buffers assumes a small instance — adjust for actual server spec)
- [ ] `autovacuum = on` — already verified, keep it

---

## 5. PgBouncer

- [ ] `userlist.txt` passwords must match production DB passwords (update when DB passwords change)
- [ ] `pgbouncer.ini` passwords must match production DB passwords
- [ ] Do not expose PgBouncer port outside the Docker network
- [ ] `pool_mode = transaction` — keep as-is, correct for Django REST

---

## 6. Backup Automation

- [ ] Change `BACKUP_DIR` from `/backups` (local Docker volume) to a real offsite destination
- [ ] Point `backup.sh` to Cloudflare R2 or AWS S3 — pipe `pg_dump` output directly: `pg_dump ... | aws s3 cp - s3://bucket/path/file.dump`
- [ ] Set real R2/S3 credentials as environment variables in the backup container
- [ ] Test restore on a throwaway container before going live — `pg_restore --clean --if-exists` → verify row counts match manifest → run `python manage.py migrate --check` to confirm schema is current → tear down throwaway container
- [ ] Verify cron runs at 02:00 UTC on the production server's timezone

---

## 7. Docker Images — Production Build

- [ ] All service Dockerfiles must use multi-stage builds (dev image ≠ prod image)
- [ ] Production image must not contain: test files, dev dependencies, `.env` files, debug tools
- [ ] Driver migration Dockerfile changes — fully covered in Section 3 with exact lines per service
- [ ] Pin all base image versions (`python:3.12.4-slim`, not `python:latest`)
- [ ] Uvicorn workers = `(2 × vCPU) + 1` — set `UVICORN_WORKERS` env var based on actual server CPU count
- [ ] Add `ARG GIT_SHA` and `ENV GIT_SHA=$GIT_SHA` to each of the 7 service Dockerfiles (runtime stage) — captures the git SHA passed by CI via `--build-arg GIT_SHA=` as a runtime environment variable inside the container. Without this, the build-arg is consumed at build time only and not available at runtime — Sentry `release` tag shows `"unknown"` instead of the actual commit SHA. Confirmed: assessment-service's Dockerfile does not have this yet either (checked — same gap as the original 6). One Dockerfile edit per service is sufficient — every worker/beat container builds from its parent service's identical Dockerfile (different `entrypoint` only, verified against `docker-compose.dev.yml`), so this isn't a separate 13-Dockerfile job.

---

## 8. Nginx / Gateway

- [ ] Add TLS/SSL — HTTPS only, redirect HTTP → HTTPS
- [ ] Add real SSL certificate (Let's Encrypt or purchased cert)
- [ ] Set `server_name` to real domain — remove `_` (catch-all)
- [x] **Done (2026-08-06):** Reviewed and tightened rate limiting end to end. Findings: all active rate limiting lived solely in nginx, keyed per-client-IP (`$binary_remote_addr` — not spoofable, not a shared global bucket), with `auth_zone` (login/logout/token) and generic `api_zone` (everything else, including password-reset/admin-action endpoints) using identical values in `nginx.conf` (prod) and `nginx.dev.conf` (dev), no application-level throttling in any of the 6 active services, and 429 responses only carrying `retry_after` in the JSON body, not a real `Retry-After` header. Fixed:
  - Added a dedicated `sensitive_zone` (5r/m) for password-reset/change endpoints (`gateway/nginx.conf`, `nginx.dev.conf`) — previously shared the generic 100r/m `api_zone` bucket with everything else.
  - Tightened prod-only: `auth_zone` 10r/m→5r/m, `api_zone` 100r/m→60r/m (`gateway/nginx.conf`). Dev config (`nginx.dev.conf`) intentionally left at the looser values so local testing/integration tests stay reliable.
  - Added a real `Retry-After` HTTP header on 429s, synced with the existing JSON body value, computed per-zone via an nginx `map` (both files).
  - Added DRF-level throttling (`AnonRateThrottle`/`UserRateThrottle`, backed by the already-configured Redis cache) to all 6 services as defense-in-depth for requests that reach a service without going through nginx — explicitly exempted health-check and internal service-to-service endpoints (`throttle_classes = []`) so this can't break legitimate high-frequency internal traffic.
  - Added `NUM_PROXIES = 1` to all 6 services — without it, DRF's default throttle IP-extraction trusts a client-spoofed `X-Forwarded-For` prefix (nginx appends rather than overwrites), letting a client dodge the new per-IP DRF throttle by sending a different fake prefix on every request.
  - Added a per-account login throttle (`services/auth-service/authentication/throttling.py::LoginAttemptThrottle`, 5/min), keyed on the submitted `student_id`/`email` rather than IP — closes the gap where nginx's IP-keyed `auth_zone` can't stop an attacker spreading login guesses against one account across many source IPs.
  - See `BUGTRACKER.md` for anything that regresses.
  - **assessment-service note (added during Phase 15 doc pass):** built after this hardening pass, so it already has the equivalent protections natively rather than needing this same retrofit — `NUM_PROXIES = 1` is set in its `core/settings.py` (confirmed), and its own DRF throttle classes (`core.throttling_resilience.ResilientAnonRateThrottle`/`ResilientUserRateThrottle`, Task 13.1 — fail-open on Redis errors rather than the plain DRF classes the other 6 use) plus a dedicated per-student answer-submit throttle (Task 11.2) are already live. `gateway/nginx.conf`'s `api_zone`/`sensitive_zone`/`export_zone` already cover its routes too (Task 11.2's follow-up). Nothing outstanding here for assessment-service specifically.
- [ ] Remove or restrict access to MinIO console port (`9001`) — internal only
- [ ] Replace the `TODO: YOUR_PROD_DOMAIN_HERE` placeholder in `gateway/nginx.conf`'s `$minio_cors_origin` map with the real production domain(s) — until this is filled in, the MinIO/R2 presigned-upload proxy (port 9002) rejects CORS from every origin (fails closed, not open) and browser uploads will not work at all in production. See Section 13.
- [x] **Done (2026-06-20):** `/api/notifications/internal/` and `/api/analytics/internal/` were reachable from outside — only `/api/auth/internal/` had a `return 404;` block. Both internal endpoints relied solely on the `X-Service-Key` header with no network-level block, unlike auth-service's two-layer protection. Added matching `return 404;` blocks for both paths in `nginx.conf` and `nginx.dev.conf`. Verified live: both now return 404 from outside; internal Docker-network service-to-service calls are unaffected (they never went through nginx in the first place).

---

## 9. MinIO → Cloudflare R2

Dev uses MinIO as a local S3-compatible store. Production uses Cloudflare R2.

- [ ] Set `R2_ACCESS_KEY_ID` to real R2 access key
- [ ] Set `R2_SECRET_ACCESS_KEY` to real R2 secret key
- [ ] Set `R2_ENDPOINT_URL` to real R2 endpoint
- [ ] Set `R2_CDN_DOMAIN` to real CDN domain
- [ ] Remove MinIO and minio-init containers from production compose
- [ ] Verify file upload and download work end-to-end on production before launch announcement (part of the production smoke test in Task 10.1)

---

## 10. Run the Full Test Suite on Production-Equivalent Environment

- [ ] All 338 Phase 1–4 regression tests pass
- [ ] All 36 Task 5.1 tests pass
- [ ] All 39 Task 5.2 tests pass
- [ ] Run each suite twice (200% Rule) on production server before launch announcement

---

## 11. Monitoring and Alerting

- [ ] Set up error tracking (Sentry or equivalent) — add DSN to each service, including assessment-service (already wired to a `before_send` correlation-ID hook per Task 13.2, DSN just needs populating — see Task 15.2's own checklist item for this)
- [ ] Set up uptime monitoring on all 7 health endpoints (`/api/assessments/health/` included — already exists and is deliberately never throttled, Task 13.2)
- [ ] Set up liveness monitoring for the 7 worker/beat containers separately (`outbox-worker`, `outbox-cleanup`, `resource-worker`, `notification-worker`/`notification-beat`, `analytics-worker`/`analytics-beat`, `assessment-worker`/`assessment-beat`) — they have no HTTP endpoint to poll, so uptime monitoring on the 7 services above doesn't cover them at all; a dead worker fails silently until someone notices queued tasks aren't executing. Use `celery inspect ping` (or equivalent, e.g. Flower/a scheduled `docker ps` health check) against each, not an HTTP check. `outbox-cleanup` specifically spends most of its life asleep by design (once daily) — for it, "container is running" (a plain `docker ps` check) is the right liveness signal, not "is it actively doing work."
- [ ] Set up log aggregation — all service logs to a central store
- [ ] Set up backup failure alerting — backup.sh should notify on non-zero exit

---

## 12. Gmail SMTP — Outbox Dead-Letter Email Alerts

The outbox worker sends an alert email every time an `OutboxEvent` transitions to `dead_letter`
status (10 failed delivery attempts). A dead-letter means a student was deleted from user-service
but their auth account was not cleaned up — they can still log in. This is a security gap.
Email + the IT DLQ tab are the two safety nets. Neither replaces the other. (Moved from Super Admin to IT, 2026-08-18 — same mechanism, ownership transferred wholesale.)

> **Why it is blank in dev:** Credentials are intentionally absent from `docker-compose.dev.yml`.
> In dev, SMTP failure is caught and logged — nothing breaks. The DLQ tab still shows all events.
> You only need these set before go-live.

### Step 1 — Generate a Gmail App Password

1. Sign in to the Gmail account you want to send alerts from
2. Go to **Google Account → Security → 2-Step Verification** (must be enabled first)
3. Scroll to **App Passwords** → create one, name it `SPARK Outbox Worker`
4. Copy the 16-character password Google shows — **you cannot retrieve it again**
5. Store it immediately in your secrets manager

> **Never** use your regular Gmail account password. Google blocks SMTP logins with regular
> passwords. Only App Passwords work. If 2-Step Verification is off, App Passwords are not
> available — enable 2FA first.

### Step 2 — Set the three environment variables

Inject these into the **`outbox-worker`** container only (user-service and other services do not
send email and do not need these):

```
EMAIL_HOST_USER=your-gmail@gmail.com
EMAIL_HOST_PASSWORD=xxxx xxxx xxxx xxxx
ALERT_EMAIL_RECIPIENTS=ops@example.com,cto@example.com
```

`ALERT_EMAIL_RECIPIENTS` is a comma-separated list — add as many addresses as needed.
All listed addresses receive every dead-letter alert.

### Step 3 — Verify before launch

- [ ] Trigger a manual test: temporarily set `MAX_ATTEMPTS = 1` in `users/outbox.py`, create a
  student, kill the auth-service container so delivery fails, run the worker once, confirm the
  alert email arrives. Revert `MAX_ATTEMPTS` to `10` afterwards.
- [ ] Confirm the email subject reads: `[SPARK] Dead-letter outbox event — student <student_id>`
- [ ] Confirm the email body contains the Event ID and Student ID
- [ ] Revert `MAX_ATTEMPTS = 10` in `users/outbox.py` before go-live

### Checklist

- [ ] Gmail 2-Step Verification enabled on the sender account
- [ ] Gmail App Password generated and stored in secrets manager
- [ ] `EMAIL_HOST_USER` set in outbox-worker production environment
- [ ] `EMAIL_HOST_PASSWORD` set in outbox-worker production environment
- [ ] `ALERT_EMAIL_RECIPIENTS` set — at least one real address that someone actively monitors
- [ ] Test email received and verified before launch
- [ ] IT DLQ tab verified in production (visit `/it/dlq` — dead-letter events
  should appear in the table; Retry button should reset status to pending)

### What happens if email is misconfigured in production

The SMTP failure is caught and logged at `ERROR` level — the dead-letter record is still saved and
the worker continues. The security gap (student can still log in) persists silently until someone
checks the DLQ tab manually. This is why both safety nets must be active before go-live.

---

## 13. Resource Uploads — ClamAV Malware Scanning + CORS Restriction

Added during the resource-service upload-security hardening pass (2026-07-10): server-side
extension/MIME/size/magic-byte validation, per-section storage quota, ClamAV malware scanning,
and a CORS origin restriction on the presigned-upload proxy. All of it is live in dev except the
two items below, which need a real deployment environment to finish.

- [ ] **Set the production CORS origin.** `gateway/nginx.conf` has a `map $http_origin
  $minio_cors_origin { ... }` block with a placeholder line:
  `"https://YOUR_PROD_DOMAIN_HERE"  $http_origin;` — replace `YOUR_PROD_DOMAIN_HERE` with the
  real production frontend domain(s) before deploying. Left unset, uploads fail closed (no
  origin matches, so no CORS header is sent) rather than failing open to a wildcard `*` —
  intentional, but it means uploads simply won't work until this is filled in.
- [ ] **Let ClamAV finish its first-boot virus-DB download, then do one real test upload.**
  `docker compose up -d clamav` on a machine with real internet access; first boot downloads
  the signature database (~300MB via freshclam) before `clamd` accepts connections — can take
  several minutes. This could not be verified end-to-end during development because the sandbox
  environment used had no outbound internet access at all (confirmed via direct network test,
  not a code issue). Once `clamav` reports healthy, upload a test file as admin and confirm its
  `scan_status` flips from `pending` → `clean` in the admin UI (badge shows "Scanning…" while
  pending). If it does not flip, check `docker logs <resource-worker container>` for
  `scan_uploaded_file` task errors.
- [x] **Grandfathering confirmed safe.** Migration `resources/migrations/0006_add_scan_status.py`
  sets `scan_status="clean"` on every upload that existed before this change, so nothing already
  live disappears from students' view when this deploys — only uploads confirmed from this point
  forward go through the real `pending` → scanned gate.

---

## 14. Platform Hardening — Practice-Service Parity + Gateway Resilience

Added 2026-07-11 after an end-to-end testing pass on resource-service surfaced a class of bugs
that also existed (or risked recurring) in practice-service and the shared nginx gateway.

- [x] **`R2_PUBLIC_ENDPOINT_URL` wired into practice-service.** Same bug class as the original
  resource-service incident: the env var was set in docker-compose but never read in
  `core/settings.py`, so presigned image-upload URLs fell back to the unreachable internal
  `minio:9000` host. Fixed.
- [x] **Delete guards added to `PracticeModule`/`PracticeSection`.** Both deleted unconditionally
  with no check for children/sections/questions — worse than resource-service's equivalent gap
  (which only affected Module, not Section). Fixed to mirror resource-service's guard pattern.
- [x] **nginx gateway converted from static `upstream{}` blocks to dynamic DNS resolution**
  (`gateway/nginx.conf` and `nginx.dev.conf`). Static upstream blocks resolve backend container
  IPs once at config load and cache them for the life of the worker process — recreating any
  backend container (rebuild, redeploy) left nginx pointing at a dead IP until someone manually
  ran `nginx -s reload`, producing a 502 outage in the meantime. Replaced with `map $host $x_backend
  { default service:port; }` + `proxy_pass http://$x_backend;`, forcing per-request re-resolution
  via the existing `resolver` directive. Verified live: restarted a backend container and
  confirmed nginx routed to its new IP on the very next request with zero manual reload.
  **Trade-off accepted:** this loses upstream-block keepalive connection pooling to backends —
  acceptable since backends are on the same low-latency Docker bridge network, not the public
  internet.
- [x] **Memory limits set on the `clamav` container** (`mem_limit`/`mem_reservation` in both
  compose files) — root-cause fix for an observed OOM crash during dev testing where clamd's
  unbounded memory growth starved sibling containers. **Host RAM requirement:** production hosts
  must have at least ~2GB free beyond every other service's footprint for clamav alone
  (`mem_limit: 1500m` reserved). Undersized hosts will see clamd fail to load its full signature
  database or get OOM-killed by its own container limit — this is a real resource requirement,
  not a tunable number to shrink casually.
  **Lesson learned live:** the first attempt used `mem_limit: 1g`, which was itself too low —
  clamd got OOM-killed by that limit while building its in-memory signature index (~3.6M
  signatures across main+daily+bytecode). Corrected to `1500m`/`768m` reservation, verified by
  watching its memory climb to a stable ~670MB and pass its healthcheck. If clamav ever needs
  tuning again, raise the limit, don't lower it — a tighter cap just moves the same crash earlier.
- [x] **nginx `HEALTHCHECK` added** to both compose files (`wget --spider` against
  `http://127.0.0.1/api/auth/health/` — must use `127.0.0.1`, not `localhost`, since nginx here
  only binds IPv4 and `wget` resolves `localhost` to `::1` first and fails). Previously nginx had
  no healthcheck at all, unlike every other service — a real incident this session left it fully
  unresponsive with no automated way to detect it. Verified passing (`healthy` status).

---

## Items Added During Development

Add new items here as you discover them. Format: `- [ ] Description — discovered during Phase X`

- [ ] psycopg2 → psycopg3 migration — discovered during Phase 5 (PgBouncer setup)
- [ ] `POSTGRES_HOST_AUTH_METHOD: md5` must be removed — added only to fix Docker Desktop WSL connectivity on Windows dev machine
- [ ] `entrypoint.sh` must NOT run `manage.py migrate` in production — migrations run as a separate one-time job before services start (see LIVETRACKER Task 7.2 Stage 5.5) — discovered during Phase 7 planning
- [x] `django-migration-linter` added to each service's requirements.txt and wired into `.github/workflows/ci.yml`'s `backend-tests` job (`lintmigrations`, right after the existing missing-migrations check) — blocks unsafe migrations (DROP COLUMN, RENAME COLUMN, NOT NULL without default) from merging — discovered during Phase 7 planning, closed 2026-09-08. `django_celery_beat` and `token_blacklist` (vendored migrations from third-party packages) are excluded via `--exclude-apps`, not grandfathered — flagging someone else's package as a violation we can never fix is just noise. 21 pre-existing migrations across auth-service (3), user-service (4), resource-service (2), practice-service (2), and assessment-service (10) predate this check and are individually marked `IgnoreMigration()` in their own source, with a comment explaining why — notification-service and analytics-service needed no grandfathering (already clean). Verified empirically per service (not assumed): all 7 exit 0 against current history, and a deliberately-introduced unsafe migration (NOT NULL column, no default) was confirmed to fail with exit 1 before being discarded.
- [ ] `ARG GIT_SHA` + `ENV GIT_SHA=$GIT_SHA` required in all 7 service Dockerfiles — covered in Section 7 — discovered during Phase 7 planning (count updated to include assessment-service, added `LIVETRACKER2_V1.md` Phase 3, during the Phase 15 documentation pass)
- [ ] Zero Downtime Deployment via Expand and Contract: every schema change must be backward-compatible; schema contracts (DROP/RENAME) deployed in a separate commit after confirming zero usage of old column — discovered during Phase 7 planning
- [ ] Gmail SMTP credentials (`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `ALERT_EMAIL_RECIPIENTS`) must be set in outbox-worker production environment before go-live — credentials intentionally blank in dev; see Section 12 for full setup steps — added during outbox dead-letter alert implementation (2026-06-07)
- [ ] Production CORS domain + ClamAV first-boot DB download + live scan verification — see Section 13 — added during resource-service upload-security hardening (2026-07-10)
- [x] GitHub branch protection on `main` requires the `CI Result` status check (`.github/workflows/ci.yml`) — configured 2026-09-09 under Settings → Branches: branch pattern `main`, "Require a pull request before merging" (approvals not required — single-maintainer repo), "Require status checks to pass before merging" → `CI Result`, "Require branches to be up to date before merging". Direct pushes to `main` are no longer possible for anyone; every change now goes through a PR gated on CI. Verified end-to-end with a real test PR (this branch) rather than assumed.
  — added during CI/CD pipeline setup (2026-09-08), closed 2026-09-09
- [x] Media storage migration from local MinIO to AWS S3, replacing MinIO everywhere including local dev (not just production) — deliberate choice, so the real S3 integration gets proven before any production launch, not just simulated against MinIO's S3-compatible-but-not-identical implementation. Started 2026-09-10, closed 2026-09-10.

  **AWS side:**
  - Bucket `spark-app-media-2026` (ap-south-2), SSE-S3, Object Ownership "ACLs disabled", CORS allowing GET/PUT/HEAD from `http://localhost:3000`.
  - Block Public Access: the 2 ACL-related boxes remain checked (unused, since ACLs are disabled bucket-wide); the 2 policy-related boxes were deliberately unchecked to allow the bucket policy below — this is *not* "fully private" any more, by design.
  - Bucket policy: public `s3:GetObject` on `arn:aws:s3:::spark-app-media-2026/uploads/*` only (Sid `PublicReadUploadsOnly`) — matches MinIO's current `mc anonymous set download` behavior. Nothing outside `uploads/` is public, and no other action (list, write, delete) is public.
  - Least-privilege customer-managed IAM policy `spark-media-s3-policy` (PutObject/GetObject/DeleteObject + ListBucket, scoped to only this bucket) attached to IAM user `spark-app-s3-user`.
  - Access key `AKIASNQ6GXVPLGOG2WCI` (Access Key ID only — the secret is never recorded anywhere, including here). Note for anyone touching this later: the first access key created (`AKIASNQ6GXVPOR7FHEYX`) had its one-time secret reveal fail to render in the console (a UI glitch, not a security event) — that key was deactivated and deleted unused, and this one created fresh in its place. Separately, this key's secret was inadvertently displayed once in an AI assistant's context via an automatic file-change notification when it was added to `infra/.env`; the owner made an informed decision not to rotate it, accepting that risk knowingly rather than by oversight.

  **Code side:**
  - `storage.py` in resource-service/practice-service/assessment-service rewritten: dropped the MinIO-only `endpoint_url="http://minio:9000"` workaround and the separate "public client" hack in `generate_presigned_upload_url`. Env vars renamed from `R2_*` to boto3-standard names (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_CDN_DOMAIN`) — this also happens to be exactly what makes a later move to an EC2 instance role a zero-code change (see below).
  - Real bug found and fixed during end-to-end testing: `boto3.client("s3", region_name="ap-south-2")` with no `endpoint_url` resolves the *regular* API endpoint correctly, but `generate_presigned_url()` still falls back to the global `bucket.s3.amazonaws.com` host — which "opt-in" regions like `ap-south-2` reject outright (`IllegalLocationConstraintException`), since they only accept requests on their own regional endpoint. Fixed in all 3 services' `_get_client()` by passing an explicit `endpoint_url=f"https://s3.{region}.amazonaws.com"` and `Config(s3={"addressing_style": "virtual"})`. Confirmed via a real presigned PUT + public GET round-trip against the live bucket after the fix (200/200, body verified byte-for-byte), and all 3 services' full test suites re-run clean afterward.
  - `docker-compose.dev.yml`: removed `minio`/`minio-init` services and the `minio_data` volume; all 4 env blocks that carried `R2_*` (`resource-service`, `resource-worker`, `practice-service`, `assessment-service`) now carry the `AWS_*` vars instead. Each of those 3 services' `.env.example` updated to match. (`user-service` has its own unused copy of `storage.py` — dead code, no env vars configured for it, boto3 not even in its requirements.txt — left alone, out of scope.)
  - `gateway/nginx.dev.conf`: removed the port-9002 CORS-proxy workaround (S3's own bucket CORS + bucket policy replace it). Verified live via `nginx -t` + reload — port 9002 no longer listening.
  - Migrated the 40 pre-existing dev-upload objects (`uploads/{image,pdf}/...`) from the MinIO bucket to the new S3 bucket via a one-off boto3 script run inside the `resource-service` container (MinIO container was left running by `docker compose up` since it's no longer in the compose file — Compose doesn't delete orphaned containers/volumes automatically). All 40/40 copied, object counts verified matching on both sides. The old MinIO container, image, and volume were removed afterward once the migration was confirmed.
  - Full cross-role production-readiness sweep (2026-09-11): a real end-to-end test drove every CRUD + file action (create/upload, read/fetch, update, delete) against the live gateway (`nginx` → real HTTP, real JWTs, real S3 — nothing mocked) across all three services, for every role (`admin`, `super_admin`, `student`, `it`):
    - **resource-service**: company/section/upload create, presigned S3 PUT, confirm-upload, list, rename (PATCH), delete — as admin; student correctly blocked from write/update/delete and reads via the read-only student endpoints; `it` correctly 403s everywhere here (no CRUD access in any of the 3 services, by design).
    - **practice-service**: module/section/question create, presigned S3 PUT of a question image, PATCH-to-attach — as admin; student correctly blocked from create/update/delete; unpublished content (`is_published` defaults to `False`) correctly 404s on student read endpoints until published — verified this is the designed behavior, not a bug.
    - **assessment-service**: paper/set/section/question create, presigned S3 PUT of a set/question image, update, delete — as admin and `super_admin`; verified the ownership rule directly (a second `admin` account gets 403 editing another admin's paper; `super_admin` bypasses ownership and can edit/delete any paper); student correctly blocked from all admin-surface writes.
    - 49/49 checks passed. All test accounts, records, and S3 objects created for the sweep were cleaned up afterward; no residue left in any service's database or the bucket.

  Access keys must be retired once this app moves onto AWS compute (EC2/ECS/etc.): attach an IAM role directly to the instance instead, stop passing `aws_access_key_id`/`aws_secret_access_key` to `boto3.client()` in `storage.py` (boto3 then auto-picks-up short-lived, auto-rotating credentials from the instance itself), then deactivate and delete this IAM user's access keys.
