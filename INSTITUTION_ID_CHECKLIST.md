# Institution ID Security Checklist

**Role:** This file is the authority on multi-tenancy rules for the SPARK platform.  
**Usage:** Reference this file **before** starting any new feature implementation and **validate against it after** completion.  
**Why it exists:** `institution_id` is the hard boundary between colleges. One college must never read, write, or even detect the existence of another college's data.

---

## How institution_id Flows Through the System

```
Super Admin account (DB)
    └── institution_id stored on User record
            └── JWT token carries institution_id as a claim
                    └── request.user.institution_id available on every authenticated request
                            └── every account created by super admin inherits it
                            └── every query must filter by it
```

**Source of truth:** `request.user.institution_id`  
**Never accepted from:** request body, query params, URL params, or frontend input.

---

## Rule 1 — Every New Model

Every model that stores institution-specific data **must** have this field:

```python
institution_id = models.UUIDField(null=True, blank=True, db_index=True)
```

And a corresponding index in `Meta`:

```python
class Meta:
    indexes = [
        models.Index(fields=["institution_id"], name="idx_<modelname>_institution_id"),
    ]
```

**Exception — models that do NOT need institution_id:**
- `OutboxEvent` — internal worker queue, not tenant data
- `django_migrations`, `django_content_type` — Django internal tables
- Any model that holds only platform-level config (not per-college data)

**After adding the field:** always run `python manage.py makemigrations` and apply it.

---

## Rule 2 — Every New View (Read)

Every GET endpoint that returns institution-specific data must filter by institution_id:

```python
def get(self, request):
    institution_id = getattr(request.user, "institution_id", None)
    records = MyModel.objects.filter(institution_id=institution_id)
    ...
```

**Never do this:**
```python
records = MyModel.objects.all()           # wrong — returns all colleges' data
records = MyModel.objects.filter(pk=pk)   # wrong — no institution scope
```

---

## Rule 3 — Every New View (Create)

Every POST/PUT endpoint that creates institution-specific data must stamp institution_id from the JWT — never from the request body:

```python
def post(self, request):
    institution_id = getattr(request.user, "institution_id", None)
    serializer = MySerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(institution_id=institution_id)   # stamped here
    ...
```

**Never do this:**
```python
institution_id = request.data.get("institution_id")   # wrong — attacker can inject any UUID
```

---

## Rule 4 — Every New View (Fetch Single Object)

Every endpoint that fetches a single record by PK must include institution_id in the lookup to prevent IDOR:

```python
def _get(self, pk, institution_id):
    return get_object_or_404(MyModel, pk=pk, institution_id=institution_id)
```

**Never do this (IDOR vulnerability):**
```python
obj = MyModel.objects.get(pk=pk)
if obj.institution_id != request.user.institution_id:
    return error_response("Forbidden", status_code=403)
# Wrong — the 403 tells an attacker the object exists; 404 must be returned instead
```

---

## Rule 5 — Every New Cache Key

Every cache key that stores institution-specific data must include institution_id:

```python
def _my_cache_key(institution_id, record_id):
    return f"service_name:resource:{institution_id}:{record_id}"
```

**Never do this:**
```python
def _my_cache_key(record_id):
    return f"service_name:resource:{record_id}"   # wrong — cross-tenant cache poisoning
```

---

## Rule 6 — Serializers That Expose Sensitive Fields

If a serializer is used for both admin and student responses, create a dedicated student-facing serializer that excludes sensitive fields at the **serializer level** — not with `pop()` in the view.

**Correct pattern (from practice-service):**
```python
class StudentMySerializer(MySerializer):
    """Student-facing — sensitive_field excluded at serializer level."""
    class Meta(MySerializer.Meta):
        fields = [f for f in MySerializer.Meta.fields if f != "sensitive_field"]
```

**Never do this:**
```python
data = MySerializer(obj).data
data.pop("sensitive_field", None)   # wrong — fragile; any new endpoint that forgets pop() leaks data
```

---

## Rule 7 — Ownership Checks (Non-institution Guards)

