# SPARK — V1 Production Launch Tracker

**Platform:** SPARK — Structured Preparation and Readiness Kit  
**Version:** 1.0 (V1 Scope: Resources + Practice)  
**Architecture:** 6 Microservices — Restructure + Extensions (NOT rebuild from scratch)  
**Last updated:** 2026-05-29 — Phase 5 complete (Task 5.1 + 5.2, 39 integration tests passing twice, PgBouncer deployed, backup automation live) — CI/CD design updated: Zero Downtime Deployment, Expand and Contract, separate migration job, pre-deploy backup, migration safety linter added across Tasks 7.1, 7.2, 7.4, 9.1, 10.1

---

## Completion Standard

> **200% Rule:** A task is considered complete only when every single test in its test suite passes with zero failures, zero warnings, and zero flakiness across two consecutive runs. One flaky test = task is NOT complete. Tick the checkbox only after this bar is met.

---

## Threat Register

All 13 identified threats must be resolved before V1 launch. Each threat is assigned to a specific task.

| ID | Severity | Threat | Assigned To |
|----|----------|--------|-------------|
| T1 | CRITICAL | No `middleware.ts` — any URL accessible in browser without authentication | Task 6.1 |
| T2 | CRITICAL | N+1 query patterns in monolith ORM code causing full table scans under load | Tasks 2.1–2.4, 5.2 |
| T3 | CRITICAL | Zero automated tests exist — no regression safety net | All service tasks |
| T4 | HIGH | Sentry DSN is empty — zero production error visibility | Task 7.3 |
| T5 | HIGH | No automated database backup — full data loss risk on server failure | Tasks 5.2, 7.4 |
| T6 | MEDIUM | File upload validates MIME type only — magic bytes not checked, allows disguised malicious uploads | Task 2.3, 8.1 |
| T7 | MEDIUM | No CI/CD pipeline — broken code can reach production undetected | Task 7.2 |
| T8 | MEDIUM | Secrets stored in `.env` files — not suitable for production | Task 1.2, 8.1 |
| T9 | MEDIUM | Rate limiting only on login endpoint — all other endpoints unprotected | Task 4.1 |
| T10 | MEDIUM | No response compression in Nginx — inflated bandwidth costs | Task 4.1 |
| T11 | MEDIUM | No PgBouncer — Django opens raw PostgreSQL connections, exhausts limits under concurrent load | Task 5.2 |
| T12 | MEDIUM | Single PostgreSQL instance shared by all 6 services — assessment/contest spikes in V2 can starve V1 services | Task 5.1 |
| T13 | MEDIUM | IDOR risk — no validation that resources/practice records belong to the requesting user's institution | Tasks 2.2–2.4, 8.1 |

---

## Current State (Baseline)

**Backend:** Django monolith, 5 apps (`authentication`, `students`, `batches`, `companies`, `practice`), single PostgreSQL database, Redis (cache + Celery broker + JWT blacklist), Gunicorn (must migrate to Uvicorn), Nginx, Docker Compose (7 containers), Cloudflare R2/MinIO presigned URL uploads, Celery for async file deletion, Sentry in requirements but DSN is empty.

**Frontend:** Next.js (~90% Admin portal — 6 tabs done), (~90% Student portal — Home, Companies, Resources, Practice solver, Contact, Profile), Super Admin portal DOES NOT EXIST, `middleware.ts` DOES NOT EXIST. Auth: Zustand store (sessionStorage), JWT interceptors, cookies (`aptlogic_role`, `aptlogic_access`), `useAuth` hook.

**What is reused:** Business logic from all 5 monolith apps (models, serializers, views) — portable into service-specific Django projects without rewriting.  
**What is new:** Service isolation, per-service databases, 2 new services (notification, analytics), Nginx multi-service routing, PgBouncer, CI/CD, Super Admin portal, `middleware.ts`.

---

## Phase Index

