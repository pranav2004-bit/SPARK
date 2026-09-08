# Version 2 Gaps

Gaps deliberately deferred from Version 1. Implement before launching multi-college single-deployment or Version 2 services (assessments, contests).

---

## Gap 1 — No Institution Model

**Current:** institution_id is a raw UUID in `.env`. No college name, contact, or metadata stored anywhere in the DB.

**When it breaks:** Version 2 requires one deployment to serve multiple colleges. The platform needs to list, create, and manage colleges programmatically.

**What to build:** An `Institution` model in auth-service with `id`, `name`, `domain`, `is_active`, `created_at`. Super admin becomes platform-level (no institution_id). A "Create College" API generates a new UUID and seeds a college-specific super admin.

---

## Gap 2 — Same IT Email Across Deployments

**Current:** `IT_EMAIL` defaults to `it@spark.test` in every deployment (2026-08-20: IT is now the bootstrapped root account, replacing super_admin in that role — see `create_default_it`). Deployers must manually change it per college.

**When it breaks:** Single deployment, multiple colleges — email uniqueness constraint breaks.

**What to build:** When Gap 1 (Institution model) is implemented, the bootstrapped IT account is created per institution with a unique email — no longer a manual deployment concern.

---

## Gap 3 — Shared Core Files Copy-Pasted Across Services

**Current:** `authentication.py`, `permissions.py`, `responses.py`, `exceptions.py`, `pagination.py` are identical files duplicated in all 7 services (assessment-service added Phase 1 of `LIVETRACKER2_V1.md` — confirmed it copies the same 5 files, not an exception to this gap). A bug fix must be applied manually to each.

**When it breaks:** Version 2 adds contest-service, the 8th. 8 services with identical files becomes unmanageable — already at 7 today.

**What to build:** Extract into a `spark-common` internal Python package. Install via pip in all services. One change propagates everywhere.

---

---

## Gap 4 — token_version Stateless Limitation

**Current:** `token_version` is validated only in auth-service (`TokenVersionJWTAuthentication`). The other 5 services (user, resource, practice, notification, analytics) validate JWT signatures but do NOT check `token_version` against the DB — they are stateless. A stale token (issued before a password change) will be rejected by auth-service endpoints but **accepted** by other services until the token expires naturally.

**When it breaks:** A user whose account is compromised can still access non-auth endpoints for up to the JWT TTL window even after a forced password change.

**What to build:** Implement a Redis-backed token blocklist in the shared auth backend. On password change, push `(user_id, token_version - 1)` to a Redis set with TTL = JWT access token lifetime. All services check this blocklist before authorising a request. Alternatively, reduce JWT access TTL from 30 min to 5 min to shrink the exposure window.

---

## Notes

- None of these gaps affect Version 1 production safety or security.
- Gap 2 is automatically resolved when Gap 1 is implemented.
- Implement Gap 3 before adding new Version 2 services — not after.
- Gap 4 severity: Low for V1 (single service most state changes go through auth-service); High for V2 multi-service usage.
