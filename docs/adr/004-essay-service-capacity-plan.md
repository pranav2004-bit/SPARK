# ADR 004 — Essay Service: Capacity Plan for 2,000 Concurrent Students

**Status:** Accepted (provisional — see revisit trigger)
**Date:** 2026-09-19
**Task:** [LIVETRACKER3_V1.md](../../LIVETRACKER3_V1.md) Task 0.4, feeding Tasks 1.2, 1.3, 16.2, 18.1
**Deciders:** essay-service design (Phase 0)

## Context

The explicit target for this service is 2,000 concurrent students. This platform has already learned, the expensive way, what happens when a capacity number is asserted without real arithmetic behind it: `infra/pgbouncer/pgbouncer.ini`'s `max_client_conn=600` was sized as "~100 per service" for 6 services, then left unchanged when a 7th (`assessment-service`) was added — stale intent, never re-derived, discovered only by inspection rather than by a load test catching it first. This ADR exists so `essay-service` does not repeat that pattern: every number below is a real calculation from a stated assumption, not a copied default, and every one is explicitly provisional pending Task 18.1's actual load test.

## 1. PgBouncer / Database Connections

**Assumption:** at 2,000 concurrent students, the hottest write path is autosave (one write per student roughly every 15–30 seconds during active writing, per Task 4.2's debounced-autosave design) plus the one-time submit. This is materially lighter per-student than `assessment-service`'s per-question autosave across a multi-question exam, because this service has exactly one question per assignment.

**Decision:** `essay_db` gets its own PgBouncer pool entry at `default_pool_size = 10` (the same per-service default every existing pool on this platform uses — `assessment_db`'s own ADR 001 addendum explicitly declined to special-case this without load-test evidence, and the same reasoning applies here on day one). **Correction from this ADR's own self-audit:** the first draft mislabeled this as "the 9th pool" — 6 original services + `assessment_db` (ADR 001's addendum) = 7 pools today, so `essay_db` is the **8th pool**, matching `essay-service` as the platform's 8th microservice. `essay-worker`/`essay-beat` are additional *clients* of that same one pool (like `assessment-worker`/`assessment-beat` already are for `assessment_db`), not separate pools of their own. This adds 10 real server connections, bringing the platform's real-connection total to 80 (70 existing across the 7 current pools, per ADR 001's addendum, + 10 new).

**`max_client_conn` (currently 600, platform-wide, shared across all services' client-facing slots):** left unchanged for the same reason ADR 001's addendum gave when the 7th service was added — the "N per service" framing was already loose intent, not a hard per-service reservation, since PgBouncer enforces one global ceiling here, not a per-database one. **This is explicitly not re-validated by this ADR** — it is exactly the kind of number this project has already been burned by treating as validated without a real load test. Task 16.2 must re-check this specific value against the platform's actual combined load (7 existing services + essay-service) before Task 18.1's load test, not assume ADR 001's math still holds unchanged now that an 8th service shares the same ceiling.

**Task 16.2 re-check (2026-09-23, against the actual built system, not a projection):** confirmed live that all 8 services — not just essay-service — run the identical `--workers ${UVICORN_WORKERS:-3}` gunicorn/UvicornWorker entrypoint (grepped every `services/*/entrypoint.sh`), so the platform runs a real, current total of **8 × 3 = 24 application worker processes**. Also found and fixed, during this same re-check, a genuinely stale comment in `infra/pgbouncer/pgbouncer.ini` itself — the `default_pool_size` comment still said "7 dbs × 10 = 70 max real connections" despite `essay_db`'s pool already existing in the same file, the identical class of staleness this ADR's own Context section describes for `max_client_conn`. Corrected to the real 8 × 10 = 80. On `max_client_conn=600` itself: PgBouncer's transaction-pooling mode means a client slot is held only for one DB transaction's duration, not a worker process's whole lifetime, so 24 processes is a floor, not the real peak-concurrency number — the actual peak (simultaneous in-flight DB-touching requests across Django's ASGI sync-thread pool, spread across all 8 services) cannot be precisely derived without a real load test. What this re-check *can* state honestly: 600 slots spread evenly across 8 services is 75 simultaneous in-flight DB transactions per service, well above the 24-process floor, so there is no evidence the ceiling is already silently exceeded at rest — but this remains provisional, exactly like every other number in this document, pending Task 18.1's real load test.

## 2. Celery Worker Sizing

**Assumption:** the LLM call itself dominates evaluation-task latency (seconds, not milliseconds — an external API round trip), not database or CPU work, so worker *concurrency* (how many evaluation tasks can be in-flight waiting on an LLM response at once) matters more than worker *count* in the traditional CPU-bound sense.

**Decision:** provision `essay-worker` with a concurrency high enough to keep the LLM call pipeline saturated against Section 3's real key-rotation throughput, not higher — there is no benefit to more in-flight tasks than the quota tracker will actually let through per minute, only wasted memory holding blocked/waiting tasks. **Initial concurrency: 20** — re-checked against Section 3's corrected math (e.g. at 20 rotated keys, 40 effective RPM ≈ 0.67 requests/second; by Little's Law, at a few seconds of LLM round-trip latency per call, the *actual* average in-flight count is roughly 2–3, not 20) — this remains comfortably above what the quota tracker will actually admit per minute at any of Section 3's rotated-key scenarios, so the queue itself is never the bottleneck, the quota tracker is (correctly — it's the layer that directly protects ADR 003 Decision 9's cost ceiling). The headroom above the calculated average is deliberate burst capacity, not a sign the number needs shrinking. Revisit with Task 18.1's real measured numbers, not this estimate, once available.

**Task 16.2 re-check:** confirmed live in `infra/docker-compose.prod.yml` — `essay-worker`'s entrypoint still reads `--concurrency=20` exactly as decided above; no drift found between this ADR's decision and the actual built system.

## 3. LLM Provider Throughput — the Number That Actually Gates 2,000 Concurrent

This is the binding constraint, not the database or Celery layer. CLAP's own verified default per-key limit is `rpm_limit=3`, and the `QuotaTracker` constructor applies the 90% safety margin as `math.floor(rpm_limit * safety_margin)` — **not** the raw product. **Arithmetic correction from this ADR's own self-audit:** the first draft used `3 × 0.90 = 2.7` directly as "effective RPM," but the actual code floors that to a hard integer: `floor(2.7) = 2`. Every number in the table below is recomputed against the real floored value (2 effective RPM per key, not 2.7) — the earlier table understated drain times by roughly 35%.

**At those limits, the honest, code-accurate math:**

| Rotated API keys | Aggregate effective RPM | Time to drain 2,000 evaluations |
|---|---|---|
| 1 | 2 | 1,000 minutes (~16.7 hours) |
| 10 | 20 | 100 minutes (~1.7 hours) |
| 20 | 40 | 50 minutes |
| 50 | 100 | 20 minutes |

**Decision: this platform does not yet have an OpenAI account tier established, and this ADR does not assume one.** Per ADR 003 Decision 1's own framing, the actual per-key RPM ceiling for whatever tier this project provisions must be substituted into the table above before this number is treated as final — CLAP's `rpm_limit=3` reflects CLAP's own (likely free- or Tier-1-shaped) account, not a property of the OpenAI API in general; a paid, higher-tier account has meaningfully higher per-key RPM. **Action required before Phase 5 (Submission & LLM Evaluation Pipeline) is considered ready to start** — not a blocker for Phase 1's scaffolding/`essay_db`/nginx-routing work, which has no dependency on this number: confirm the actual provisioned tier's real RPM/TPM limits, substitute them here, and pick an explicit key-count target from the corrected table — do not proceed with CLAP's numbers as if they were this platform's own without checking.

**Given that open item, the explicit, honest position of this ADR:** 2,000 truly *simultaneous* LLM evaluation completions is not achievable with a small number of Tier-1-shaped keys — but 2,000 students *taking the assessment concurrently* does not require 2,000 *simultaneous LLM calls*, because evaluation is asynchronous and students do not all submit in the same second (Non-Negotiable Constraint §5 exists exactly so this distinction holds — the student experience is never blocked on evaluation throughput). The real requirement to size against is **evaluation queue drain time relative to when results are actually needed** (e.g., "results available within N hours of the assignment closing" is a realistic, statable SLA; "results available within seconds of each submission" is not, and was never the workflow spec — the workflow you described is submit → queued → LLM → score+feedback, not a synchronous round trip).

## 4. Nginx Rate Zones

Reuse the platform's existing tiered pattern (`assessment-service`'s `token_refresh_zone`-style reasoning: a generous, purpose-fitted limit per endpoint class, not one blanket number):

- **Autosave endpoint:** sized like `assessment-service`'s per-student answer-submit throttle (120/min per student, per `LIVETRACKER2_V1.md` Task 11.2) — a single-question autosave is lower-frequency than multi-question exam autosave, so this ceiling is generous headroom, not a tight fit.
- **Submit endpoint: 10 requests/minute per student** (gap found and closed during this ADR's final audit pass — the first draft said "a tight limit is appropriate" without ever giving one, which this document's own stated standard, real numbers not placeholders, requires). Reasoning: a genuine submit happens once per assignment; 10/min comfortably absorbs a handful of legitimate client retries on a flaky network (matching the reasoning, though not the exact value, behind `assessment-service`'s `auth_zone` login-endpoint sizing) without needing anything close to autosave's 120/min headroom.
- **Admin bulk-action endpoints** (retrigger, bulk-resend, bulk-DLQ-retry): their own dedicated zone, mirroring `assessment-service`'s dedicated 10r/m export-endpoint zone — bulk admin actions are inherently infrequent and expensive per call (see ADR 003 Decision 6 and the tracker's dry-run-by-default requirement), so a tight nginx-level ceiling is a correct second layer, not redundant with the application-level dry-run/cap safeguards already required.

**Task 16.2 re-check:** confirmed live in `gateway/nginx.conf` — `essay_autosave_zone` (120r/m), `essay_submit_zone` (10r/m), and `essay_admin_bulk_zone` (10r/m) all exist exactly as decided above (implemented in Task 15.2), with matching `limit_req` directives on their respective `location` blocks. No discrepancy between this ADR's decision and the actual built system.

## 5. Submission-Creation Rate Limiting (Application Layer, Redis-Backed)

Per ADR 003 Decision 8 and the tracker's Task 5.1 finding: reuse CLAP's two-tier, **fail-closed** design directly —

- **Per-student:** a generous per-hour ceiling (CLAP's own default, 500/hour, is already generous relative to a single-question assessment's realistic autosave+submit volume; adopt as-is rather than re-deriving a smaller number that risks legitimate false-positives with no real benefit).
- **Per-institution/batch:** CLAP's own default (5,000/hour) — re-derive only if a real institution's expected concurrent batch size would exceed it, which is unlikely at the scoped batch sizes ADR 002 Decision 4 already assumes for the (separate) plagiarism-check scoping.
- **Fails closed, not open**, on a Redis outage — restated here because it is the one deliberate exception to "prefer fail-open for resilience" elsewhere on this platform, and it is easy to accidentally "fix" into fail-open by someone applying the platform's general resilience convention without knowing this one path is intentionally different.

## Consequences

- **Positive:** every number in this ADR traces to either a real existing platform value (PgBouncer pool sizing, nginx zone philosophy) or an explicit, correctable placeholder (the LLM tier assumption) rather than an invented target dressed up as settled.
- **Negative / accepted tradeoff:** this ADR cannot state a final "2,000 concurrent, confirmed" number today, because the one binding constraint (real LLM provider tier) is an external account-provisioning decision outside this codebase, not a design choice. That is stated plainly here rather than papered over with an optimistic assumption.
- **Revisit trigger (two, not one):** (1) the moment a real OpenAI account tier is provisioned, substitute its real RPM/TPM limits into Section 3's table and pick a concrete key-count target — this is a blocking prerequisite for **Phase 5** (evaluation pipeline), not for Phase 1's scaffolding, and not a "later" item once Phase 5 is reached. (2) Task 18.1's real load test either confirms or corrects every other number in this document; update it with real measurements, not estimates, once available.