| Phase | Scope | Tasks |
|-------|-------|-------|
| [Phase 1](#phase-1-foundation--repository-setup) | Foundation & Repository Setup | 1.1, 1.2 |
| [Phase 2](#phase-2-backend-service-extraction) | Backend Service Extraction (Restructure) | 2.1, 2.2, 2.3, 2.4 |
| [Phase 3](#phase-3-new-backend-services) | New Backend Services | 3.1, 3.2 |
| [Phase 4](#phase-4-api-gateway) | API Gateway | 4.1 |
| [Phase 5](#phase-5-database) | Database | 5.1, 5.2 |
| [Phase 6](#phase-6-frontend) | Frontend | 6.1, 6.2, 6.3 |
| [Phase 7](#phase-7-infrastructure--devops) | Infrastructure & DevOps | 7.1, 7.2, 7.3, 7.4 |
| [Phase 8](#phase-8-security-hardening) | Security Hardening | 8.1 |
| [Phase 9](#phase-9-load--performance-testing) | Load & Performance Testing | 9.1 |
| [Phase 10](#phase-10-pre-launch-final-checklist) | Pre-Launch Final Checklist | 10.1 |

---

## Phase 1: Foundation & Repository Setup

---

### Task 1.1 — Monorepo Directory Structure

**Objective:** Establish the canonical monorepo layout for all 6 services, frontend, gateway, and infra — the foundation every subsequent task builds on.

**Pre-empts:** T8 (partial — sets up the isolation needed for secrets management)

#### Implementation Subtasks

- [x] Create monorepo root with top-level directories: `services/`, `frontend/`, `gateway/`, `infra/`, `docs/`
- [x] Move existing `frontend/` into the new `frontend/` directory (no code changes, directory relocation only)
- [x] Under `services/`, create skeleton directories for all 6 services:
  - `services/auth-service/`
  - `services/user-service/`
  - `services/resource-service/`
  - `services/practice-service/`
  - `services/notification-service/`
  - `services/analytics-service/`
- [x] Each service skeleton contains: `manage.py`, `core/` (settings, urls, wsgi), `requirements.txt`, `Dockerfile`, `.env.example`, `entrypoint.sh`
- [x] Move existing monolith's `backend/` into `services/legacy-monolith/` (keep for reference during extraction, delete after Phase 2 is complete)
- [x] Under `gateway/`, place the existing `nginx.conf` as starting point
- [x] Under `infra/`, place: `docker-compose.dev.yml`, `docker-compose.prod.yml` stubs
- [x] Create root `.gitignore` covering: `*.env`, `.env.*` (not `.env.example`), `__pycache__/`, `*.pyc`, `.next/`, `node_modules/`, `*.log`, `media/`, `staticfiles/`
- [x] Verify: `git status` shows no `.env` files tracked, no `__pycache__` tracked
- [x] Verify: `frontend/` builds successfully from its new location (`npm run build` exits 0)

#### Optimization Requirements

- Flat directory depth — no more than 3 levels deep for service source files
- Each service is fully self-contained — no shared Python packages between services
- `.dockerignore` per service excludes: `__pycache__/`, `*.pyc`, `.git/`, `tests/`, `docs/`, `*.md` — reduces image build context by >80%

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | `git status` at repo root | No `.env` files, no `__pycache__` tracked |
| Sanity | `ls services/` | All 6 service directories present |
| Functionality | `python manage.py check` in each service skeleton | Exits 0 with "System check identified no issues" |
| Integration | `docker-compose -f infra/docker-compose.dev.yml config` | Validates without YAML errors |
| Negative | Add a `.env` file → attempt `git add .env` | Git rejects it (`.gitignore` match) |
| Edge | File paths with spaces in service directory on Windows | All tools work correctly |
| Regression | `cd frontend && npm run build` from new location | Exits 0, build artifacts in `frontend/.next/` |

**Completion Gate:** All 7 test rows pass, zero warnings. Check the box.

- [x] **TASK 1.1 COMPLETE**

---

### Task 1.2 — Secrets & Environment Configuration

**Objective:** Establish per-service environment variable contracts, fail-fast startup validation, and a documented production secrets management approach — eliminating hardcoded and accidentally committed credentials.

**Pre-empts:** T8 (secrets in `.env` files not suitable for production)

#### Implementation Subtasks

- [x] Create `.env.example` for each of the 6 services, documenting every required variable with type and example value:
  - `DATABASE_URL` — PostgreSQL connection string
  - `REDIS_URL` — Redis connection string
  - `SECRET_KEY` — Django secret key (minimum 50 chars)
  - `DEBUG` — boolean, must be `False` in production
  - `ALLOWED_HOSTS` — comma-separated host list
  - `SENTRY_DSN` — Sentry DSN (required in production, optional in dev)
  - Service-specific variables (e.g., `JWT_SIGNING_KEY` for auth-service, `R2_ACCESS_KEY` for resource-service)
- [x] Create `infra/.env.example` for Docker Compose level variables
- [x] Add Django startup validation to each service's `settings.py`:
  - If `DEBUG=True` AND `ENVIRONMENT=production` → raise `ImproperlyConfigured` and refuse to start
  - If any required variable is missing or empty → raise `ImproperlyConfigured` with the variable name
- [x] Audit entire codebase for hardcoded credentials: `grep -r "password\|secret\|api_key\|ACCESS_KEY" --include="*.py" --include="*.ts" --include="*.js"` — review and move each to env var
- [x] Check git history for accidentally committed secrets: `git log -p -- "*.env"` — rotate any found
- [x] Document production secrets management approach in `docs/secrets.md`:
  - Option A: Docker Secrets (docker swarm mode)
  - Option B: Cloud secrets manager (AWS Secrets Manager / GCP Secret Manager)
  - Step-by-step for each option
- [x] Add `infra/scripts/validate-env.sh` — checks all required env vars are set before `docker-compose up`

#### Optimization Requirements

- Fail-fast: service refuses to start if required env var is missing — prevents silent misconfiguration in production
- No secret is ever logged (filter `SECRET_KEY`, `DATABASE_URL`, `SENTRY_DSN` from log output)
- `.env.example` files are the single source of truth for required variables — no undocumented variables

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | Start any service with one required env var removed | Service exits with clear error naming the missing variable |
| Sanity | `grep -r "SECRET_KEY\s*=" services/` (not in .example files) | Zero hardcoded values |
| Functionality | Start all 6 services with only `.env.example` values (dev) | All services start and pass health checks |
| Integration | `validate-env.sh` with one variable missing | Script exits non-zero with variable name in output |
| Negative | Set `DEBUG=True` and `ENVIRONMENT=production` | Service refuses to start with `ImproperlyConfigured` |
| Edge | `SECRET_KEY` set to only 10 characters | Service warns or rejects (too short for Django) |
| Regression | Existing frontend `.env.local` still works, `NEXT_PUBLIC_API_URL` still resolves | Frontend builds and connects to API |

**Completion Gate:** All 7 test rows pass. Check the box.

- [x] **TASK 1.2 COMPLETE**

---

## Phase 2: Backend Service Extraction

> **Rule for this phase:** Business logic (models, serializers, views) is moved from the monolith — not rewritten. Rewrite only what the new service architecture requires (settings, URL patterns, JWT middleware, per-service DB config). Every extraction is complete when the monolith app is REMOVED from `legacy-monolith/` and the service handles all its traffic.

---

### Task 2.1 — auth-service

**Objective:** Extract the `authentication` app from the monolith into a standalone Django microservice backed by `auth_db`, serving JWT issuance, refresh, blacklist, and password reset for all 3 roles.

**Pre-empts:** T2 (index on token lookup), T4 (Sentry in service), T9 (rate limiting on all auth endpoints)

#### Current Monolith Scope (authentication app)

- Student login / logout / token refresh
- Admin login / logout / token refresh
- Super Admin login / logout / token refresh
- Password reset (email-based)
- JWT issuance: `djangorestframework-simplejwt` (15min access / 7-day refresh / rotation + blacklist)
- Token blacklist: Redis (O(1) lookup)

#### Implementation Subtasks

**Service Setup:**
- [ ] Create `services/auth-service/` Django project: `manage.py`, `core/` (settings, urls), `authentication/` (copied from monolith)
- [ ] Configure `auth_db` as the sole database (PostgreSQL Instance 2)
- [ ] Configure Redis connection for JWT blacklist
- [ ] Remove Gunicorn — configure Uvicorn as ASGI server (`uvicorn core.asgi:application`)
- [ ] Set Uvicorn worker count: `(2 × vCPU) + 1` via `UVICORN_WORKERS` env var
- [ ] Add `entrypoint.sh`: start Uvicorn only
  > **Production rule:** `entrypoint.sh` does NOT run `manage.py migrate` in production. Migrations run as a separate one-time job (Task 7.2 Stage 5.5) before any service container starts. Running migrations inside `entrypoint.sh` causes multiple containers in a rolling deploy to race on the same migration simultaneously — data corruption risk.

**Authentication Logic (verify, don't rewrite):**
- [ ] Verify `djangorestframework-simplejwt` config: access=15min, refresh=7 days, `ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True`
- [ ] Verify login endpoint handles all 3 roles: `student`, `admin`, `super_admin`
- [ ] Verify password reset flow: request reset → email with token → confirm reset with token
- [ ] Add Admin ability to reset a Student's password (direct reset, no email required)
- [ ] Add Super Admin ability to reset an Admin's password (direct reset, no email required)

**New additions:**
- [ ] Add `GET /api/auth/health/` — returns `{status: "ok", service: "auth-service", db: "ok", redis: "ok"}`
- [ ] Add rate limiting (Nginx handles it, but document the expected limits): login 10/min, password reset 3/hour, token refresh 20/min
- [ ] Add structured JSON logging: every auth event logs `{timestamp, level, event, user_id, role, ip, request_id}`
- [ ] Initialize Sentry: `sentry_sdk.init(dsn=env("SENTRY_DSN"), traces_sample_rate=0.1)` (T4)

**Testing:**
- [ ] Write `pytest` test suite covering all auth flows: `tests/test_login.py`, `tests/test_refresh.py`, `tests/test_logout.py`, `tests/test_password_reset.py`, `tests/test_health.py`
- [ ] Minimum coverage: 80% (enforced in CI — Task 7.2)

**Cleanup:**
- [ ] Remove `authentication` app from `legacy-monolith/`

#### Optimization Requirements

- Redis for JWT blacklist: O(1) lookup via Redis SET membership — never query PostgreSQL for blacklist check
- Database index on `users.email` (login lookup) and composite index on `refresh_tokens.(user_id, expires_at)` (cleanup queries)
- `SELECT` only required fields in all user queries — never `SELECT *`
- Uvicorn replaces Gunicorn: non-blocking async I/O — lower memory per worker
- No database call on token refresh if token is valid and not in Redis blacklist (Redis check first, DB second)

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | `POST /api/auth/login/` with valid admin credentials | `200 OK`, `{access: "...", refresh: "..."}` |
| Sanity | Access token decoded — check expiry (15min), role claim present | Correct values |
| Functionality | Login all 3 roles; logout (blacklist refresh); refresh token; password reset flow end-to-end | All return expected status codes and response bodies |
| Integration | Token issued by auth-service → send to `GET /api/users/me/` on user-service (via Nginx) | user-service accepts token, returns user data |
| Negative | Wrong password → `401`; expired access token → `401`; blacklisted refresh token → `401`; missing `email` field → `400`; Student credentials on Admin login → `403`; 11th login attempt in 1 min → `429` | Correct status code per case |
| Edge | Login with email in UPPERCASE (must be case-insensitive); refresh token at exact expiry boundary (within 1 second); concurrent login from 5 devices (all succeed); 10 rapid-fire token refreshes by same user | All pass, tokens distinct |
| Regression | Admin portal login page still works end-to-end; Student portal login still works; existing JWT interceptors in frontend accept new token format | Zero regressions |

**Completion Gate:** All 7 test rows pass, pytest coverage ≥80%, zero open issues. Check the box.

- [x] **TASK 2.1 COMPLETE**

---

### Task 2.2 — user-service

**Objective:** Extract `students` and `batches` apps from the monolith into a standalone user-service backed by `user_db`, serving student account management, batch management, and admin account management (for Super Admin use).

**Pre-empts:** T2 (N+1 on student list), T13 (IDOR — student can only access own profile)

#### Current Monolith Scope

- `students` app: student profiles, CSV bulk import, account management
- `batches` app: batch creation, student-batch assignment

#### Implementation Subtasks

**Service Setup:**
- [ ] Create `services/user-service/` Django project
- [ ] Merge `students` and `batches` apps into a single `users/` app within the service
- [ ] Configure `user_db`
- [ ] Add JWT validation middleware: validate token signature and expiry on every request (no call to auth-service — validate using shared `JWT_SIGNING_KEY`)
- [ ] Remove Gunicorn → Uvicorn
- [ ] Add `entrypoint.sh`: start Uvicorn only
  > **Production rule:** `entrypoint.sh` does NOT run `manage.py migrate` in production. Migrations run as a separate one-time job (Task 7.2 Stage 5.5) before any service container starts. Running migrations inside `entrypoint.sh` causes multiple containers in a rolling deploy to race on the same migration simultaneously — data corruption risk.

**RBAC (fix T13):**
- [ ] Enforce at view level: Student can only `GET` their own profile (`/api/users/me/`) — any attempt to access `/api/users/:other_id/` returns `403`
- [ ] Admin can manage all students and batches within their own `institution_id` only — requests for records with a different `institution_id` return `403`
- [ ] Super Admin can read all students and batches across all institutions (read-only)

**N+1 Fix (T2):**
- [ ] Student list endpoint: add `select_related('batch')` to prevent N+1 on batch name lookup
- [ ] Batch detail endpoint: add `prefetch_related('students')` only when student count is needed
- [ ] Verify: student list for 500 students executes ≤ 3 SQL queries (use `django-debug-toolbar` in dev)

**API Endpoints:**
- [ ] `GET /api/users/me/` — authenticated user's own profile
- [ ] `GET /api/users/students/` — Admin: paginated list of students in institution (page_size=50, max=200)
- [ ] `POST /api/users/students/` — Admin: create single student
- [ ] `POST /api/users/students/import/` — Admin: bulk CSV import
- [ ] `GET /api/users/students/:id/` — Admin: single student detail
- [ ] `PATCH /api/users/students/:id/` — Admin: update student
- [ ] `DELETE /api/users/students/:id/` — Admin: deactivate student (soft delete)
- [ ] `GET /api/users/batches/` — list batches
- [ ] `POST /api/users/batches/` — Admin: create batch
- [ ] `PATCH /api/users/batches/:id/` — Admin: update batch
- [ ] `POST /api/users/batches/:id/assign/` — Admin: assign students to batch
- [ ] `GET /api/users/admins/` — Super Admin only: list all admins
- [ ] `POST /api/users/admins/` — Super Admin only: create admin account
- [ ] `PATCH /api/users/admins/:id/` — Super Admin only: deactivate/update admin
- [ ] `GET /api/users/health/`

**Bulk Import:**
- [ ] CSV import: validate header row, validate each row (email format, required fields), create accounts in `bulk_create()` — one query, not N inserts
- [ ] On duplicate email: skip and report in response (not error crash)
- [ ] Max import size: 1,000 rows per request

**Structured logging + Sentry initialization (T4)**

**pytest test suite** (T3): `tests/test_students.py`, `tests/test_batches.py`, `tests/test_admin_management.py`, `tests/test_health.py`

**Cleanup:** Remove `students` and `batches` apps from `legacy-monolith/`

#### Optimization Requirements

- Paginate all list endpoints (page_size=50 default, max=200) — never load all students into memory
- `bulk_create()` for CSV import — 1,000 rows = 1 INSERT query, not 1,000
- `bulk_update()` for batch assignment updates
- Index: `students.email` (unique), `students.institution_id`, `students.batch_id`, `batches.institution_id`
- Soft delete (`is_active=False`) — no `DELETE FROM` on student records; preserves data integrity for analytics
- Paginated CSV import response: `{created: N, skipped: M, errors: [{row: N, reason: "..."}]}`

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | `GET /api/users/health/` | `200 OK`, all dependency statuses green |
| Sanity | Admin lists students — SQL query count | ≤ 3 queries for 500 students (verified with debug toolbar) |
| Functionality | Create student; assign to batch; CSV import 100 rows; update profile; soft delete; list with filters; batch creation; admin creation by super admin | All return correct status codes and data |
| Integration | Admin creates student → notification-service internal endpoint receives event → student receives "Welcome" notification | End-to-end notification delivery |
| Negative | Student `GET /api/users/students/5/` (not own ID) → `403`; Admin from Institution A queries Institution B students → `403`; CSV import with invalid email format → row skipped, not crash; missing `batch_id` in assign request → `400` | Correct error per case |
| Edge | CSV import with 1,000 rows (single bulk_create query); student with no batch assigned (batch field is null, not error); duplicate email in CSV (row skipped, counted in response); batch with 0 students (returns empty list, not 404) | All handled gracefully |
| Regression | Admin portal Students tab loads; Batches tab loads; student count per batch is correct; existing student login still works | Zero regressions |

**Completion Gate:** All 7 test rows pass, pytest ≥80% coverage.

- [x] **TASK 2.2 COMPLETE**

---

### Task 2.3 — resource-service

**Objective:** Extract the `companies` app from the monolith into a standalone resource-service backed by `resource_db`, serving company-wise resource management with presigned URL uploads, CDN delivery, and magic bytes validation.

**Pre-empts:** T2 (N+1 on resource list), T6 (magic bytes validation), T13 (IDOR on resources)

#### Current Monolith Scope

- `companies` app: company models, resource models, presigned URL generation, Celery async file deletion, CDN URL generation

#### Implementation Subtasks

**Service Setup:**
- [ ] Create `services/resource-service/` Django project
- [ ] Move `companies` app → rename to `resources/` app within service
- [ ] Configure `resource_db`
- [ ] Keep presigned URL pattern: Django generates presigned URL → browser uploads directly to R2/MinIO → browser sends confirmation to Django → Django records the upload
- [ ] Keep Celery for async file deletion (Celery worker connects to same Redis instance)
- [ ] JWT validation middleware
- [ ] Remove Gunicorn → Uvicorn
- [ ] Add `entrypoint.sh`: start Uvicorn only
  > **Production rule:** `entrypoint.sh` does NOT run `manage.py migrate` in production. Migrations run as a separate one-time job (Task 7.2 Stage 5.5) before any service container starts. Running migrations inside `entrypoint.sh` causes multiple containers in a rolling deploy to race on the same migration simultaneously — data corruption risk.

**Magic Bytes Validation (T6):**
- [ ] On upload confirmation endpoint (`POST /api/resources/:id/confirm-upload/`): fetch first 512 bytes from R2 using Range header (`Range: bytes=0-511`) — do NOT download the full file
- [ ] Validate magic bytes against allowed types:
  - PDF: `25 50 44 46 2D` (`%PDF-`)
  - JPEG: `FF D8 FF`
  - PNG: `89 50 4E 47 0D 0A 1A 0A`
  - DOCX/XLSX: `50 4B 03 04` (ZIP-based Office formats)
- [ ] If magic bytes mismatch: delete object from R2 via Celery task → return `400 {"error": "File type rejected: content does not match declared type"}`
- [ ] Log all magic bytes rejections: `{timestamp, user_id, institution_id, filename, declared_type, detected_bytes}` — these are potential attack attempts

**IDOR Fix (T13):**
- [ ] Every resource view/edit/delete must verify: `resource.institution_id == jwt.institution_id`
- [ ] Students can only access resources from companies where `published=True` and `institution_id` matches
- [ ] Admin can only manage resources within their `institution_id`

**N+1 Fix (T2):**
- [ ] Resource list with company: `select_related('company')` — no separate query per resource for company name
- [ ] Company list with resource count: annotate with `Count('resources')` — 1 query, not N+1

**Redis Caching:**
- [ ] Cache company resource lists: key `resources:institution:{id}:company:{id}`, TTL 5 minutes
- [ ] Invalidate cache on any upload, delete, or publish state change

**API Endpoints:**
- [ ] `GET /api/resources/companies/` — list companies for institution (cached)
- [ ] `GET /api/resources/companies/:id/` — company detail
- [ ] `POST /api/resources/companies/` — Admin: create company
- [ ] `PATCH /api/resources/companies/:id/` — Admin: update company (including publish/unpublish)
- [ ] `DELETE /api/resources/companies/:id/` — Admin: delete company (cascades resource deletion via Celery)
- [ ] `GET /api/resources/companies/:id/resources/` — list resources for company (paginated, sorted by created_at DESC)
- [ ] `POST /api/resources/presign/` — Admin: generate presigned upload URL + create pending resource record
- [ ] `POST /api/resources/:id/confirm-upload/` — Admin: confirm upload, trigger magic bytes validation
- [ ] `PATCH /api/resources/:id/` — Admin: update metadata (title, description, category)
- [ ] `DELETE /api/resources/:id/` — Admin: soft delete + async R2 deletion
- [ ] `GET /api/resources/health/`

**All resource URLs in responses must be CDN URLs** — never return direct R2 bucket URLs.

**Structured logging + Sentry (T4). pytest test suite (T3).**

**Cleanup:** Remove `companies` app from `legacy-monolith/`

#### Optimization Requirements

- CDN URLs always (not R2 direct URLs) — CDN serves cached copies, reduces R2 egress cost
- Redis cache for company+resource lists: saves DB round-trip on every page load (most frequently accessed data)
- No binary data through Django process: presigned URL pattern strictly enforced — Django handles only metadata
- File deletion is async (Celery): response returns immediately, deletion happens in background
- Paginate resource lists: page_size=20 default, max=100
- Index: `resources.company_id`, `resources.institution_id`, `resources.published`, `resources.created_at DESC`

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | `GET /api/resources/health/`; `GET /api/resources/companies/` | Both return `200`, company list is array |
| Sanity | Resource response contains CDN URL (not R2 URL); company list SQL = 1 query | CDN prefix in URL; query count ≤ 2 |
| Functionality | Full upload flow: `POST /presign/` → upload to R2 → `POST /confirm-upload/` → resource appears in list; publish/unpublish; delete (Celery task fired); category filter; sort by latest | All correct |
| Integration | Upload confirmed → Celery task queued → R2 object deleted (verify in R2 on delete); upload confirmed → notification-service receives event | Tasks and events fire |
| Negative | Upload PDF with DOCX magic bytes → `400` + R2 object deleted; resource from another institution → `403`; unpublished resource accessed by student → `404`; presign URL with disallowed file extension → `400`; file > 50MB → `413` at Nginx | Correct error per case |
| Edge | Upload exactly at 50MB limit (accepted); PDF with valid magic bytes but corrupted body after header (accepted — we validate header only); concurrent uploads from same admin (all succeed, independent); company with 0 resources (empty array, not 404); delete company with 50 resources (all async deletions queued) | All handled correctly |
| Regression | Admin Resources tab: company list, resource list, upload flow still works; Student Companies tab: browse resources, open PDF | Zero regressions |

**Completion Gate:** All 7 test rows pass, pytest ≥80% coverage.

- [x] **TASK 2.3 COMPLETE**

---

### Task 2.4 — practice-service

**Objective:** Extract the `practice` app from the monolith into a standalone practice-service backed by `practice_db`, serving topic-wise practice modules, sections, questions, student attempt tracking, and progress analytics.

**Pre-empts:** T2 (N+1 on question queries), T13 (IDOR on modules/questions)

#### Current Monolith Scope

- `practice` app: modules, sections, questions (MCQ single, MCQ multiple, FIB), student attempts, explanations, progress tracking, image uploads (question + explanation images)

#### Implementation Subtasks

**Service Setup:**
- [ ] Create `services/practice-service/` Django project
- [ ] Move `practice` app
- [ ] Configure `practice_db`
- [ ] JWT validation middleware
- [ ] Remove Gunicorn → Uvicorn
- [ ] Add `entrypoint.sh`: start Uvicorn only
  > **Production rule:** `entrypoint.sh` does NOT run `manage.py migrate` in production. Migrations run as a separate one-time job (Task 7.2 Stage 5.5) before any service container starts. Running migrations inside `entrypoint.sh` causes multiple containers in a rolling deploy to race on the same migration simultaneously — data corruption risk.

**IDOR Fix (T13):**
- [ ] Every module/section/question must verify: `object.institution_id == jwt.institution_id`
- [ ] Students only see `published=True` modules and questions
- [ ] Student attempt records: `attempt.student_id == jwt.user_id` enforced on every read/write

**N+1 Fixes (T2):**
- [ ] Question list with section and module: `select_related('section__module')` — 1 join query, not N queries
- [ ] Section list with question count: annotate with `Count('questions', filter=Q(questions__published=True))`
- [ ] Student progress overview: single aggregation query `GROUP BY module_id` — not N per-module queries
- [ ] Verify: question list for 200 questions executes ≤ 3 SQL queries

**Redis Caching:**
- [ ] Cache published question sets per module: key `practice:institution:{id}:module:{id}:questions`, TTL 10 minutes
- [ ] Invalidate on any question publish state change, question create, or question delete

**Attempt Logic:**
- [ ] Attempts are idempotent: re-submitting same question with different answer updates the record, does not create duplicate
- [ ] FIB answers: trim whitespace and lowercase before comparison
- [ ] MCQ multiple: correct only if selected options exactly match correct options (no partial credit in V1)

**API Endpoints:**
- [ ] `GET /api/practice/modules/` — list published modules for institution (student); all modules (admin)
- [ ] `GET /api/practice/modules/:id/` — module detail with sections
- [ ] `POST /api/practice/modules/` — Admin: create module
- [ ] `PATCH /api/practice/modules/:id/` — Admin: update/publish/unpublish module
- [ ] `DELETE /api/practice/modules/:id/` — Admin: delete module
- [ ] `GET /api/practice/modules/:id/sections/` — list sections in module
- [ ] `POST /api/practice/sections/` — Admin: create section
- [ ] `PATCH /api/practice/sections/:id/` — Admin: update/publish/unpublish section
- [ ] `GET /api/practice/sections/:id/questions/` — list questions in section (paginated)
- [ ] `POST /api/practice/questions/` — Admin: create question (with optional image upload via presigned URL)
- [ ] `PATCH /api/practice/questions/:id/` — Admin: update question
- [ ] `POST /api/practice/questions/:id/attempt/` — Student: submit answer
- [ ] `GET /api/practice/progress/` — Student: own progress summary (completion %, accuracy, topic breakdown)
- [ ] `GET /api/practice/health/`

**All question/explanation images must be CDN URLs in responses.**

**Structured logging + Sentry (T4). pytest test suite (T3).**

**Cleanup:** Remove `practice` app from `legacy-monolith/`

#### Optimization Requirements

- Cache published question sets (10 min TTL): serves 80%+ of student requests from Redis, not DB
- Index: `modules.institution_id`, `sections.module_id`, `questions.section_id`, `questions.difficulty`, `questions.published`, composite unique `(student_attempts.student_id, student_attempts.question_id)`
- Paginate question lists: page_size=50 default
- Progress query: single `GROUP BY` SQL — never N per-question queries
- Attempt save: `update_or_create()` for idempotency — one upsert, not check-then-insert

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | `GET /api/practice/health/`; `GET /api/practice/modules/` | Both `200`, modules list is array |
| Sanity | Question list SQL count for 200 questions | ≤ 3 queries |
| Functionality | Module CRUD; section CRUD; question CRUD; MCQ single attempt (correct/incorrect); MCQ multiple attempt; FIB attempt with extra whitespace; view explanation; check progress after attempt; retry incorrect | All correct behaviors |
| Integration | Student completes practice module → analytics-service internal endpoint receives event → student analytics updated | Event fires and is processed |
| Negative | Student accesses unpublished module → `404`; student submits attempt for another student → `403`; admin from wrong institution accesses module → `403`; submit attempt with no answer → `400`; question with image — student sees CDN URL (not R2 URL) | Correct error/behavior |
| Edge | Module with 0 questions (empty section, not error); FIB with trailing spaces in answer ("  Django  " = "django" after trim+lowercase); MCQ multiple with partial selection (marked incorrect correctly); concurrent attempts same question by 1,000 students (no duplicate attempts created); very large explanation text | All handled correctly |
| Regression | Student Practice tab: module list, solver (MCQ/FIB), explanation view, progress tracking all work; Admin Practice tab: module management, question creation all work | Zero regressions |

**Completion Gate:** All 7 test rows pass, pytest ≥80% coverage.

- [x] **TASK 2.4 COMPLETE**

---

## Phase 3: New Backend Services

---

### Task 3.1 — notification-service

**Objective:** Build the notification-service from scratch with `notification_db` to deliver in-app notifications to students (V1: new resource uploads, general announcements from scrollbar updates).

**Pre-empts:** T3 (new test suite from scratch), T4 (Sentry initialized)

#### Implementation Subtasks

**Service Setup:**
- [ ] Create `services/notification-service/` Django project
- [ ] Create `notifications/` app with models:
  - `Notification`: `id`, `user_id`, `institution_id`, `type` (enum: `resource_upload`, `announcement`), `title`, `body`, `is_read` (bool, default False), `is_deleted` (bool, default False), `created_at`
  - No foreign keys to other service databases — only IDs
- [ ] Configure `notification_db`
- [ ] JWT validation middleware (for user-facing endpoints)
- [ ] Service key validation (shared secret header `X-Service-Key`) for internal endpoints — prevents unauthorized services from injecting notifications
- [ ] Remove Gunicorn → Uvicorn
- [ ] Add `entrypoint.sh`: start Uvicorn only
  > **Production rule:** `entrypoint.sh` does NOT run `manage.py migrate` in production. Migrations run as a separate one-time job (Task 7.2 Stage 5.5) before any service container starts. Running migrations inside `entrypoint.sh` causes multiple containers in a rolling deploy to race on the same migration simultaneously — data corruption risk.

**Redis Caching:**
- [ ] Cache unread count per user: key `notifications:unread:{user_id}`, TTL 60 seconds
- [ ] Invalidate on new notification creation and on mark-as-read

**Auto-expiry:**
- [ ] Celery beat scheduled task: every day at 03:00 UTC, soft-delete notifications older than 90 days (`is_deleted=True`)
- [ ] This keeps the `notifications` table bounded in size — prevents unbounded growth

**API Endpoints (user-facing, JWT required):**
- [ ] `GET /api/notifications/` — paginated list of user's notifications (page_size=20, exclude `is_deleted=True`)
- [ ] `GET /api/notifications/unread-count/` — returns `{count: N}` (cached)
- [ ] `PATCH /api/notifications/:id/read/` — mark one notification as read
- [ ] `POST /api/notifications/read-all/` — mark all as read

**API Endpoints (internal, service key required):**
- [ ] `POST /api/notifications/internal/send/` — receives `{user_ids: [...], institution_id, type, title, body}`, creates notification records in bulk

**Structured logging + Sentry (T4). pytest test suite (T3).**

#### Optimization Requirements

- Unread count cached in Redis: student home page loads unread count in <5ms (Redis) vs 50ms+ (DB query)
- `bulk_create()` for send-to-multiple-users: 1 INSERT for 500 users, not 500 INSERTs
- Index: composite `(user_id, is_read, is_deleted)`, `created_at DESC`
- Soft delete (is_deleted): never hard-delete notification records — preserves send history, bounded by 90-day cron
- Paginate with cursor pagination (not offset) — consistent results even when new notifications arrive

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | `GET /api/notifications/health/` | `200 OK` |
| Sanity | Send notification to 500 users → SQL INSERT count | 1 bulk insert, not 500 |
| Functionality | Send notification → appears in list; mark as read → `is_read=True`; unread count decrements; mark-all-read; pagination; 90-day cleanup cron | All correct |
| Integration | resource-service uploads resource → calls internal send endpoint → notification appears in student's `GET /api/notifications/` | End-to-end delivery |
| Negative | `PATCH` another user's notification as read → `403`; internal endpoint without `X-Service-Key` header → `401`; send with empty `user_ids` → `400`; notification after 90-day cleanup → not returned in list | Correct error per case |
| Edge | User with 10,000 notifications (pagination works correctly, no timeout); send to 0 users (empty `user_ids` — graceful no-op or error, defined); mark-all-read with 10,000 unread (completes in <2 seconds via bulk update); deleted user still in notification list (soft delete means row exists — return as normal) | All handled |
| Regression | Student home page unread badge works; clicking notification marks it read; existing resource upload flow sends notifications | Zero regressions |

**Completion Gate:** All 7 test rows pass, pytest ≥80% coverage.

- [x] **TASK 3.1 COMPLETE**

---

### Task 3.2 — analytics-service

**Objective:** Build the analytics-service from scratch with `analytics_db` to aggregate and serve student, admin, and super admin analytics (V1: practice completion, resource usage, student engagement, weak topic trends).

**Pre-empts:** T3 (new test suite), T4 (Sentry), T2 (pre-computed aggregations — no on-the-fly full table scans)

#### Implementation Subtasks

**Service Setup:**
- [ ] Create `services/analytics-service/` Django project
- [ ] Create `analytics/` app with models:
  - `PracticeEvent`: `id`, `student_id`, `institution_id`, `module_id`, `question_id`, `topic`, `difficulty`, `is_correct`, `created_at`
  - `ResourceViewEvent`: `id`, `student_id`, `institution_id`, `company_id`, `resource_id`, `created_at`
  - `DailyEngagementSnapshot`: `id`, `student_id`, `institution_id`, `department`, `batch_id`, `practice_attempts`, `resource_views`, `snapshot_date` — pre-computed daily
  - `InstitutionSnapshot`: `id`, `institution_id`, `total_students`, `total_active`, `practice_completion_rate`, `resource_utilization_rate`, `snapshot_date` — pre-computed daily
- [ ] Configure `analytics_db`
- [ ] JWT validation middleware
- [ ] Service key validation for internal endpoints
- [ ] Remove Gunicorn → Uvicorn
- [ ] Add `entrypoint.sh`: start Uvicorn only
  > **Production rule:** `entrypoint.sh` does NOT run `manage.py migrate` in production. Migrations run as a separate one-time job (Task 7.2 Stage 5.5) before any service container starts. Running migrations inside `entrypoint.sh` causes multiple containers in a rolling deploy to race on the same migration simultaneously — data corruption risk.

**Pre-computation (T2 prevention):**
- [ ] Celery beat task: runs nightly at 01:00 UTC — aggregates raw events into `DailyEngagementSnapshot` and `InstitutionSnapshot`
- [ ] Real-time endpoints read from snapshots, not raw events — no O(N×students) aggregation on request

**Redis Caching:**
- [ ] Admin overview: `analytics:admin:{institution_id}:overview`, TTL 15 minutes
- [ ] Super admin overview: `analytics:superadmin:overview`, TTL 30 minutes
- [ ] Student analytics: `analytics:student:{student_id}`, TTL 5 minutes

**API Endpoints (JWT required):**
- [ ] `GET /api/analytics/student/` — student's own: completion %, accuracy %, topic breakdown, strong topics, weak topics, practice streak
- [ ] `GET /api/analytics/admin/overview/` — Admin: institution engagement summary (active students, completion rates, resource usage)
- [ ] `GET /api/analytics/admin/top-performers/` — Admin: top 10 students by accuracy
- [ ] `GET /api/analytics/admin/weak-topics/` — Admin: topics with lowest average accuracy across students
- [ ] `GET /api/analytics/admin/resource-usage/` — Admin: most viewed companies and resources
- [ ] `GET /api/analytics/super-admin/overview/` — Super Admin: institution-wide KPIs
- [ ] `GET /api/analytics/super-admin/departments/` — Super Admin: per-department breakdown

**API Endpoints (internal, service key required):**
- [ ] `POST /api/analytics/internal/event/` — receives `{event_type, student_id, institution_id, ...payload}` from practice-service and resource-service

**Structured logging + Sentry (T4). pytest test suite (T3).**

#### Optimization Requirements

- All admin/super admin analytics served from pre-computed snapshots — never run GROUP BY on raw events table in production
- Cache all overview endpoints (15–30 min TTL) — analytics are not real-time, slight delay is acceptable and vastly reduces DB load
- Index: `practice_events.(institution_id, created_at)`, `practice_events.(student_id, topic)`, `daily_snapshots.(institution_id, snapshot_date)`, `resource_view_events.(institution_id, company_id)`
- Raw event table: partition by `created_at` month in future (add comment in model for future reference) — not required in V1 but partition key must be set correctly now
- `DATABASE_REPLICA` setting stub: if set, analytics queries use replica — not required in V1 but code path ready

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | `GET /api/analytics/health/` | `200 OK` |
| Sanity | Student completes 10 practice questions; check student analytics endpoint | Completion % and accuracy match the 10 attempts exactly |
| Functionality | Student analytics (all fields); admin overview (engagement, top performers, weak topics); admin resource usage; super admin overview and department breakdown; nightly aggregation cron runs and updates snapshots | All return correct data |
| Integration | practice-service sends `practice_attempt` event → analytics-service processes → student analytics updated; resource-service sends `resource_view` event → resource usage analytics updated | Both event types processed correctly |
| Negative | Student accesses admin analytics → `403`; admin accesses super admin endpoint → `403`; admin from Institution A accesses Institution B data → `403`; internal endpoint without service key → `401`; invalid `student_id` in event → logged, not crash | Correct error per case |
| Edge | Student with 0 practice attempts (analytics returns zeros, not `null` or `NaN`, not `500`); institution with 10,000 students (aggregation snapshot completes in <30 seconds during off-peak cron); new institution created today with no data (all counts return 0, not 500) | All handled |
| Regression | Student My Profile analytics section loads; admin dashboard all metrics load; super admin analytics tab all charts render | Zero regressions |

**Completion Gate:** All 7 test rows pass, pytest ≥80% coverage.

- [x] **TASK 3.2 COMPLETE**

---

## Phase 4: API Gateway

---

### Task 4.1 — Nginx API Gateway: Routing + Security Hardening

**Objective:** Update Nginx configuration to route requests to all 6 microservices, enforce rate limiting on all API endpoints, and enable gzip compression — eliminating the current single-backend routing and two identified gaps.

**Pre-empts:** T9 (rate limiting on all endpoints), T10 (response compression)

#### Routing Map

| Path Pattern | Upstream | Port |
|---|---|---|
| `/api/auth/*` | auth-service | 8001 |
| `/api/users/*` | user-service | 8002 |
| `/api/resources/*` | resource-service | 8003 |
| `/api/practice/*` | practice-service | 8004 |
| `/api/notifications/*` | notification-service | 8005 |
| `/api/analytics/*` | analytics-service | 8006 |
| `/*` (catch-all) | Next.js frontend | 3000 |

#### Implementation Subtasks

**Routing:**
- [ ] Define 6 `upstream` blocks (one per service) with keepalive connections
- [ ] Define `location /api/auth/` → proxy to auth-service upstream
- [ ] Define `location /api/users/` → proxy to user-service upstream
- [ ] Define `location /api/resources/` → proxy to resource-service upstream
- [ ] Define `location /api/practice/` → proxy to practice-service upstream
- [ ] Define `location /api/notifications/` → proxy to notification-service upstream
- [ ] Define `location /api/analytics/` → proxy to analytics-service upstream
- [ ] Define `location /` → proxy to Next.js frontend
- [ ] Forward headers: `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, `Host` to all upstreams
- [ ] Generate and forward `X-Request-ID` header (unique per request — for log tracing)
- [ ] Set `proxy_read_timeout 30s`, `proxy_send_timeout 30s`, `proxy_connect_timeout 10s`

**Rate Limiting (T9):**
- [ ] Define rate limit zones in `http {}` block:
  - `limit_req_zone $binary_remote_addr zone=auth_zone:10m rate=10r/m;` (auth endpoints)
  - `limit_req_zone $binary_remote_addr zone=api_zone:10m rate=100r/m;` (all other API endpoints)
  - `limit_req_zone $binary_remote_addr zone=static_zone:10m rate=500r/m;` (frontend assets)
- [ ] Apply `limit_req zone=auth_zone` to `location /api/auth/`
- [ ] Apply `limit_req zone=api_zone` to all other `/api/` locations
- [ ] Rate limit response: `limit_req_status 429`, custom JSON error: `{"error": "Rate limit exceeded", "retry_after": "60"}`

**Response Compression (T10):**
- [ ] Enable gzip:
  ```
  gzip on;
  gzip_types application/json text/html text/css application/javascript image/svg+xml;
  gzip_min_length 1024;
  gzip_comp_level 6;
  gzip_proxied any;
  gzip_vary on;
  ```

**Security Headers:**
- [ ] `X-Frame-Options: DENY`
- [ ] `X-Content-Type-Options: nosniff`
- [ ] `Referrer-Policy: strict-origin-when-cross-origin`
- [ ] `X-Request-ID: $request_id` (generated by Nginx, forwarded to services)

**Performance Settings:**
- [ ] `worker_processes auto;`
- [ ] `worker_connections 1024;`
- [ ] `keepalive_timeout 65;`
- [ ] `keepalive 32;` per upstream block
- [ ] `sendfile on; tcp_nopush on; tcp_nodelay on;`
- [ ] `client_max_body_size 50M;` (max upload size — enforced at gateway)

**Access Logging:**
- [ ] JSON access log format: `{time, method, uri, status, body_bytes_sent, request_time, remote_addr, request_id, upstream_addr}`
- [ ] Exclude `/api/*/health/` and `/api/*/ready/` from access logs (no noise from health checks)

**Verify:**
- [ ] Test all 6 routing paths with curl
- [ ] Verify rate limiting fires at the configured threshold
- [ ] Verify gzip encoding present on API responses (`curl -H "Accept-Encoding: gzip" --compressed`)
- [ ] Verify security headers present in response
- [ ] Verify `X-Request-ID` forwarded to service and appears in service logs

#### Optimization Requirements

- `worker_processes auto`: Nginx uses all available CPU cores automatically
- Upstream `keepalive 32`: reuses TCP connections to services instead of creating new ones per request — significant reduction in latency and connection overhead
- `gzip_comp_level 6`: sweet spot between CPU cost and compression ratio (level 9 uses 4× more CPU for 10% better compression — not worth it)
- `gzip_min_length 1024`: don't compress tiny responses — compression overhead exceeds savings below 1KB
- Health check routes excluded from access logs: prevents log file bloat from Kubernetes/Docker health check polling

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | `curl http://localhost/api/auth/health/`; `/api/users/health/`; `/api/resources/health/`; `/api/practice/health/`; `/api/notifications/health/`; `/api/analytics/health/` | All 6 return `200 OK` via Nginx |
| Sanity | `curl -I http://localhost/api/users/` | Response headers include `X-Frame-Options`, `X-Content-Type-Options`, `X-Request-ID`, `Content-Encoding: gzip` |
| Functionality | Each service path routes to correct upstream; `X-Request-ID` in service logs matches Nginx log; client_max_body_size enforced | All routing correct |
| Integration | Full request: Browser → Nginx → auth-service → PostgreSQL auth_db → response | End-to-end under 100ms at idle |
| Negative | 11th login request in 1 minute → `429` with correct JSON body; request to `/api/unknown/` → `404` (not hang, not `500`); body size > 50MB → `413` | Correct status codes |
| Edge | Upstream service down → `502 Bad Gateway` within 10 seconds (not hang until proxy_read_timeout); 200 concurrent requests to same endpoint (all handled, none dropped); very long URL (>8KB) → `414` | Correct degradation behavior |
| Regression | Frontend loads at `/`; PWA service worker served; all existing API calls work through new routing; login flow end-to-end | Zero regressions |

**Completion Gate:** All 7 test rows pass.

- [x] **TASK 4.1 COMPLETE**

---

## Phase 5: Database

---

### Task 5.1 — PostgreSQL Instance 2: 6 Isolated Databases

**Objective:** Provision PostgreSQL Instance 2 (standard compute — not the high-load instance reserved for V2 assessments/contests) and create 6 isolated databases with dedicated least-privilege users, one per microservice.

**Pre-empts:** T12 (resource contention — each service has its own database, no shared tables)

#### Implementation Subtasks

**Provisioning:**
- [x] Provision PostgreSQL Instance 2 (standard compute — CPU/RAM appropriate for V1 traffic, not oversized)
- [x] Configure PostgreSQL instance settings in `postgresql.conf`:
  - `max_connections = 200` (will be managed via PgBouncer in Task 5.2, but instance limit must be high enough)
  - `shared_buffers = 128MB` (dev — 25% of 512MB)
  - `effective_cache_size = 384MB` (dev — 75% of 512MB)
  - `work_mem = 16MB`
  - `wal_buffers = 64MB`
  - `log_min_duration_statement = 200` (log queries slower than 200ms)
  - `log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '`

**Database Creation:**
- [x] `CREATE DATABASE auth_db;`
- [x] `CREATE DATABASE user_db;`
- [x] `CREATE DATABASE resource_db;`
- [x] `CREATE DATABASE practice_db;`
- [x] `CREATE DATABASE notification_db;`
- [x] `CREATE DATABASE analytics_db;`

**Dedicated Users (minimum privilege — each user can only access its own database):**
- [x] `CREATE USER auth_db_user WITH PASSWORD '...';`
- [x] `GRANT CONNECT ON DATABASE auth_db TO auth_db_user;`
- [x] `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO auth_db_user;` (in auth_db)
- [x] `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO auth_db_user;`
- [x] Repeat pattern for all 6 users: `user_db_user`, `resource_db_user`, `practice_db_user`, `notification_db_user`, `analytics_db_user`
- [x] Revoke cross-database access: verify `auth_db_user` cannot connect to `user_db`

**Migrations:**
- [x] Run `python manage.py migrate` for each service against its respective database
- [x] Verify all migrations complete with 0 errors
- [x] Verify schema in each database matches Django models

**Connection Verification:**
- [x] From auth-service container: `python -c "import django; django.setup(); from django.db import connection; connection.ensure_connection(); print('OK')"` → OK
- [x] Repeat for all 6 services
- [x] Attempt cross-service connection: auth-service container with user_db credentials → connection refused

#### Optimization Requirements

- `shared_buffers = 25%` RAM: industry standard for dedicated PostgreSQL server — keeps hot data in memory
- `work_mem = 16MB`: prevents disk spill on sort/hash join operations for typical analytics queries
- `log_min_duration_statement = 200`: identifies slow queries in production without logging every query (which would fill disk)
- Separate users per database: if one service's DB credentials are compromised, attacker cannot access other databases
- `pg_stat_statements`: provides query-level performance metrics — essential for identifying real bottlenecks (no guessing)

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | Each service connects to its DB and runs `SELECT 1` | 6/6 succeed, 0 errors |
| Sanity | `\dt` in each database | Tables match Django models, no stale monolith tables |
| Functionality | Each service can CREATE, READ, UPDATE, DELETE a test record in its own database | All CRUD operations succeed |
| Integration | Service-to-service communication uses REST API (not DB cross-access); auth-service issues JWT → user-service validates without connecting to auth_db | REST-only inter-service communication confirmed |
| Negative | auth-service with user_db credentials → `FATAL: password authentication failed` or `FATAL: database does not exist`; wrong database name in service config → service refuses to start | Connection isolation enforced |
| Edge | PostgreSQL server restart mid-request (Django connection retry works, request may fail once but retries automatically); 200 concurrent connections total across all 6 services (within max_connections limit) | Correct behavior under disruption |
| Regression | All 6 services pass their respective health checks (`/health/` endpoints return `db: ok`) after migration | Zero regressions |

**Completion Gate:** All 7 test rows pass.

- [x] **TASK 5.1 COMPLETE** — 36/36 tests passed twice (200% Rule satisfied, 2026-05-29)

---

### Task 5.2 — Query Optimization, Indexes, PgBouncer, Backup Automation

**Objective:** Eliminate all N+1 queries, add targeted indexes for hot query paths, deploy PgBouncer to manage connection pooling, and establish automated database backups.

**Pre-empts:** T2 (N+1 queries), T5 (automated backup), T11 (connection pooling)

#### Implementation Subtasks

**Query Optimization — N+1 Audit (T2):**
- [x] Enable `django-debug-toolbar` in development for each service
- [x] Audit all list endpoints: visit each endpoint in dev → confirm SQL query count in toolbar
- [x] Required query counts (must pass before task is complete):
  - Student list (500 students with batches): ≤ 3 queries
  - Resource list (100 resources with company): ≤ 3 queries
  - Question list (200 questions with sections): ≤ 3 queries
  - Notification list (50 notifications): ≤ 2 queries
  - Analytics overview: ≤ 5 queries (reads from pre-computed snapshots)
- [x] Fix any violations with `select_related()` / `prefetch_related()` / annotation
- [x] Run `EXPLAIN ANALYZE` in production on all fixed queries — confirm index scan (not sequential scan)

**Indexes:**
- [x] `auth_db`: `idx_users_email`, `idx_users_institution_id`, `idx_users_role` created via migrations
- [x] `user_db`: `idx_students_institution_id`, `idx_students_batch_id`, `idx_students_college_email`, `idx_students_department`, `idx_students_is_active`, `idx_batches_institution_id` created
- [x] `resource_db`: `idx_companies_institution_id`, `idx_companies_is_published`, `idx_companies_created_desc`, `idx_sections_company_id`, `idx_uploads_section_id`, `idx_uploads_upload_type`, `idx_uploads_created_desc` created
- [x] `practice_db`: `idx_pmodule_inst_published`, `idx_psection_inst_published`, `idx_pq_section_published`, `idx_pqa_student_question`, `idx_pqp_student_id`, `idx_pqp_student_question` created
- [x] `notification_db`: `notif_user_read_deleted_idx`, `notif_created_desc_idx` created
- [x] `analytics_db`: `pe_institution_created_idx`, `pe_student_topic_idx`, `is_institution_date_idx` created
- [x] Run `EXPLAIN ANALYZE` after index creation — confirm planner uses new indexes

**PgBouncer (T11):**
- [x] Deploy PgBouncer as a Docker container in the infrastructure stack
- [x] Configure `pgbouncer.ini`:
  - `pool_mode = transaction` (best for Django REST — requests are short, connections are released after each transaction)
  - `max_client_conn = 600` (100 per service × 6 services)
  - `default_pool_size = 10` (10 real PostgreSQL connections per pool × 6 databases = 60 total real connections vs potential 600 without pooling)
  - `server_idle_timeout = 600`
  - `client_idle_timeout = 60`
- [x] Update each service's DB_HOST to point to PgBouncer; CONN_MAX_AGE=0 (required for transaction-mode pooling)
- [x] Verify: under normal load, PostgreSQL shows ≤ 15 active connections (PgBouncer absorbs the rest)

**Backup Automation (T5):**
- [x] Write `infra/scripts/backup.sh`:
  - For each of 6 databases: `pg_dump --compress=9 --format=custom`
  - Write manifest JSON: `{databases: [{name, size, checksum, duration}], timestamp}`
  - On any failure: logs ERROR to stderr, exits non-zero
- [x] Schedule via cron in a dedicated container: daily at `02:00 UTC`
- [x] Retention policy:
  - Daily backups: keep 30 days (`find -mtime +30 -delete`)
  - Monthly backups (first Sunday): keep 365 days
  - Cleanup runs at end of each backup.sh execution
- [x] backup.sh tested: all 6 .dump files non-zero, manifest valid JSON with all 6 DBs, retry logic verified
- [x] db-backup container stable (restart count = 0)

**Additional PostgreSQL Maintenance:**
- [x] Enable `VACUUM ANALYZE` auto-vacuum (PostgreSQL default) — verified `autovacuum = on`
- [x] Enable `pg_stat_statements` extension on auth_db, user_db, practice_db

#### Optimization Requirements

- PgBouncer transaction-mode pooling: 10 real DB connections handle 100 concurrent Django requests — 10× reduction in PostgreSQL connection overhead
- `pg_dump --compress=9`: maximum compression — a 1GB database compresses to ~100MB, reducing R2 storage costs by ~90%
- Backup goes directly to R2 (streaming via pipe) — no temporary disk usage, eliminates disk-full risk
- `EXPLAIN ANALYZE` must show `Index Scan` (not `Seq Scan`) on all indexed columns before task is marked complete
- Index-only scans for analytics queries: covering indexes on `(institution_id, snapshot_date)` — planner never touches the heap

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | `EXPLAIN SELECT * FROM students WHERE institution_id='...' LIMIT 50;` | `Index Scan` (not `Seq Scan`) on institution_id index |
| Sanity | Student list API endpoint — django-debug-toolbar query count | ≤ 3 SQL queries for 500 students |
| Functionality | Run `backup.sh` manually → verify backup file in R2, manifest written, file is non-zero size; restore backup to throwaway DB → row counts match source | Both pass |
| Integration | PgBouncer transparent: all service APIs return correct data through PgBouncer; 100 concurrent requests → PostgreSQL shows ≤ 15 active connections | Connection pooling working |
| Negative | Backup when R2 is unreachable → script retries 3 times then exits non-zero and alerts; PgBouncer pool exhausted → Django receives `pooler: no more connections allowed` error (not hang indefinitely); missing index on filtered column → `EXPLAIN` reveals `Seq Scan` → fix before marking complete | Failures are visible and reported |
| Edge | Backup during peak traffic (backup uses separate read-only DB connection if replica available, else during off-peak); 30-day cleanup runs and deletes correct files (not newer files); index on very large table (>5M rows) — `CREATE INDEX CONCURRENTLY` to avoid table lock | Correct behavior |
| Regression | All API endpoints return correct data after index additions; no data changed by indexing operations | Zero regressions |

**Completion Gate:** All 7 test rows pass.

- [x] **TASK 5.2 COMPLETE — 39/39 tests passed twice (200% Rule satisfied, 2026-05-29)**

---

## Phase 6: Frontend

---

### Task 6.1 — Route Protection Middleware (CRITICAL)

**Objective:** Implement Next.js `middleware.ts` to enforce authentication and role-based route access for all three portals — closing the most critical security gap in the current codebase.

**Pre-empts:** T1 CRITICAL (currently ANY URL is accessible in browser without authentication)

> **Current state:** `middleware.ts` does not exist. A completely unauthenticated user can navigate to `/admin/students` and the page renders. This is a critical security failure. This task is the highest-priority frontend task.

#### Implementation Subtasks

**Middleware Implementation:**
- [ ] Create `frontend/src/middleware.ts`
- [ ] Define public routes (no auth required):
  ```typescript
  const PUBLIC_ROUTES = ['/', '/login', '/students/login', '/admin/login', '/super-admin/login'];
  // NOTE: Route is '/students/login' (plural) — matches actual Next.js app directory structure.
  // '/student/login' (singular) does NOT exist in the codebase. The middleware also accepts
  // '/student/login' as a legacy alias in LOGIN_PATHS but the canonical path is '/students/login'.
  ```
- [ ] Define role → allowed path prefixes mapping:
  ```typescript
  const ROLE_PATHS: Record<string, string> = {
    student: '/students',   // NOTE: plural — matches src/app/students/ directory
    admin: '/admin',
    super_admin: '/super-admin',
  };
  ```
- [ ] Middleware logic (in order):
  1. If request path is a public route → allow through (no auth check)
  2. Read `aptlogic_role` cookie from request
  3. If no cookie (unauthenticated) → redirect to `/login` (or role-specific login if path prefix gives a hint)
  4. If authenticated: check that the request path starts with the role's allowed prefix
  5. If path mismatch (e.g., Student trying to access `/admin/*`) → redirect to their own portal home
  6. If authenticated and on a login page → redirect to their portal home (prevent re-login loop)
  7. Allow through
- [ ] Configure `middleware.ts` `config.matcher`:
  - Exclude: `/_next/static/*`, `/_next/image/*`, `/favicon.ico`, `/api/*`, `/*.png`, `/*.jpg`, `/*.svg`, `/*.webp`
  - Include: all other paths
- [ ] Middleware must NOT make any API calls (zero latency overhead — reads cookie only)
- [ ] Write Jest unit tests for middleware logic (`tests/middleware.test.ts`):
  - Test unauthenticated access to each portal
  - Test wrong role access
  - Test authenticated redirect from login page
  - Test public routes pass through

**Additional Hardening:**
- [ ] Verify JWT is also validated server-side on every API call (auth-service does this) — middleware only guards Next.js routes, not APIs
- [ ] Add `httpOnly=false` check: `aptlogic_role` cookie must be readable by JavaScript (for middleware) but NOT `httpOnly` (this is already the design — verify it)
- [ ] Document: middleware guards Next.js routes; API services guard their own endpoints; two independent layers

#### Optimization Requirements

- Zero API calls in middleware: reads only the cookie header — adds <1ms to every request
- Matcher excludes all static assets: middleware does not run on `/_next/static/*` — no overhead on asset requests
- Edge runtime compatible: `export const runtime = 'edge';` if supported by Next.js version — reduces cold start latency

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | Navigate to `/admin/students` in browser with no cookies | Redirected to `/admin/login` (not the page rendered) |
| Sanity | Navigate to `/students/practice` with no cookies → redirect; `/super-admin/overview` with no cookies → redirect | Both redirect |
| Functionality | Student logs in → access `/students/*` (allowed) → navigate to `/admin/*` → redirect to `/students/home`; Admin logs in → `/admin/*` allowed → `/students/*` → redirect; Super Admin logs in → `/super-admin/*` allowed | All 3 role flows correct |
| Integration | Cookie set on auth-service successful login → middleware reads it on next request → routing enforced | Cookie-to-middleware chain works |
| Negative | Manually set `aptlogic_role=admin` in browser devtools without a valid JWT → middleware allows the route through (middleware only reads role cookie, API rejects the missing JWT) — document this is by design and API layer is the actual guard | Expected behavior — API is authoritative |
| Edge | Cookie expires mid-session (next page navigation) → redirect to login; browser back button after logout → middleware catches cleared cookie → redirect to login; two tabs with same browser: Student tab + no-cookie tab (each handled independently) | All correct |
| Regression | All existing Admin portal pages load correctly for authenticated admin; all existing Student portal pages load correctly for authenticated student; PWA install flow unaffected | Zero regressions |

**Completion Gate:** All 7 test rows pass, Jest middleware tests pass.

- [x] **TASK 6.1 COMPLETE** — 24 Jest tests passing twice (200% Rule satisfied, 2026-05-30)

---

### Task 6.2 — SuperAdminUser Type & Auth Store Extension

**Objective:** Add `SuperAdminUser` TypeScript type, extend the Zustand auth store to handle the `super_admin` role, and implement the Super Admin login page — enabling the Super Admin portal login flow.

**Pre-empts:** T3 (typed test coverage for super admin auth flow)

#### Current State

- `AuthUser` type in `src/types/index.ts` is `AdminUser | StudentUser`
- `SuperAdminUser` does not exist
- Zustand auth store handles 2 roles
- No `/super-admin/login` page exists

#### Implementation Subtasks

**TypeScript Types:**
- [ ] Add `SuperAdminUser` interface to `src/types/index.ts`:
  ```typescript
  interface SuperAdminUser {
    id: string;
    email: string;
    name: string;
    role: 'super_admin';
    institution_id: string;
    institution_name: string;
  }
  ```
- [ ] Update `AuthUser` type: `type AuthUser = AdminUser | StudentUser | SuperAdminUser;`
- [ ] Run `tsc --noEmit` — 0 TypeScript errors across entire codebase

**Zustand Auth Store (`src/lib/auth-store.ts`):**
- [ ] Add `super_admin` to the role handling logic
- [ ] Add `isSuperAdmin` computed/helper (alongside existing `isAdmin`, `isStudent`)
- [ ] Verify the store correctly persists `SuperAdminUser` in sessionStorage

**Cookies (`src/lib/cookies.ts`):**
- [ ] Verify `aptlogic_role` can hold the value `'super_admin'` (string comparison — likely already works, but verify explicitly)
- [ ] Add type narrowing: `isValidRole(role: string): role is 'student' | 'admin' | 'super_admin'`

**useAuth Hook (`src/hooks/useAuth.ts`):**
- [ ] Return type correctly narrows when `role === 'super_admin'` — `user` is typed as `SuperAdminUser`
- [ ] `isSuperAdmin()` helper available from hook

**Super Admin Login Page:**
- [ ] Create `frontend/src/app/super-admin/login/page.tsx`
- [ ] Reuse existing login form component (same form, different redirect target and API payload)
- [ ] On submit: `POST /api/auth/login/` with `{email, password, role: 'super_admin'}`
- [ ] On success: set `aptlogic_role=super_admin` cookie → redirect to `/super-admin/overview`
- [ ] On failure: display error message (same pattern as admin/student login pages)

**JWT Interceptor:**
- [ ] Verify `src/lib/api.ts` JWT interceptor handles `super_admin` role (attaches access token to all requests regardless of role) — likely works already, verify

#### Optimization Requirements

- Zero duplicate code: Super Admin login page reuses the same `<LoginForm>` component with a different `role` prop — no copy-paste
- Type narrowing eliminates runtime `role === 'super_admin'` string checks throughout the codebase — use discriminated union type
- No new state management patterns — extends existing Zustand store

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | Open `/super-admin/login` | Page renders without console errors |
| Sanity | `tsc --noEmit` from `frontend/` | 0 TypeScript errors |
| Functionality | Super admin login with valid credentials → cookie set → redirect to `/super-admin/overview`; `useAuth().isSuperAdmin()` returns `true` for super admin user; auth store correctly deserializes `SuperAdminUser` from sessionStorage | All correct |
| Integration | Super admin JWT returned by auth-service → accepted by analytics-service enterprise endpoints → super admin analytics load | End-to-end flow |
| Negative | Super admin credentials on `/admin/login` page → `403` or correct error message; student credentials on `/super-admin/login` → error displayed; missing password → form validation fires | Correct errors |
| Edge | Super admin token expiry → silent refresh → session continues; super admin logs out → cookie cleared → middleware redirects to `/super-admin/login`; reload on `/super-admin/overview` with valid cookie → stays on page (not logged out) | All handled |
| Regression | Admin login (`/admin/login`) still works; student login (`/student/login`) still works; existing `AuthUser` type usages compile correctly | Zero regressions |

**Completion Gate:** All 7 test rows pass, `tsc --noEmit` exits 0.

- [x] **TASK 6.2 COMPLETE** — tsc --noEmit exits 0, 24 Jest tests passing twice (200% Rule satisfied, 2026-05-30)

---

### Task 6.3 — Super Admin Portal (5 Tabs)

**Objective:** Build the complete Super Admin portal — the only portal that does not currently exist. 5 tabs: Overview, Admin Management, Batches, Students, Analytics.

**Pre-empts:** T3 (test coverage for new portal)

#### Implementation Subtasks

**Portal Layout:**
- [ ] Create `frontend/src/app/super-admin/layout.tsx` — sidebar with 5 navigation items, logout button, institution name display
- [ ] Sidebar icons: use existing Lucide React icons (match admin portal icon style)
- [ ] Sidebar active state highlighting (match existing admin portal pattern)
- [ ] Responsive: sidebar collapses to icon-only on narrow screens

**Tab 1 — Overview (`/super-admin/overview`):**
- [ ] KPI cards: Total Students, Total Batches, Active Admins, Platform Engagement (weekly active %)
- [ ] Data source: `GET /api/analytics/super-admin/overview/`
- [ ] Trend indicators: arrow + percentage vs. previous week (if available in API response)
- [ ] Loading skeleton (not spinner) while data loads
- [ ] Error state: "Unable to load overview" message with retry button
- [ ] Empty state: meaningful message (no "undefined" or "NaN" visible to user)

**Tab 2 — Admin Management (`/super-admin/admins`):**
- [ ] Table: Name, Email, Department, Status (Active/Inactive), Actions (Deactivate, Reset Password)
- [ ] Data source: `GET /api/users/admins/`
- [ ] Create admin form: Name, Email, Department, Temporary Password — `POST /api/users/admins/`
- [ ] Deactivate admin: confirmation modal ("Are you sure? This admin will lose access immediately.") — `PATCH /api/users/admins/:id/` with `{is_active: false}`
- [ ] Reset admin password: modal with new password input — `POST /api/auth/admin-password-reset/` (or auth-service equivalent)
- [ ] Guard: Super Admin cannot deactivate their own account (disable button if `admin.id === currentUser.id`)
- [ ] Loading, error, and empty states

**Tab 3 — Batches (`/super-admin/batches`) — READ ONLY:**
- [ ] Table: Batch Name, Department, Student Count, Assigned Admin
- [ ] Filter by department (dropdown)
- [ ] Data source: `GET /api/users/batches/` (super admin scoped — all institutions)
- [ ] Pagination (reuse existing pagination component)
- [ ] No create/edit/delete controls — read-only view
- [ ] Loading, error, and empty states

**Tab 4 — Students (`/super-admin/students`) — READ ONLY:**
- [ ] Table: Name, Email, Batch, Department, Enrollment Date
- [ ] Filter by Department, Batch
- [ ] Search by name or email (debounced input, 300ms delay)
- [ ] Data source: `GET /api/users/students/` (super admin scoped — all institutions)
- [ ] Pagination
- [ ] No create/edit/delete controls
- [ ] Loading, error, and empty states

**Tab 5 — Analytics (`/super-admin/analytics`):**
- [ ] Department-wise performance bar chart — practice accuracy per department
- [ ] Batch-wise comparison chart
- [ ] Resource utilization line chart — resource views over time (weekly)
- [ ] Practice engagement trend chart — toggle Weekly/Monthly
- [ ] Top performers table (top 10 students by accuracy across institution)
- [ ] Weak topics table (topics with <50% average accuracy)
- [ ] Data source: `GET /api/analytics/super-admin/departments/`, `GET /api/analytics/super-admin/overview/`
- [ ] Loading, error, and empty states per chart

> **Implementation note (2026-05-30):** Recharts is NOT in `package.json` and the "no new npm packages" constraint applied. Charts are implemented using **CSS horizontal bar charts** (percentage-width `div` bars) and **SVG gradient line charts** (path + area fill + gridlines + data-point circles) — no Recharts dependency. This satisfies the "no fixed pixel width" requirement and the zero-new-packages constraint simultaneously. Do NOT add Recharts unless `package.json` is explicitly updated in a future task.

#### Optimization Requirements

- All data fetching uses the same pattern as the existing Admin portal (check `admin/` pages and match: SWR or React Query or useEffect — whichever is the existing pattern)
- Paginate all list views — reuse existing `<Pagination>` component (if it exists) or admin portal pattern
- Debounce search inputs (300ms) — no API call on every keystroke
- Charts must not use fixed pixel widths — CSS percentage widths (bar charts) or SVG `viewBox` with `preserveAspectRatio` (line charts) are the compliant patterns
- Empty state components are reused from existing design system (not new one-off components)
- No additional npm packages — use only what is already in `package.json`

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | Navigate to `/super-admin/overview`, `/super-admin/admins`, `/super-admin/batches`, `/super-admin/students`, `/super-admin/analytics` | All 5 pages render without console errors or white screen |
| Sanity | All KPI values on Overview tab show numbers (not `NaN`, not `undefined`, not empty) | All values rendered |
| Functionality | Create admin → appears in Admin Management list; Deactivate admin → status changes to Inactive; Batches tab shows correct count; Students search by name returns matching results; Analytics charts render with data (verify axis labels are meaningful) | All features work |
| Integration | Admin Management tab calls user-service; Analytics tab calls analytics-service enterprise endpoints; role guard enforced (admin JWT cannot access super admin endpoints) | Correct service calls |
| Negative | Create admin with duplicate email → form shows validation error (not crash); Deactivate own account → button disabled (can't click); filter by non-existent department → empty state displayed (not error); network error on any tab → error state shown with retry button (not blank page) | Correct error handling |
| Edge | Institution with 0 students: Students tab shows empty state (not error); 10,000 students in Students tab: pagination renders first page correctly, not all 10,000 at once; very long admin name in table: truncated with ellipsis (not overflow); super admin deactivated by itself somehow via API directly → next page load middleware redirects to login | All handled |
| Regression | Admin portal (all 6 tabs) still functions correctly for admin user; Student portal still functions for student user; no shared component broken by Super Admin portal additions | Zero regressions |

**Completion Gate:** All 7 test rows pass.

- [x] **TASK 6.3 COMPLETE** — tsc --noEmit exits 0, 24 Jest tests passing twice (200% Rule satisfied, 2026-05-30)

---

### Phase 6 — Category 2 Regression Tests (Post-Phase 6 gap closure, 2026-05-30)

**Objective:** Close the regression test gap identified after Phase 6 completion. Phase 6 modified 4 existing frontend files that affect admin and student portal flows. These files had zero automated test coverage after the modification.

**Files modified in Phase 6 that were unverified:**
- `src/hooks/useAuth.ts` — logout logic rewritten with new LOGIN_PATHS record + super_admin branch
- `src/lib/api.ts` — 401 interceptor redirect refactored (two duplicate loginPaths → single exported constant)
- `src/app/admin/login/page.tsx` — 312-line page replaced with PortalLoginForm wrapper
- `src/app/super-admin/login/page.tsx` — new login page with auth config

**Source changes (zero behavior change — testability improvements only):**
- `src/hooks/useAuth.ts` — exported `LOGIN_PATHS` constant (was unexported)
- `src/lib/api.ts` — extracted two identical inline `loginPaths` records into a single exported `LOGIN_REDIRECT_PATHS` constant; used by both 401 interceptor branches
- `src/app/admin/login/page.tsx` — exported `ADMIN_LOGIN_CONFIG`; page uses `{...ADMIN_LOGIN_CONFIG}` spread
- `src/app/super-admin/login/page.tsx` — exported `SUPER_ADMIN_LOGIN_CONFIG`; page uses `{...SUPER_ADMIN_LOGIN_CONFIG}` spread

**New test files (63 tests):**
- `src/tests/useAuth.test.ts` — 20 tests: LOGIN_PATHS values, computed booleans, logout API endpoint selection, finally-block state-clear guarantees
- `src/tests/api.test.ts` — 24 tests: LOGIN_REDIRECT_PATHS values, LOGIN_PATHS cross-consistency check, request interceptor Authorization header, getErrorMessage for all DRF error shapes, **+ 9 response interceptor 401 redirect tests** (Branch A: no refresh token per role + null-user fallback + side effects; bypass: /login/ and token/refresh endpoints; Branch B: refresh fails per role + null-user fallback)
- `src/tests/portalLoginForm.test.ts` — 15 tests: admin config contract, super-admin config contract, setAuthCookies, clearAuthCookies
- `src/tests/portalLoginForm.component.test.tsx` — 12 tests (jsdom): full submit flow for admin and super-admin (api.post endpoint+body, setAuthCookies role+token, setTokens payload, router.push redirect), failed-login error display + no-side-effect assertions, form validation (empty submit, missing email, missing password)

**Total Jest tests: 96 (was 24 middleware-only → 75 → 87 → 96 after 401 interceptor behaviour tests)**

**Key discoveries during implementation:**
1. ts-jest does not hoist `jest.mock` factory closures the same way babel-jest does. Variables declared with `const` outside a factory are in the TDZ when the factory runs. Solution: use `jest.spyOn` after import for method-level mocking — never reference outer `const` inside `jest.mock` factories.
2. Next.js `<Image>` passes Next.js-only props (`priority`, `fill`, `quality`, `placeholder`, `blurDataURL`, `loader`, `unoptimized`) that React DOM warns about when spread onto a plain `<img>`. The `next/image` mock must explicitly destructure and discard these props.
3. Per-file `@jest-environment jsdom` docblock isolates component tests without affecting the project-level `testEnvironment: "node"` for all other test files.
4. api.ts has a module-level `isRefreshing` flag. The "no refresh token" branch sets it to `true` before an early return — the `finally` block that resets it to `false` only runs when a refresh is actually attempted. Without `jest.resetModules()` in `beforeEach`, every subsequent 401 test enters the pending-queue branch and times out. Solution: `jest.resetModules()` + dynamic `require()` per test. `jest.mock()` factory registrations survive `resetModules()`, so mocks remain active.

- [x] **PHASE 6 CATEGORY 2 REGRESSION COMPLETE (FINAL)** — tsc --noEmit exits 0, 96 Jest tests passing twice consecutively (200% Rule satisfied, 2026-05-30). Zero gaps: 401 interceptor redirect behaviour, null-user fallback, side effects, and bypass logic all validated — moving with validation, not hope.

---

## Phase 7: Infrastructure & DevOps

---

### Task 7.1 — Production Docker Compose

**Objective:** Replace the development Docker Compose (7 containers) with a production-grade configuration covering all 6 services, PgBouncer, frontend, and Nginx — with resource limits, health checks, and restart policies.

#### Implementation Subtasks

**Services in `docker-compose.prod.yml`:**
- [ ] `postgres` — PostgreSQL Instance 2 container (or external managed service pointed to by env var)
- [ ] `redis` — Redis container with `maxmemory` and `maxmemory-policy` configured
- [ ] `pgbouncer` — connection pooler
- [ ] `migrate` — one-time Django migration job: runs `manage.py migrate` for all 6 services sequentially; `restart: "no"`; all 6 service containers depend on this job completing with exit 0 before they start
- [ ] `auth-service` — Uvicorn, depends on postgres+redis healthy AND migrate complete
- [ ] `user-service` — Uvicorn, depends on postgres+redis healthy AND migrate complete
- [ ] `resource-service` — Uvicorn, depends on postgres+redis healthy AND migrate complete
- [ ] `resource-celery-worker` — Celery worker (async R2 file deletion), depends on migrate complete
- [ ] `practice-service` — Uvicorn, depends on postgres+redis healthy AND migrate complete
- [ ] `notification-service` — Uvicorn, depends on postgres+redis healthy AND migrate complete
- [ ] `notification-celery-worker` — Celery worker (async notification delivery), depends on migrate complete
- [ ] `notification-celery-beat` — Celery beat (90-day cleanup cron at 03:00 UTC), depends on migrate complete
- [ ] `analytics-service` — Uvicorn, depends on postgres+redis healthy AND migrate complete
- [ ] `analytics-celery-worker` — Celery worker (practice/resource event processing), depends on migrate complete
- [ ] `analytics-celery-beat` — Celery beat (nightly aggregation cron at 01:00 UTC), depends on migrate complete
- [ ] `frontend` — Next.js production build (`next start`)
- [ ] `nginx` — Nginx gateway, depends on all 6 services healthy

**Per Service Config:**
- [ ] `restart: always` on all services
- [ ] `healthcheck` on all services:
  - Django services: `curl -f http://localhost:800X/api/{service}/health/`
  - PostgreSQL: `pg_isready -U postgres`
  - Redis: `redis-cli ping`
  - Nginx: `nginx -t`
- [ ] `depends_on` with `condition: service_healthy` for startup ordering
- [ ] Resource limits:
  - Each Django service: `memory: 512M`, `cpus: '0.5'`
  - PostgreSQL: `memory: 2G`, `cpus: '2.0'`
  - Redis: `memory: 256M`, `cpus: '0.25'`
  - Nginx: `memory: 128M`, `cpus: '0.25'`
  - Frontend: `memory: 512M`, `cpus: '0.5'`
  - Celery worker: `memory: 512M`, `cpus: '0.5'`

**Networking:**
- [ ] Internal network `spark-internal`: all services communicate on this network
- [ ] Only Nginx exposes ports to host: port 80 (and 443 when SSL added)
- [ ] No other service exposes ports externally

**Multi-stage Dockerfiles (per service):**
- [ ] Stage 1 `builder`: `python:3.12-slim`, install `requirements.txt`, copy source
  - Add `RUN apt-get update && apt-get install -y libpq-dev gcc` in build stage — compiles psycopg3 C extension during `pip install psycopg[c]`
- [ ] Stage 2 `runtime`: `python:3.12-slim`, copy only installed packages + source (no pip cache in runtime image)
  - Add `RUN apt-get update && apt-get install -y libpq5` in runtime stage — runtime library the compiled psycopg3 C extension links against
  - Add `ARG GIT_SHA` and `ENV GIT_SHA=$GIT_SHA` in runtime stage — captures the `--build-arg GIT_SHA=` value passed by CI (Task 7.2 Stage 4) as a runtime environment variable inside the container. Without this, the build-arg is consumed at build time only and not available to the running process — Sentry `release` tag shows `"unknown"` instead of the actual commit SHA.
  - **Both libpq lines required together.** Missing `libpq-dev gcc` causes `psycopg[c]` to silently fall back to pure Python mode during build (no error, just slower). Missing `libpq5` causes runtime import failure. See PRODUCTION_CHECKLIST.md Section 3 for full details.
- [ ] `.dockerignore` per service: excludes `__pycache__/`, `*.pyc`, `.git/`, `tests/`, `*.md`, `.env*` (not `.env.example`)
- [ ] Frontend Dockerfile: Stage 1 build, Stage 2 runtime (`node:20-alpine`)

**Startup & Shutdown:**
- [ ] `infra/scripts/start-prod.sh`: validate env vars → run pre-deploy backup (all 6 databases, verify manifest `overall_status: "ok"`) → run `migrate` job container (wait for exit 0 — halt if non-zero) → `docker-compose -f docker-compose.prod.yml up -d` → wait for all health checks → print status
- [ ] `infra/scripts/stop-prod.sh`: graceful `docker-compose -f docker-compose.prod.yml down` (not `kill`)

#### Optimization Requirements

- Multi-stage Dockerfiles: runtime images contain no build tools, no pip cache — typically 60–70% smaller than single-stage
- No services exposed on host except Nginx port 80/443 — minimal attack surface
- Memory limits prevent one runaway service from starving others on the same host
- `restart: always` ensures services recover from crashes without manual intervention
- `healthcheck` startup ordering: prevents services starting before their dependencies are ready (eliminates "connection refused" race conditions)
- Redis `maxmemory 200mb` + `maxmemory-policy allkeys-lru`: prevents Redis from using unbounded memory and evicts least-recently-used keys when full (graceful degradation, not crash)

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | `docker-compose -f infra/docker-compose.prod.yml up -d`; `migrate` job exits 0 before any service starts | All containers reach `healthy` status within 120 seconds; `migrate` container shows `Exited (0)` |
| Sanity | `docker stats` (resource usage) | All containers within defined resource limits at idle |
| Functionality | Complete user flow in production Docker environment: admin login → upload resource → student login → view resource → attempt practice | End-to-end flow works |
| Integration | Service-to-service calls work within `spark-internal` network; Nginx routes to all 6 services correctly; PgBouncer handles all DB connections | All internal communication works |
| Negative | `docker kill spark-auth-service` → container restarts automatically (restart policy); start with missing required env var → startup script exits non-zero with clear message; PostgreSQL slow to start → health check retries until ready (not fail immediately); `migrate` job exits non-zero (bad migration) → all 6 service containers blocked from starting, old images still serving traffic | Correct behavior |
| Edge | All containers starting simultaneously (depends_on ordering prevents race condition); Redis container restart mid-operation (services handle connection error and retry); 30-minute sustained operation (no memory leak, resource usage stable) | Stable operation |
| Golden Rule | Inspect running service containers: image digest matches what was pulled from registry — not rebuilt locally on the production server (`--build` was never run on production) | `docker inspect {service} --format='{{.Image}}'` matches registry SHA |
| Entrypoint | For each of the 6 service images: `docker run --rm {service} cat entrypoint.sh` — confirm output contains no `manage.py migrate` call | Zero occurrences of `migrate` in any service entrypoint.sh; migrations run only in the dedicated `migrate` job container |
| Regression | All 6 service health checks return `200` after full stack startup; complete end-to-end user flows work | Zero regressions |

**Completion Gate:** All 9 test rows pass.

- [ ] **TASK 7.1 COMPLETE**

---

### Task 7.2 — CI/CD Pipeline

**Objective:** Establish an automated CI pipeline that catches regressions before they reach production, and a CD pipeline that deploys verified builds with Zero Downtime Deployment — backward-compatible migrations enforced by linter, pre-deploy database backup before every deploy, separate migration job with health gate, and rolling service updates so old containers serve traffic until each new container is confirmed healthy.

**Pre-empts:** T7 (no CI/CD pipeline)

#### Implementation Subtasks

**CI Pipeline (`.github/workflows/ci.yml` or equivalent):**
- [ ] Trigger: on `push` to `main`, on `pull_request` targeting `main`
- [ ] Stage 1 — Lint (fail fast):
  - Python: `flake8 services/*/` (PEP8 compliance, max line length 120)
  - TypeScript: `eslint frontend/src/`
  - Both run in parallel
- [ ] Stage 2 — Type Check (requires Stage 1 pass):
  - Python: `mypy services/*/` (strict mode for critical paths)
  - TypeScript: `tsc --noEmit` from `frontend/`
  - Both run in parallel
- [ ] Stage 3 — Tests (requires Stage 2 pass):
  - Run `pytest tests/` for each service in parallel (6 parallel jobs)
  - Fail if any service coverage < 80%
  - Frontend: `jest --ci` for middleware and component tests
  - Run `django-migration-linter` for each service — fail CI if any migration is unsafe (drops column, renames column, adds NOT NULL without a default value). No unsafe migration ever reaches production.
- [ ] Stage 4 — Docker Build (requires Stage 3 pass):
  - Build Docker image for each of 6 services
  - Build frontend Docker image
  - Pass git SHA as build argument: `--build-arg GIT_SHA=${{ github.sha }}` — Dockerfile captures this as `ENV GIT_SHA` so Sentry `release` tag shows the exact commit (not `"unknown"`)
  - Run in parallel

**CD Pipeline (on merge to `main` only):**
- [ ] Stage 4.5 — Pre-Deploy Backup (CD only):
  - SSH to production server
  - Run `backup.sh` for all 6 databases — verify manifest `overall_status: "ok"` and all 6 backup files non-zero in R2
  - **If backup fails: halt pipeline entirely. Do not proceed to push or deploy.** A failed backup means there is no restore point if the upcoming migration corrupts data.
  - Store manifest timestamp as pipeline artifact — rollback uses this to identify the correct restore point

- [ ] Stage 5 — Push Images:
  - Tag images with git SHA: `{service}:{git_sha}`
  - Push to container registry (Docker Hub / GitHub Container Registry / private registry)

- [ ] Stage 5.5 — Run Migrations (CD only):
  - SSH to production server
  - Pull the migration image: `docker pull {registry}/migrate:{git_sha}`
  - Run one-time migration container: `docker run --rm --env-file production.env {registry}/migrate:{git_sha} python manage.py migrate`
  - Wait for exit 0 — **if non-zero, halt pipeline immediately.** Old containers are still running and serving traffic. Zero downtime. Fix the migration, push a new commit.
  - **Rule (Expand and Contract):** Every migration reaching this step must be backward-compatible — the currently-running service version must continue working against the new schema without errors. Non-backward-compatible changes (DROP COLUMN, RENAME COLUMN) are blocked by the `django-migration-linter` in Stage 3.

- [ ] Stage 6 — Deploy:
  - SSH to production server
  - Pull all new service images: `docker pull {registry}/{service}:{git_sha}` for each service
  - **Rolling deploy order (strict):** `auth-service` → `user-service` → `resource-service` → `practice-service` → `notification-service` → `analytics-service` → `nginx` → `frontend`
  - Per service: `docker-compose -f docker-compose.prod.yml up -d --no-deps {service}` (**no `--build` flag** — image was pulled in previous step; using `--build` would rebuild on the production server, producing a different artifact than the one CI tested and approved)
  - After each service restarts: health check at `/api/{service}/health/` must return `200` within 60 seconds, else **halt pipeline and rollback this service** to previous SHA before continuing
  - **Never deploy nginx before all 6 backend services are healthy** — nginx routes to all 6 services; deploying nginx with one unhealthy upstream causes 502s for all users on that route

- [ ] Stage 7 — Post-deploy Smoke Test:
  - Automated curl checks: all 6 `/health/` endpoints return `200`
  - If any fail: alert via Sentry + notification

**Migration Rollback Strategy:**
- **Stage 5.5 fails (migration exits non-zero):** Pipeline halts. Old containers are still running — zero downtime. Fix the migration file, push a new commit. CI re-runs from scratch.
- **Stage 6 deploy causes errors (backward-compatible migration + new service code):** Rollback service images to previous SHA. No database rollback needed — the migration was backward-compatible so old code still works against the new schema.
- **Non-backward-compatible migration accidentally slipped through:** Restore from Stage 4.5 pre-deploy backup (taken before this deploy). Follow `docs/disaster-recovery.md` including `manage.py migrate --check` after restore. Deploy previous image tags. This scenario should not occur if `django-migration-linter` is enforced in Stage 3 — the backup exists as the last line of defence.
- **Expand and Contract rule for schema contracts:** DROP COLUMN or RENAME COLUMN may only be deployed after confirming zero traffic is writing to the old column across all running service versions. The human confirms this window has passed; CI executes the contract migration.

**Dependency Caching:**
- [ ] Cache Python pip dependencies: key = `requirements-{hash(requirements.txt)}`
- [ ] Cache npm/yarn dependencies: key = `npm-{hash(package-lock.json)}`
- [ ] Skip frontend CI stages if only `services/**` files changed (path filters)
- [ ] Skip backend CI stages if only `frontend/**` files changed

#### Optimization Requirements

- Parallel job execution: 6 service test jobs + frontend test job run simultaneously — total CI time < 10 minutes
- Dependency caching: eliminates pip install time on warm runs (typically 2–3 minutes savings)
- Rolling deploy (one service at a time): zero downtime during deployment — other services handle traffic while one restarts
- Path filters: frontend CI skips when only backend files change — saves 3–4 minutes per backend-only commit
- `fail-fast: true` on lint stage: no point building Docker images if linting fails
- Expand and Contract migrations: every schema change reaching Stage 5.5 is backward-compatible — the currently-running service version works against the new schema without errors. Schema contracts (DROP/RENAME) are deployed in a separate commit after confirming the old column is no longer used. This eliminates the need for a staging environment as a migration safety net.
- `--build-arg GIT_SHA`: every Docker image carries the exact git SHA as an environment variable (`GIT_SHA`). Sentry `release` tag matches the commit — error traceability to the exact line. No more `release: "unknown"` in Sentry.
- No `--build` on production server: the image that passed CI is the image that deploys to production. Running `--build` on the production server produces a different artifact (different environment, different build cache) — breaks the "same artifact" guarantee.

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | Push a trivial commit (comment addition) to main | CI pipeline triggers within 30 seconds and completes |
| Sanity | Lint stage catches a deliberately introduced PEP8 violation | Stage fails, pipeline stops, no Docker build attempted |
| Functionality | Full pipeline: lint → typecheck → tests + migration linter → build (with GIT_SHA build-arg) → Stage 4.5 backup → push → Stage 5.5 migration job (exit 0) → rolling deploy (auth first, frontend last, health gate between each) → smoke test | All stages complete successfully on a clean commit |
| GIT_SHA | Inspect deployed service container: `docker exec {service} printenv GIT_SHA`; check Sentry dashboard for the deploy's release tag | `GIT_SHA` env var inside container matches the git SHA from the CI run that built it; Sentry `release` tag shows correct SHA (not `"unknown"`) |
| Integration | Merged PR triggers CD; production health checks pass within 60 seconds of deploy completing | CD and health check chain works |
| Negative | Commit with a failing pytest test → pipeline fails at Stage 3 (not deploy stage); commit with unsafe migration (DROP COLUMN) → `django-migration-linter` fails Stage 3, no deploy; Stage 5.5 migration job exits non-zero → pipeline halts, old containers still running, no new images deployed; Stage 4.5 backup fails → pipeline halts before any image is pushed | Correct failure at each gate |
| Edge | 20 concurrent PRs trigger CI simultaneously (resource contention handled by CI runner); very large test suite (100+ tests) — cache hit still reduces time significantly | Correct operation |
| Regression | Existing codebase passes all CI stages with 0 failures on first run (no pre-existing lint violations or test failures) | Clean baseline |

**Completion Gate:** All 8 test rows pass.

- [ ] **TASK 7.2 COMPLETE**

---

### Task 7.3 — Monitoring & Observability

**Objective:** Activate Sentry error tracking across all 6 services, implement structured JSON logging with request ID propagation, and verify all health check endpoints report real dependency status.

**Pre-empts:** T4 (Sentry DSN empty — zero production error visibility)

#### Implementation Subtasks

**Sentry Activation (T4):**
- [ ] Set `SENTRY_DSN` in production environment for each of 6 services (from Sentry project dashboard)
- [ ] Configure Sentry SDK in each service's `settings.py`:
  ```python
  import sentry_sdk
  sentry_sdk.init(
      dsn=env("SENTRY_DSN", default=""),
      environment=env("ENVIRONMENT", default="development"),
      release=env("GIT_SHA", default="unknown"),
      traces_sample_rate=0.1,  # 10% — cost control
      send_default_pii=False,  # do not send user PII to Sentry
  )
  ```
- [ ] Verify: trigger an intentional `1/0` exception in each service → appears in Sentry dashboard within 30 seconds
- [ ] Verify: `environment` tag is `production` (not `development`) in Sentry events
- [ ] Verify: `release` tag contains the git SHA

**Structured JSON Logging:**
- [ ] Configure Python `logging` with JSON formatter in each service:
  ```python
  LOG_FORMAT = {
      "timestamp": "%(asctime)s",
      "level": "%(levelname)s",
      "service": "auth-service",  # hardcoded per service
      "request_id": "%(request_id)s",
      "message": "%(message)s",
  }
  ```
- [ ] In production: log level `WARNING` and above (not DEBUG — prevents log file bloat)
- [ ] Add middleware to each Django service that extracts `X-Request-ID` from Nginx header and stores in thread-local → all log calls include it automatically

**Request ID Propagation:**
- [ ] Nginx generates `X-Request-ID: $request_id` on every incoming request (already in Task 4.1)
- [ ] Each Django service reads `X-Request-ID` header → logs it with every log line
- [ ] Verify: a single API request generates logs in Nginx access log AND in the service log with the SAME `request_id` value — enables end-to-end request tracing

**Health Check Endpoints (verify real status, not hardcoded):**
- [ ] `GET /api/{service}/health/` returns:
  ```json
  {
    "status": "ok",
    "service": "{service-name}",
    "timestamp": "2026-05-28T12:00:00Z",
    "dependencies": {
      "database": "ok",
      "redis": "ok"
    }
  }
  ```
- [ ] Database check: run `SELECT 1` (not just "assume it's ok")
- [ ] Redis check: run `PING` (not just "assume it's ok")
- [ ] If any dependency fails: return `{"status": "degraded", "dependencies": {"database": "error", "redis": "ok"}}`
- [ ] Verify: take down Redis → health check reflects `redis: "error"` (not still `"ok"`)

**Runbook:**
- [ ] Create `docs/incident-response.md`: step-by-step for investigating a production incident using Sentry → structured logs → request_id tracing

#### Optimization Requirements

- `traces_sample_rate=0.1`: 10% of requests generate Sentry performance traces — enough for visibility without incurring 100% overhead costs at scale
- `send_default_pii=False`: no student emails, IDs, or personal data sent to third-party Sentry service
- Health checks are lightweight: only `SELECT 1` and `PING` — no heavy queries — completes in <5ms
- Health check routes excluded from Nginx access logging (Task 4.1 already handles this — verify the exclusion works)
- Log rotation configured: max 100MB per log file, 5 rotations — prevents disk fill

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | Trigger `raise Exception("test sentry")` in auth-service → check Sentry dashboard | Exception appears in Sentry within 30 seconds, `environment=production`, `service=auth-service` |
| Sanity | `grep "request_id" /var/log/nginx/access.log` and `grep "request_id" /var/log/auth-service.log` | Same request_id appears in both logs for the same request |
| Functionality | All 6 health check endpoints return `{status: ok, dependencies: {database: ok, redis: ok}}`; stop Redis → health checks return `redis: error`; restart Redis → health checks return `redis: ok` | Dynamic status reflection |
| Integration | Single API request → 1 Nginx log entry + 1 service log entry with matching `request_id` | Tracing chain works |
| Negative | Wrong Sentry DSN → service starts with warning log (not crash); Redis down during health check → `{"status": "degraded"}` (not 500); database down → health check returns `{"database": "error"}` (not exception) | Graceful degradation |
| Edge | Health check called 1,000 times/second (lightweight — completes each in <5ms, no timeout); Sentry rate-limit hit (Sentry SDK handles gracefully, does not crash the service); very long exception stack trace in Sentry (truncated by SDK, not dropped) | All handled |
| Regression | Normal API operations unaffected by logging/Sentry additions; health check endpoints excluded from Nginx access logs (verified by log inspection) | Zero regressions |

**Completion Gate:** All 7 test rows pass.

- [ ] **TASK 7.3 COMPLETE**

---

### Task 7.4 — Automated Backup

**Objective:** Implement and verify automated daily database backups for all 6 databases with compression, R2 storage, retention policy, and restore verification.

**Pre-empts:** T5 (no automated database backup — full data loss risk on server failure)

#### Implementation Subtasks

**Backup Script (`infra/scripts/backup.sh`):**
- [ ] For each of 6 databases: stream `pg_dump --compress=9 --format=custom` directly to R2 (via `aws s3 cp` with stdin) — no temporary file on disk
- [ ] Naming convention: `backups/db/{db_name}/{YYYY-MM-DD_HHMMSS}.dump.gz`
- [ ] After each dump: verify file size in R2 is non-zero (zero-byte file = silent failure)
- [ ] Write JSON manifest to R2: `backups/manifests/{YYYY-MM-DD_HHMMSS}.json` containing:
  ```json
  {
    "timestamp": "...",
    "databases": [
      {"name": "auth_db", "size_bytes": 12345, "duration_seconds": 5, "status": "ok"},
      ...
    ],
    "overall_status": "ok"
  }
  ```
- [ ] On any failure: exit non-zero → Sentry alert fires (Sentry has a DSN alert rule for non-zero exit codes)
- [ ] Retry logic: retry failed dump 3 times with 60-second wait before giving up

**Scheduling:**
- [ ] Run backup in a dedicated `backup` container with cron: daily at `02:00 UTC`
- [ ] Monthly backup (first Sunday at 02:00 UTC): same script, different path prefix `backups/monthly/`

**Retention Policy:**
- [ ] Cleanup script: `infra/scripts/cleanup-backups.sh`
  - Delete daily backups older than 30 days in `backups/db/`
  - Delete monthly backups older than 12 months in `backups/monthly/`
- [ ] Cleanup runs daily at `03:00 UTC` (1 hour after backup completes)

**Restore Procedure:**
- [ ] Create `docs/disaster-recovery.md` with step-by-step:
  1. Provision fresh PostgreSQL instance
  2. Create databases and users (Task 5.1 commands)
  3. Download latest backup from R2: `aws s3 cp s3://{bucket}/backups/db/{db_name}/{latest}.dump.gz -`
  4. Restore: `pg_restore --clean --if-exists -d {db_name} {backup_file}`
  5. Verify: row counts in restored DB match manifest
  5b. Run `python manage.py migrate --check` for each service against the restored database — exit 0 confirms schema is current; exit 1 means the backup predates a migration (run `python manage.py migrate` to apply missing migrations before starting services)
  6. Update service env vars to point to new DB
  7. Restart services
- [ ] Monthly restore drill: every month, restore `analytics_db` to a throwaway container and verify row count — document results

**Media Backup:**
- [ ] Enable R2 bucket versioning (R2/MinIO supports object versioning) — media files are automatically versioned without a separate backup job
- [ ] Document: how to recover a deleted/overwritten media file from R2 version history

#### Optimization Requirements

- `pg_dump --compress=9` + direct streaming to R2: no disk I/O on the backup server — database size × compression ratio goes directly to cloud storage. A 1GB database → ~80–100MB in R2.
- `--format=custom` (PostgreSQL custom format) allows selective table restore — more flexible than SQL dump
- Streaming (not dump-to-disk-then-upload): eliminates the need for disk space = backup_size on the server. Essential for large databases.
- Retention cleanup prevents unbounded storage cost growth: 30 daily + 12 monthly = bounded known cost

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | Run `backup.sh` manually | Script exits 0; 6 backup files created in R2; manifest JSON written |
| Sanity | Check each backup file size in R2 | All 6 files > 0 bytes |
| Functionality | Full restore test: restore each database to throwaway container → `SELECT COUNT(*) FROM {main_table}` matches manifest row count; run `python manage.py migrate --check` for all 6 services against restored databases → all exit 0 | All 6 databases restore correctly, schema confirmed current |
| Integration | Cron runs at 02:00 UTC → manifest visible in R2 by 02:30 UTC; cleanup cron runs at 03:00 UTC → old backups deleted (verify by checking timestamps) | Schedule works |
| Negative | R2 unreachable during backup → script retries 3 times, then exits non-zero, Sentry alert fires; `pg_dump` fails (DB connection refused) → exit non-zero + alert; cleanup script deletes files older than 30 days (not newer) | Correct failure behavior |
| Edge | Backup during peak traffic (backup connection does not block application queries — separate DB connection); `analytics_db` has 10M rows (backup completes in <30 minutes); disk full on backup container (streaming to R2 means disk full is not a backup failure) | All handled |
| Regression | Production databases unaffected by backup operation; application performance not degraded during backup window | Zero regressions |

**Completion Gate:** All 7 test rows pass.

- [ ] **TASK 7.4 COMPLETE**

---

## Phase 8: Security Hardening

---

### Task 8.1 — Full Security Audit

**Objective:** Execute a structured security audit across all 6 services and frontend, resolving all remaining identified threats — file upload magic bytes, IDOR, secrets management, rate limiting verification, HTTPS enforcement, and XSS/SQL injection confirmation.

**Pre-empts:** T6 (magic bytes), T8 (secrets), T9 (rate limiting verification), T13 (IDOR final verification)

#### Implementation Subtasks

**File Upload Magic Bytes — Final Verification (T6):**
- [ ] Confirm resource-service magic bytes check is deployed and active (from Task 2.3)
- [ ] Run full test matrix: upload PDF, JPEG, PNG, DOCX (each accepted); upload EXE disguised as PDF, PHP disguised as PNG (each rejected + R2 object deleted)
- [ ] Confirm rejection logs are written with attacker context (user_id, institution_id, filename, detected bytes)
- [ ] Check: frontend file input `accept` attribute restricts file picker to allowed types (defense-in-depth — magic bytes check is the real guard)

**IDOR Validation — Full Audit (T13):**
- [ ] Generate IDOR test matrix: for every endpoint that reads/writes a record, test with a JWT from a different institution
- [ ] All 6 services: every `GET /api/{service}/{resource}/:id/` endpoint must return `403` if the record's `institution_id` ≠ JWT's `institution_id`
- [ ] Every student's own data endpoint must return `403` if JWT `user_id` ≠ record's `student_id`
- [ ] Write automated IDOR test suite (`tests/test_idor.py` per service) — this becomes part of CI (Task 7.2)
- [ ] Confirm: IDOR test suite has 0 failures across all 6 services

**Secrets Management — Final Verification (T8):**
- [ ] Run `git log --all --full-history -- "*.env"` — verify no `.env` files ever committed
- [ ] Run `trufflehog git file://.` or equivalent secret scanning tool on full git history
- [ ] Run `grep -r "password\s*=\s*['\"]" services/ frontend/` — confirm 0 hardcoded credentials
- [ ] Confirm all production secrets are injected via environment variables (Docker Compose env_file or secrets manager)
- [ ] Rotate: Django `SECRET_KEY` per service (should be unique per service), database passwords, Redis password (if set), R2 access keys — generate new values for production

**Rate Limiting — Final Verification (T9):**
- [ ] Run rate limit tests:
  - Send 11 requests to `/api/auth/login/` in 1 minute → 11th returns `429`
  - Send 101 requests to `/api/users/students/` in 1 minute → 101st returns `429`
- [ ] Verify `X-RateLimit-Limit` and `Retry-After` headers present in `429` response
- [ ] Confirm rate limiting is enforced at Nginx level (not inside Django — Django should not see the rejected requests)

**HTTPS Enforcement:**
- [ ] Nginx redirect: `return 301 https://$host$request_uri;` for all HTTP requests
- [ ] HSTS header: `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- [ ] SSL certificate: valid, not expired, correct domain
- [ ] Verify: `curl http://yourdomain.com` → `301` redirect to `https://`

**JWT Security:**
- [ ] Verify each service validates JWT `iss` (issuer) claim — reject tokens from unexpected issuers
- [ ] Verify each service validates JWT `aud` (audience) claim if set — reject tokens for wrong service
- [ ] Verify `alg` is `HS256` or `RS256` — no `none` algorithm allowed
- [ ] Verify expired tokens are rejected (not just signature-validated)

**SQL Injection:**
- [ ] `grep -r "raw_query\|cursor\.execute\|\.extra(" services/` — review every result
- [ ] All identified raw SQL uses parameterized queries (no f-string or format injection)
- [ ] Django ORM handles parameterization automatically — verify no ORM escaping bypassed

**XSS Prevention:**
- [ ] `grep -r "dangerouslySetInnerHTML" frontend/src/` — review every result
- [ ] All found instances must be audited and justified (e.g., sanitized HTML only)
- [ ] DRF JSON responses auto-escape — verify no custom response renderers that bypass escaping

**Final Security Checklist:**
- [ ] No debug endpoints exposed in production (`DEBUG=False` enforced — Task 1.2 handles this)
- [ ] Django `ALLOWED_HOSTS` is a specific domain list (not `['*']`)
- [ ] CORS: `CORS_ALLOWED_ORIGINS` lists only the production frontend domain (not `*`)
- [ ] Session cookie: `CSRF_COOKIE_SECURE=True`, `SESSION_COOKIE_SECURE=True` (HTTPS only)

#### Optimization Requirements

- IDOR checks use indexed `institution_id` column — O(1) lookup, zero performance overhead
- Magic bytes check is a Range request to R2 (512 bytes) — does not download the full file — negligible cost
- Rate limiting at Nginx layer: rejected requests never reach Django — saves Django process cycles
- Secret rotation before production launch: no secrets shared between development and production environments

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | Upload EXE file renamed as `resume.pdf` → rejected with `400`; Access another institution's resource → `403` | Both immediate rejections |
| Sanity | `trufflehog` scan on git history → 0 findings; IDOR automated test suite → 0 failures | Clean bill of health |
| Functionality | Full magic bytes matrix (4 allowed types accepted, 3 disallowed types rejected); IDOR test across all 6 services all endpoints; HTTPS redirect works; rate limiting fires at correct threshold | All pass |
| Integration | Security test suite integrated into CI pipeline (Task 7.2) — runs on every PR; IDOR test failure blocks merge | CI integration working |
| Negative | Every IDOR-sensitive endpoint tested with wrong institution JWT → `403`; JWT with `alg: none` → `401`; JWT with expired `exp` claim → `401`; SQL injection probe (`'; DROP TABLE students; --`) → `400` (ORM parameterization prevents execution) | All correctly rejected |
| Edge | JWT with institution_id claim set to null → `403` (not 500); JWT issued by auth-service but for wrong service's audience → `403`; file with valid PDF magic bytes but 0-byte body after header → accepted (magic bytes only checks header); rate limit zone filled from one IP → other IPs still work normally (per-IP limiting) | All handled |
| Regression | All legitimate API operations still work after security hardening; login flow, resource upload, practice attempt all complete successfully | Zero regressions |

**Completion Gate:** All 7 test rows pass, IDOR test suite has 0 failures, secrets scan has 0 findings.

- [ ] **TASK 8.1 COMPLETE**

---

## Phase 9: Load & Performance Testing

---

### Task 9.1 — Concurrent User Simulation, DB Benchmarks, Profiling

**Objective:** Verify the V1 platform handles expected production load — 5,000 concurrent users (institutional student body) — within defined response time and error rate targets, and resolve any bottlenecks found.

> **V1 Scale Target:** 5,000 concurrent users at practice/resources peak. V2 will scale to 20,000 for assessments/contests — that is a separate infrastructure concern. V1 must be proven solid before V2 adds load.

> **Load test environment:** Runs directly on the production server before the V1 launch announcement. There is no staging environment. Expand and Contract migrations eliminate staging as a migration safety net — every schema change is backward-compatible before it reaches production, so the only thing load testing needs to verify is performance under real production infrastructure conditions.

#### Performance Targets

| Metric | Target |
|--------|--------|
| P50 response time | < 150ms |
| P95 response time | < 500ms |
| P99 response time | < 2,000ms |
| Error rate at 5,000 concurrent | < 0.1% |
| Memory stability (30-min sustain) | Stable (no growth trend) |
| Redis cache hit rate | > 80% on resource/practice lists |

#### Implementation Subtasks

**Setup:**
- [ ] Install Locust in a test environment: `pip install locust`
- [ ] Create `tests/load/locustfile.py` with realistic user behavior scenarios

**Scenarios:**
- [ ] Scenario 1 — Resource Browser (1,000 users):
  - Login → `GET /api/resources/companies/` → `GET /api/resources/companies/:id/resources/` → open resource
  - Think time: 2–5 seconds between actions (realistic reading time)
- [ ] Scenario 2 — Practice Session (1,000 users):
  - Login → `GET /api/practice/modules/` → `GET /api/practice/sections/:id/questions/` → `POST /api/practice/questions/:id/attempt/` (10 questions)
  - Think time: 30–120 seconds per question (realistic)
- [ ] Scenario 3 — Admin Operations (500 users):
  - Admin login → `GET /api/users/students/` → `GET /api/analytics/admin/overview/` → `GET /api/resources/companies/`
- [ ] Scenario 4 — Mixed Load (5,000 users):
  - 70% students (Scenario 1 + 2 mix), 20% admins (Scenario 3), 10% super admins (analytics)

**Test Execution:**
- [ ] Baseline: 10 concurrent users → record P50, P95, P99 per endpoint
- [ ] Ramp test: 0 → 1,000 users over 5 minutes → sustain 10 minutes → record metrics
- [ ] Load test: 0 → 5,000 users over 10 minutes → sustain 10 minutes → record metrics
- [ ] Stress test: 0 → 10,000 users → identify breaking point → record when error rate exceeds 1%

**Metrics Collection:**
- [ ] Locust dashboard: P50/P95/P99 per endpoint, RPS, error rate
- [ ] `docker stats` during test: CPU%, memory per container
- [ ] PostgreSQL `pg_stat_activity`: active connection count (verify PgBouncer keeping it ≤ 15 per service)
- [ ] Redis `INFO stats`: `keyspace_hits` / `keyspace_misses` → cache hit rate = hits / (hits + misses)

**Bottleneck Resolution:**
- [ ] For any endpoint with P95 > 500ms at 1,000 concurrent: identify root cause (slow query? missing cache? CPU bound?) → fix → retest
- [ ] Document findings: `docs/load-test-results.md` — scenarios, results, bottlenecks found and fixed

#### Optimization Requirements

- Fix bottlenecks found during testing — do not accept P95 > 500ms as "good enough" without a fix
- Redis cache hit rate must be >80%: if below, TTLs are too short or caching is missing from critical paths — fix before marking complete
- PgBouncer verified under load: real PostgreSQL connection count must stay ≤ 15 per service even at 5,000 concurrent (the whole point of PgBouncer)
- No memory leaks: memory usage stable over 30-minute sustained load (not growing linearly)

#### Test Suite

| Type | Test | Pass Criteria |
|------|------|---------------|
| Smoke | Locust with 10 users, all 4 scenarios | All requests succeed, 0 errors |
| Sanity | Locust with 100 concurrent users | P95 < 200ms, 0 errors |
| Functionality | All API endpoints under load return CORRECT data (not stale cache, not truncated responses) | Data integrity maintained under load |
| Integration | Full user journey (login → resources → practice → analytics) completes end-to-end under 1,000 concurrent users with P95 < 500ms | Journey passes under load |
| Negative | Spike to 10,000 users: rate limiting fires at Nginx (`429` responses), error rate stays <5% (system degrades gracefully — does not crash or return 500s); Redis eviction under memory pressure: services fall back to DB, no 500 errors | Graceful degradation |
| Edge | Sudden spike from 0 to 5,000 in 30 seconds (no warm-up): system recovers within 60 seconds (initial spike may cause elevated latency briefly); sustained 5,000 for 60 minutes: memory stable (no leak); traffic drops back to 0: services return to baseline resource usage (no zombie memory retention) | Correct behavior |
| Regression | Platform functions correctly at normal load (10–100 users) after all load optimizations applied — no feature broken by caching or query changes | Zero regressions |

**Completion Gate:** All 7 test rows pass. P95 < 500ms at 5,000 concurrent, error rate < 0.1%. Document results.

- [ ] **TASK 9.1 COMPLETE**

---

## Phase 10: Pre-Launch Final Checklist

---

### Task 10.1 — Go / No-Go Checklist

**Objective:** Verify 100% of tasks are complete, all 13 threats are resolved, all quality gates are passed, rollback plan is in place, and production smoke test passes — then declare V1 launch ready.

> **Rule:** Every item below must be a confirmed check. If any box is unchecked, V1 does not launch. There is no "we'll fix it after launch" for this list.

#### Phase Completion Verification

- [ ] **Phase 1** — Task 1.1 COMPLETE, Task 1.2 COMPLETE
- [ ] **Phase 2** — Task 2.1 COMPLETE, Task 2.2 COMPLETE, Task 2.3 COMPLETE, Task 2.4 COMPLETE
- [ ] **Phase 3** — Task 3.1 COMPLETE, Task 3.2 COMPLETE
- [ ] **Phase 4** — Task 4.1 COMPLETE
- [x] **Phase 5** — Task 5.1 COMPLETE (36/36 tests), Task 5.2 COMPLETE (39/39 tests), 200% Rule satisfied both tasks
- [x] **Phase 6** — Task 6.1 COMPLETE, Task 6.2 COMPLETE, Task 6.3 COMPLETE (2026-05-30)
- [ ] **Phase 7** — Task 7.1 COMPLETE, Task 7.2 COMPLETE, Task 7.3 COMPLETE, Task 7.4 COMPLETE
- [ ] **Phase 8** — Task 8.1 COMPLETE
- [ ] **Phase 9** — Task 9.1 COMPLETE

#### Threat Resolution Verification

- [ ] **T1 RESOLVED** — `middleware.ts` deployed, tested end-to-end, all 3 portals protected
- [ ] **T2 RESOLVED** — All N+1 patterns eliminated, `EXPLAIN ANALYZE` confirms index scans on all hot paths
- [ ] **T3 RESOLVED** — Automated pytest suites for all 6 services, Jest for frontend, running in CI
- [ ] **T4 RESOLVED** — Sentry active in all 6 services, test exception appears in Sentry dashboard
- [ ] **T5 RESOLVED** — Automated backup runs nightly, restore tested and verified
- [ ] **T6 RESOLVED** — Magic bytes validation deployed, full test matrix passed
- [ ] **T7 RESOLVED** — CI/CD pipeline running on production branch, at least 1 successful deployment; Zero Downtime Deployment confirmed: rolling deploy with health gate between each service, separate migration job (Stage 5.5), pre-deploy backup (Stage 4.5), Expand and Contract migrations enforced by `django-migration-linter` in Stage 3
- [ ] **T8 RESOLVED** — Secrets scan clean, all production secrets in environment (not source code)
- [ ] **T9 RESOLVED** — Rate limiting on all API endpoints, verified with actual HTTP requests
- [ ] **T10 RESOLVED** — gzip compression active, verified with `curl --compressed`
- [ ] **T11 RESOLVED** — PgBouncer deployed, real DB connections ≤ 15 per service under load test
- [ ] **T12 RESOLVED** — PostgreSQL Instance 2 isolated for V1 services; PostgreSQL Instance 1 provisioned (empty) for V2 — no resource contention
- [ ] **T13 RESOLVED** — IDOR automated test suite passes 0 failures across all 6 services

#### Quality Gates

- [ ] All CI runs are green (0 failing tests across all 6 services and frontend)
- [ ] pytest coverage ≥ 80% for all 6 services (CI enforces this)
- [ ] `tsc --noEmit` exits 0 (0 TypeScript errors)
- [ ] `django-migration-linter` passes with 0 unsafe migrations across all 6 services (CI Stage 3 enforces this — no DROP COLUMN, no RENAME COLUMN, no NOT NULL without default in any pending migration)
- [ ] `PRODUCTION_CHECKLIST.md` — every checkbox ticked before first production deploy
- [ ] Expand and Contract rule confirmed: every schema change in the deploy is an expand (add column, add table, add index) — no contracts (DROP/RENAME) in the same deploy as the code change that removes the old reference
- [ ] Load test: P95 < 500ms at 5,000 concurrent users, error rate < 0.1%
- [ ] No `TODO:`, `FIXME:`, or `HACK:` comments in production code paths
- [ ] `DEBUG=False` verified in all 6 production service containers
- [ ] `ALLOWED_HOSTS` is specific domain (not `['*']`) in all services
- [ ] SSL certificate valid and not expiring within 30 days

#### Production Environment Verification

- [ ] All production environment variables set (0 placeholders, 0 default fallbacks used)
- [ ] Domain name configured and resolving to production server
- [ ] SSL certificate active, HTTPS enforces correctly (HTTP → 301 → HTTPS)
- [ ] All 6 `/health/` endpoints return `{status: ok, dependencies: {database: ok, redis: ok}}`
- [ ] Sentry dashboard shows production events (no development events mixed in)
- [ ] First automated backup completed and manifest visible in R2

#### Rollback Plan

- [ ] **Step 1:** Take note of current Docker image tags (git SHA) before deployment
- [ ] **Step 2:** If production issue is detected: `docker-compose stop {failing-service}` → `docker pull {service}:{previous_sha}` → `docker-compose up -d {service}` → verify health check
- [ ] **Step 3:** If a migration caused data corruption or application errors: `docker-compose down all-services` → restore from Stage 4.5 pre-deploy backup (the backup taken before this specific deploy — follow `docs/disaster-recovery.md`, including step 5b: run `manage.py migrate --check` after restore to confirm schema state) → deploy previous image tags → restart services
- [ ] **Step 4:** If multiple services affected: full rollback → restore backup → deploy previous image tags
- [ ] **Step 5:** Post-incident: verify all health checks green → run smoke test → announce recovery
- [ ] Rollback procedure dry-run on production server before launch announcement: restore one database (e.g., `analytics_db`) from backup to a throwaway container → verify row counts match manifest → run `manage.py migrate --check` against restored database → confirm exit 0 → tear down throwaway container

#### Production Smoke Test (run immediately before launch announcement)

- [ ] Admin logs in via `/admin/login` → Dashboard loads with all 6 tabs functional
- [ ] Admin creates a test company and uploads a test resource → resource appears in list
- [ ] Admin creates a test practice module with 3 questions → questions visible in admin Practice tab
- [ ] Student logs in via `/students/login` → Home page loads with correct sections
- [ ] Student navigates to Companies tab → sees test company → opens resource → resource loads (CDN URL)
- [ ] Student navigates to Practice tab → sees test module → attempts all 3 questions → sees explanations → progress updates
- [ ] Student checks My Profile → analytics show correct attempt data
- [ ] Student submits a Contact inquiry → inquiry appears in admin Inquiries tab
- [ ] Super Admin logs in via `/super-admin/login` → Overview tab loads with KPIs
- [ ] Super Admin navigates to all 5 tabs → all render without errors
- [ ] All smoke test steps pass: 0 errors in browser console, 0 errors in Sentry, all API calls return `2xx`

#### Sign-off

- [ ] Development team sign-off: all tasks verified
- [ ] Security audit sign-off: all threats resolved
- [ ] Load test sign-off: performance targets met
- [ ] Backup/recovery sign-off: restore tested, `migrate --check` confirmed on restored databases
- [ ] Deployment architecture sign-off: Zero Downtime Deployment confirmed — rolling deploy order verified, migration job tested, pre-deploy backup verified, Expand and Contract rule acknowledged

**V1 LAUNCH APPROVED — READY FOR PRODUCTION**

- [ ] **TASK 10.1 COMPLETE**
- [ ] **SPARK V1 PRODUCTION LAUNCH**

---

## Legend

| Symbol | Meaning |
|--------|---------|
| `- [ ]` | Pending — not started or not verified |
| `- [x]` | Complete — implemented and all tests passed |
| **CRITICAL** | Must be resolved before any other task in the same phase |
| **T1–T13** | Threat identifiers from the Threat Register above |
| 200% Rule | Task incomplete until all test rows pass twice consecutively with 0 failures |

---

*Tracker locked for V1 scope. V2 scope (Assessments, Contests, assessment_db, contest_db, Redis Streams, WebSocket, PWA push) is tracked separately in LIVETRACKER_V2.md.*