For user-owned resources (e.g. a student's own notification), include the ownership filter directly in the query — not as a separate check after fetching:

```python
# Correct
notification = get_object_or_404(Notification, pk=pk, user_id=user_id, is_deleted=False)

# Wrong — IDOR oracle (attacker learns if pk exists via 403 vs 404)
notification = Notification.objects.get(pk=pk)
if notification.user_id != user_id:
    return error_response("Forbidden", status_code=403)
```

---

## Validation Checklist — After Every New Feature

Go through each item and confirm:

### Models
- [ ] Every new model that stores college data has `institution_id = models.UUIDField(null=True, blank=True, db_index=True)`
- [ ] An index named `idx_<modelname>_institution_id` exists in `Meta.indexes`
- [ ] `makemigrations` was run and the migration file is committed

### Views
- [ ] Every list/filter query uses `.filter(institution_id=institution_id)`
- [ ] Every create/save call uses `serializer.save(institution_id=institution_id)`
- [ ] Every single-object fetch uses `get_object_or_404(Model, pk=pk, institution_id=institution_id)`
- [ ] `institution_id` is always read from `request.user.institution_id` — never from request body

### Cache
- [ ] Every cache key that stores per-college data includes `institution_id` in the key string

### Serializers
- [ ] No sensitive fields are hidden with `pop()` in views — use a dedicated serializer instead

### Tests
- [ ] At least one test verifies that User A from Institution A cannot access Institution B's data
- [ ] At least one test verifies that institution_id is stamped correctly on creation (not overridable from request body)

---

## Rule 8 — Credentials Must Never Be Hardcoded

All default passwords (IT, super admin, admin, student) must be read from environment variables — never hardcoded in source code. The credentials live in `auth-service/.env`. As of 2026-08-20, IT is the platform's bootstrapped root account (replacing super_admin in that role); Super Admin, Admin, and Student accounts are all created afterward by IT:

```
IT_EMAIL=ithead@gmail.com
IT_PASSWORD=<strong-unique-password>
SUPERADMIN_DEFAULT_PASSWORD=<strong-default>
ADMIN_DEFAULT_PASSWORD=<strong-default>
STUDENT_DEFAULT_PASSWORD=<strong-default>
```

In production: set strong values in `.env` before first deployment. Never commit real passwords to git.

---

## Rule 9 — Force Password Change on First Login

Every account created by the system (super admin, admin, student, IT) must have `force_password_change=True`. The JWT carries this flag. The frontend must check it on every login response and redirect to the password change screen if `True`. After a successful password change, the flag is cleared and new tokens are issued.

---

## Rule 10 — Token Version for Immediate Revocation

The `token_version` integer is stored on every User record and carried in every JWT. When a password is reset or an institution_id correction is required, `token_version` is incremented. Auth-service validates token_version against the DB on every request. Old tokens with a stale version are rejected immediately — before their natural expiry.

---

## Rule 11 — Generating a New Institution ID

There is no automated "create a new college" feature (see `V2_GAPS.md` Gap 1). For each new deployment, the institution_id must be generated and placed manually:

```bash
python -c "import uuid; print(uuid.uuid4())"
```

Copy the printed value into that deployment's `services/auth-service/.env`:
```
INSTITUTION_ID=<the-value-you-copied>
```

This only matters the **first time** the IT account is created on an empty database — `create_default_it` (replaced `create_default_superadmin` 2026-08-20, when IT became the bootstrapped root role) reads it once at that point and stamps it onto the new IT record. On every later container start, if `.env`'s `INSTITUTION_ID` differs from what's already saved in the database, the container **refuses to start** (`CommandError`) rather than silently applying the wrong value — this is the hard boundary protection described above, enforced at startup, every time.

---

## Rule 12 — Backfill Is Loud, Audit Cross-Account Drift Separately

**Backfill case:** if an existing IT account has no `institution_id` yet (e.g., created before this field existed), `create_default_it` fills it in from `.env` automatically. This is a one-way action — any later `.env` value that differs will be rejected by the mismatch guard (Rule 11). Because of that, the backfill emits a `WARNING`-level log entry, not a quiet success message, so a wrong UUID is never silently locked in without anyone noticing:

```
institution_id BACKFILLED for IT account '...' -> <uuid>. ... STOP and fix INSTITUTION_ID in .env now if unexpected.
```

**Cross-account drift:** `create_default_it` only validates the IT account's *own* record — it has no visibility into whether super_admin, admin, or student accounts already have a different or missing `institution_id`. Run this separately to check everyone else:

```bash
docker exec <auth-service-container> python manage.py audit_institution_consistency
```

It compares every non-IT account against the IT account's `institution_id` (2026-08-20: previously compared against the super-admin's, back when super_admin was the bootstrapped root) and raises `CommandError` listing every mismatched or `NULL` account if any are found. This is not run automatically on startup — run it manually or on a schedule (e.g., a periodic cron/monitoring job) to catch data drift the startup check cannot see.

---

## Current State of the Codebase (as of 2026-06-18)

All existing models, views, cache keys, and serializers across all 6 microservices are fully compliant with these rules. The 200% Rule (two consecutive test runs) was passed with 397 tests across 5 services.

**Update (2026-08-13) — assessment-service, the 7th service, added since this snapshot:** compliant with all rules above, verified via its own dedicated audit rather than assumed — see `LIVETRACKER2_V1.md` Task 12.1 for the full evidence (a 42-test file plus 12 more covering every admin content/assignment endpoint's institution scoping and IDOR behavior, all returning 404 not 403 per Rule 4). Specific notes:
- Models (`QuestionPaper`, `BatchAssignment`): `institution_id` field + dedicated index, per Rule 1.
- Views: every list/detail/create endpoint goes through the shared `_get_institution_id(request)` helper (`assessments/views.py`) reading from `request.user.institution_id`, never request body, per Rules 2–4.
- Cache keys (`assessment_dashboard:{assignment_id}`, Task 9.1): keyed on `assignment_id` alone, not prefixed with `institution_id` like Rule 5's example — verified safe rather than assumed: `assignment_id` is a globally-unique UUID that belongs to exactly one institution by construction, and every read that populates or hits this cache key already passed its own `institution_id`-scoped `get_object_or_404` lookup first, so the shorter key can't become a cross-tenant leak or oracle. Not a violation of Rule 5's intent (prevent cross-tenant cache poisoning), just a case where the object's own ID already carries the necessary scoping.
- Rules 8–12 (credentials, force-password-change, token_version, institution_id generation/backfill): all owned by auth-service, not per-service — assessment-service has no separate account/credential surface, so these don't apply to it directly.

**Security gaps resolved on 2026-06-18:**
- Credentials moved from source code to `.env` (Gap 1)
- `force_password_change` field added to User model (Gap 2)
- `INSTITUTION_ID` startup validation added — container refuses to start without it (Gap 3)
- INSTITUTION_ID mismatch guard added — detected and blocked at startup (Gap 4)
- `token_version` field added — immediate token revocation on password change (Gap 5)
- INSTITUTION_ID health check added to auth-service `/health/` endpoint (Gap 10)
- IP address added to all admin account creation/password audit logs (Gap 11)
- Sentry SDK wired to all 6 service settings — activates when `SENTRY_DSN` is set (Gap 12)
- SUPERADMIN_PASSWORD drift detection added — container refuses to start if `.env` no longer matches the live database password (Gap 13)
- `rotate_superadmin_password` command added — atomic password change + token invalidation + audit log, replacing the no-effect `.env`-edit workflow (Gap 14)
- institution_id backfill made loud — `WARNING`-level log instead of a quiet success message (Gap 15)
- `audit_institution_consistency` command added — checks all admin/student accounts against the super-admin's institution_id, catching cross-account drift the startup check cannot see (Gap 16)

**Update (2026-08-18) — IT role added (auth-service, 4th role alongside super_admin/admin/student):** compliant with Rules 8–10, verified via a dedicated 21-test file (`services/auth-service/tests/test_it_management.py`) plus the 200% Rule (backend 135/135, frontend 234/234 across two consecutive runs). IT accounts are created/managed by super_admin only, via the same mechanism as Admin account management (`ITListCreateView`/`ITDetailView`/`ITResetDefaultPasswordView` mirror `AdminListCreateView`/`AdminDetailView`/`AdminResetDefaultPasswordView` exactly), on their own independent roster (`/api/auth/it-accounts/`) rather than folded into the Admin list. `institution_id` is stamped from the creating super_admin's own record (Rule 2), never accepted from the request body (Rule 3). `IT_DEFAULT_PASSWORD` follows Rule 8; `force_password_change=True` on creation follows Rule 9; `token_version` incremented on password reset follows Rule 10. The role currently has no functional modules beyond account creation/login — a temporary placeholder page (`/it/welcome`) is the only authenticated view — so there is nothing further for this checklist to cover yet.
*(Superseded 2026-08-20 — see the update below. `ITListCreateView`/`ITDetailView`/`ITResetDefaultPasswordView` and `/api/auth/it-accounts/` no longer exist.)*

**Update (2026-08-20) — account-provisioning root inverted: IT replaces super_admin as the bootstrapped role.** `create_default_it` (auth-service management command, run by `entrypoint.sh` on every startup) replaces `create_default_superadmin` — reads `IT_EMAIL`/`IT_PASSWORD` from `.env`, stamps `institution_id` from `INSTITUTION_ID` exactly as the old command did for super_admin (Rule 2/11 mechanics unchanged, just retargeted). `rotate_it_password` replaces `rotate_superadmin_password` for the same reason (see `IT_PASSWORD_ROTATION.md`, replacing `SUPERADMIN_PASSWORD_ROTATION.md`). `audit_institution_consistency` now compares every non-IT account against the IT account's `institution_id` (previously non-super-admin against super-admin's).

Super Admin, Admin, and Student accounts are now all created by IT through the ordinary account-management UI — same as Admin already worked (2026-08-19). New `SuperAdminListCreateView`/`SuperAdminDetailView`/`SuperAdminResetDefaultPasswordView` (`permission_classes = [IsITUser]` throughout, no read-only remnant for Super Admin — unlike Admin management, Super Admin has zero access to this resource, not even GET) replace the old `ITListCreateView`/`ITDetailView`/`ITResetDefaultPasswordView` at a new `/api/auth/super-admins/` roster. `institution_id` is stamped from the creating IT user's own record (Rule 2), never accepted from the request body (Rule 3). `SUPERADMIN_DEFAULT_PASSWORD` follows Rule 8; `force_password_change=True` on creation follows Rule 9; `token_version` incremented on password reset follows Rule 10.

Verified via a dedicated 26-test file (`services/auth-service/tests/test_superadmin_management.py`) plus the 200% Rule (backend 189/189, frontend 269/269 across two consecutive runs) and live curl through nginx covering the full lifecycle: IT logs in from `.env` credentials, creates a super_admin, the new super_admin logs in successfully and is confirmed blocked (403) on every `/api/auth/super-admins/*` endpoint including GET, and IT can edit/toggle/reset-password/delete the account it created.

**Update (2026-08-20) — Department master data added (auth-service), new `Department` model.** IT's Departments module — the canonical, backend-driven department list every dropdown/filter across the platform now reads from, replacing the frontend's old hardcoded `DEPARTMENTS` constant. Follows Rule 1 (`institution_id` field + dedicated index on `Department`), Rules 2–3 (`DepartmentListCreateView.get()` filters by `request.user.institution_id`, `super_admin` sees cross-institution same as Batch; `.post()` stamps `institution_id` from the creating IT user's own record, never accepted from the request body), Rule 4 (`DepartmentDetailView` 404s on a cross-institution `pk`, not 403). New `IsAdminOrSuperAdminOrIT` permission class added to auth-service's `core/permissions.py` (read = Admin + Super Admin + IT, write = IT-only) — mirrors user-service's existing class of the same name, the pattern already established for Batches. `code` is immutable after creation (enforced by the update serializer simply not declaring the field) since it's the free-text string `user-service Student.department` and `assessment-service BatchAssignment.departments` already match against with zero shared validation — deliberately **not** retrofitted into a cross-service FK; those two services keep their existing free-text fields unchanged, only the frontend's source-of-truth for the valid-values list moved off a hardcoded constant.

A one-off data migration (`0008_seed_departments`, dependent on the new `0007_department` schema migration) seeded the 11 codes the old frontend constant held, for every `institution_id` already present in the `users` table — idempotent, skips any `(institution_id, code)` pair that already exists.

Verified via a dedicated 39-test file (`services/auth-service/tests/test_department_management.py`, covering list/create/detail/patch/delete, code uniqueness, code immutability on PATCH, 3-way read vs IT-only write, and institution scoping) plus `services/auth-service/tests/test_department_seed_migration.py` for the seed migration's idempotency, the full backend suite (380+ tests) and frontend suite (288/288 across two consecutive runs), and live curl through nginx: create/duplicate-reject/PATCH-ignores-code/deactivate/delete, plus a 401 for unauthenticated.

**Update (2026-08-20) — `department` added to Admin/Super Admin accounts, plus bulk CSV import.** `User.department` (already Rule-1-compliant, pre-existing field) is now set on creation and editable via PATCH for both roles, through the same `AdminCreateSerializer`/`AdminUpdateExtendedSerializer` both endpoints already shared — no new institution_id surface. New bulk-import endpoints `POST /api/auth/admins/import/` and `POST /api/auth/super-admins/import/` (`AdminBulkCreateView`/`SuperAdminBulkCreateView`, both `IsITUser`-only) share a private `_bulk_create_accounts(request, role, default_password)` helper: `institution_id` is stamped once from `request.user.institution_id` (Rule 2/3, identical to the single-create views — never accepted from the request body) and applied to every account the request creates, mirroring `AdminStudentBulkCreateView`'s existing pattern in user-service. The CSV itself is email-only; department is a single value picked in the UI and applied to the whole import (not a per-row column), so there's only one institution-scoping decision per request, not one per row.

Verified via 18 new tests across `test_admin_bulk_import.py`/`test_superadmin_bulk_import.py` (institution_id stamped correctly on created accounts, IT-only access, row-level validation) plus the full backend suite and frontend suite (24 suites/299 tests across two consecutive runs), and live curl through nginx: bulk-created accounts carry the creating IT user's institution_id, non-IT roles blocked.

**Re-verified on 2026-07-10 after resource-service migration (commit `0a4e7c4`):** the `ResourceModule`/`Resource` models named below were replaced by `Company`/`Module`/`Section`/`ModuleSection`/`Upload`/`ModuleUpload` when general resource models moved from user-service into resource-service. `institution_id` scoping was carried over correctly — `Company` and `Module` carry `institution_id` directly; `Section`, `ModuleSection`, `Upload`, and `ModuleUpload` inherit scope through their FK chain. All admin/student views filter via `request.user.institution_id`, single-object fetches 404 (not 403) across institutions, and `institution_id` is never a writable serializer field. Cross-institution isolation is covered by explicit tests in `services/resource-service/tests/test_companies.py` and `test_modules.py` (e.g. `test_admin_b_cannot_see_institution_a_companies`, `test_section_idor`, `test_upload_idor`, `test_student_institution_idor`, `test_module_idor_other_institution`).

| Service | Models with institution_id | Views scoped | Migrations |
|---|---|---|---|
| auth-service | User (via JWT), Department | AdminListCreateView, SuperAdminListCreateView, DepartmentListCreateView, DepartmentDetailView, StudentPasswordResetView | 0005, 0007, 0008 |
| user-service | Student, Batch, ScrollConfig, ScrollUpdate | All student + scroll views | 0008 |
| practice-service | PracticeModule, PracticeSection, PracticeQuestion, PracticeQuestionProgress, PracticeQuestionAttempt | All admin + student practice views | 0003 |
| analytics-service | PracticeEvent, ResourceViewEvent, DailyEngagementSnapshot, InstitutionSnapshot | StudentAnalyticsView, InternalEventView | — |
| notification-service | Notification | NotificationListView, MarkReadView | — |
| resource-service | Company, Module (institution_id direct); Section, ModuleSection, Upload, ModuleUpload (scoped via FK chain to Company/Module) | Admin: CompanyDetailView, SectionListCreateView, UploadDetailView, AdminModuleDetailView, AdminModuleSectionDetailView, AdminModuleUploadDetailView, etc. Student: StudentCompanyListView, StudentModuleHubView, StudentModuleDetailView, etc. | 0001–0005 |
| assessment-service | QuestionPaper, BatchAssignment (institution_id direct); QuestionSet, Question, QuestionOption, StudentSetAllocation, AssessmentSession, AssessmentResponse, ResultSummary, ActivityLog (scoped via FK chain to QuestionPaper/BatchAssignment) | Admin: AdminPaperListCreateView, AdminPaperDetailView, AdminAssignmentListCreateView, AdminAssignmentDetailView, AdminAssignmentResultsView, AdminAssignmentAnalyticsView, AdminAssignmentDashboardView, etc. Student: StudentAssignmentListView, StudentAssignmentStartSessionView, StudentResultsView, etc. — all via the shared `_get_institution_id(request)` helper. Cross-institution isolation verified in `services/assessment-service/tests/test_admin_papers.py` and `test_assignments.py` (42+12 tests, Task 12.1). | 0001–0010 |

---

## Key Constants

| Item | Value |
|---|---|
| ANITS institution_id | `1470350a-1765-41d1-92b9-bf7b040ddaf9` |
| Super admin email | `spark@gmail.com` |
| JWT claim name | `institution_id` |
| How to read in a view | `getattr(request.user, "institution_id", None)` |
