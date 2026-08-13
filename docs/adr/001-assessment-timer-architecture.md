# ADR 001 — Assessment Timer & Concurrency Architecture

**Status:** Accepted
**Date:** 2026-08-11
**Task:** [LIVETRACKER2_V1.md](../../LIVETRACKER2_V1.md) Task 0.1
**Deciders:** assessment-service design (Phase 0)

## Context

`assessment-service` runs timed exams for hundreds to thousands of concurrently-connected students. Every exam has two timing layers, per the product spec:

1. **Global timer** — admin-configured `global_start_time` / `global_expire_time` on a `BatchAssignment`, manually started by an admin action (not a schedule alone).
2. **Exam timer** — a per-student `exam_duration_minutes` window that starts the moment that specific student begins their session.

The effective deadline for any one student is `min(session_start + exam_duration, global_expire_time)`.

The threat register (`LIVETRACKER2_V1.md`) flags this as the single highest-risk design surface:

- **AT1** (CRITICAL) — timer spoofing: a client tampering with its local clock or intercepting requests to gain extra time.
- **AT2** (CRITICAL) — thundering herd: thousands of students hitting session-start/submit within the same narrow window.
- **AT5** (HIGH) — a race between the auto-submit sweep and a concurrent manual submit.
- **AT13** (MEDIUM) — the shared single Postgres instance being starved by this service's write spikes.

This ADR settles how timing is enforced before any model or endpoint is built, since every later phase (session model, submit endpoints, sweep job, admin controls, load testing) depends on this decision.

## Decision

**The database is the source of truth for timestamps — not an active running process.** No `pg_cron` busy-loop, no per-session background thread, no client-trusted clock.

1. **Timestamps are plain columns, computed once.**
   - `BatchAssignment.global_start_time` / `global_expire_time` — set by the admin, mutated only by explicit admin actions (`start/`, `close/`, `extend/` — see Task 3.2).
   - `AssessmentSession.ends_at` — computed **exactly once**, at session creation, as `min(now() + exam_duration_minutes, global_expire_time)`. Never recomputed on resume. The one narrow exception is the admin `.../sessions/<id>/extend/` action, which directly patches this column — a targeted, audited override, not a silent recomputation from `global_expire_time` (which has no effect on an already-started session; see Task 3.2/5.1).

2. **Every mutating student request is revalidated server-side, on every call.** The answer-autosave and submit endpoints check `now() < session.ends_at AND session.status == 'IN_PROGRESS' AND assignment.status != 'CLOSED'` before accepting any write. The client-side countdown is cosmetic only — it renders from a server-time-sync endpoint (`GET /api/assessments/student/server-time/`) so client clock skew, tampering, or a paused tab never affects what the server will actually accept. Any client-supplied timestamp field is ignored outright if one is ever sent (defense in depth against AT1).

3. **A Celery beat sweep enforces expiry independent of any client request.** Every 15–30 seconds, a scheduled task:
   - Transitions `BatchAssignment` rows where `now() >= global_expire_time AND status = 'LIVE'` → `CLOSED`.
   - Transitions `AssessmentSession` rows where `now() >= ends_at AND status = 'IN_PROGRESS'` → `AUTO_SUBMITTED`, scoring each from its frozen `AssessmentResponse` set.

   Both use conditional `UPDATE ... WHERE status = <current>` — the same code path an admin's manual `close/`/`submit/` action uses. Whichever write lands second is a no-op, because the row no longer matches the `WHERE` clause. This is what makes the sweep race-safe against a concurrent manual submit (closes AT5) without locks, and it's why this task is placed at the front of Phase 4 — it's the reusable primitive that Task 3.2's `close/` cascade and Task 5.2's manual submit both build on, rather than three independent implementations of "score a session."

4. **Redis holds ephemeral, non-authoritative state only** — fast countdown display, live dashboard rollups (Task 9.1). It is never on the write path for scoring or submission. If Redis is unavailable, the system degrades to slower direct computation (Task 13.1), never to incorrect scoring.

5. **No WebSocket-per-student for V1.** The countdown is a lightweight poll (every 20–30 seconds) against the server-time endpoint. At thousands of concurrent students, thousands of long-lived sockets is an operational cost (connection management, horizontal-scaling complexity, a new failure mode) this design doesn't need yet. Revisit only if Phase 14 load testing shows polling — not scoring, not the sweep — is the actual bottleneck.

## Alternatives Considered

| Alternative | Why rejected |
|---|---|
| **Active DB timer** (`pg_cron` job per session, or a long-running background thread per exam) | Doesn't scale to thousands of concurrent sessions — one process/job per session is the wrong shape. Also duplicates what a single, shared Celery beat sweep already does with a simple indexed query, adding an entirely separate scheduling mechanism (`pg_cron`) to a stack that has no other Postgres-side scheduled jobs — inconsistent with how `notification-service`/`analytics-service` already solve this exact class of problem. |
| **Pure client-side timer** (JavaScript countdown is the only enforcement) | Trivially defeated — pause the tab, edit `Date.now()`, intercept the request, or just stop sending it. This is AT1 by definition; a client-only timer isn't a mitigation, it's the vulnerability. |
| **WebSocket push per student** (server pushes "time's up" to each connected client) | Solves a UX polish problem (near-instant countdown/lockout) at real infrastructure cost (thousands of long-lived connections, reconnection/backpressure handling, a new class of production incident) that isn't justified by the spec. The server-authoritative revalidation on every request already makes any residual lag in the client's countdown display harmless — the server rejects the write regardless of what the UI showed. Deferred, not ruled out permanently; see decision point 5. |

## Session & Assignment State Machines

**`AssessmentSession.status`:**

```
NOT_STARTED → IN_PROGRESS → SUBMITTED
                           → AUTO_SUBMITTED   (sweep, or admin close/ cascade)
            → EXPIRED_UNSTARTED               (global_expire_time passed before the student ever called start-session)
```

- `NOT_STARTED` is conceptual, not a stored initial row — a session row is only created by `start-session` (Task 5.1), at which point it's immediately `IN_PROGRESS`. There is no student-facing action that leaves a row sitting in `NOT_STARTED`.
- `IN_PROGRESS → SUBMITTED` — manual student submit (Task 5.2), conditional `UPDATE ... WHERE status='IN_PROGRESS'`.
- `IN_PROGRESS → AUTO_SUBMITTED` — either the beat sweep (deadline passed) or an admin `close/` cascade (Task 3.2/4.1); both use the same conditional update and same scoring code path.
- `EXPIRED_UNSTARTED` — a student who was allocated (`StudentSetAllocation` exists) but never called `start-session` before `global_expire_time`. No row transitions into this state from `NOT_STARTED`/`IN_PROGRESS`; it's the terminal state assigned to a `ResultSummary` for students who simply never showed up, so Results/Analytics (Phase 7/8) can distinguish "didn't attempt" from "attempted and scored."
- Every transition above is gated by a `now()` comparison against `ends_at`/`global_expire_time`, or is an explicit authenticated admin action — no transition is reachable purely from client-supplied data.

**`BatchAssignment.status`:**

```
SCHEDULED → LIVE → CLOSED
```

- `SCHEDULED → LIVE` — admin's manual `start/` action only (Task 3.2). Never automatic, even after `global_start_time` passes — the spec is explicit that student access is gated on a manual admin action, not a schedule alone.
- `LIVE → CLOSED` — either the sweep (`now() >= global_expire_time`) or the admin's manual `close/` action, which additionally cascades to terminate any `IN_PROGRESS` sessions (Task 3.2/4.1).
- `CLOSED` is terminal — no reopen action exists. An admin needing another attempt window creates a new `BatchAssignment` (Task 3.2's documented no-retake policy).

## Capacity Planning

The beat sweep's two queries (`BatchAssignment` by `(status, global_expire_time)`, `AssessmentSession` by `(status, ends_at)`) must stay sub-second even at tens of thousands of concurrent sessions, since the sweep runs every 15–30s regardless of load. Both require a covering index — confirmed as an explicit index-audit item in Task 11.1, using the same `(status, ends_at)` composite this ADR assumes. Not created here (no models exist yet in Phase 0) — this is the design constraint Task 4.1's migration and Task 11.1's audit must satisfy.

## Addendum (Task 1.2) — PgBouncer Capacity Review

Added when `assessment_db` was provisioned as PgBouncer's 7th pool (`infra/pgbouncer/pgbouncer.ini`).

**Before (6 services):** `max_client_conn = 600` (intended as ~100 client slots/service, though this is a single global ceiling in PgBouncer, not an enforced per-database cap), `default_pool_size = 10` × 6 databases = 60 real Postgres server connections at any time.

**After (7 services, +assessment-worker +assessment-beat):** `assessment_db` adds a 7th pool at the same `default_pool_size = 10` → 70 real server connections. `max_client_conn` was **left unchanged at 600** rather than bumped to 700 — the "100/service" comment was already loose intent, not a hard reservation, and every service already shares the same global client-slot pool today (a burst on one service can already consume another's headroom in the current 6-service setup; adding a 7th doesn't change that pre-existing property). Whether 600 needs to rise is exactly what Task 11.1's index/connection-pool audit and Task 14.1's load test settle with real numbers — this addendum documents the *starting* math, not a load-tested conclusion. Do not treat 600 (or 70) as validated capacity for exam-day thundering-herd traffic (AT2/AT13) until Task 14.1 confirms it.

`assessment-worker` and `assessment-beat` are additional PgBouncer clients beyond the web process (Django's ORM connects through PgBouncer for the beat sweep's queries and the worker's task execution) — both run with `CONN_MAX_AGE=0` like every other service in this stack, so they hold a connection only for the duration of a single query/transaction under `pool_mode = transaction`, not persistently.

**Decision (not implemented, evaluation only):** `assessment_db` stays on the shared single Postgres instance for V1, alongside the other 6 databases — matching every existing service's setup, and matching this ADR's broader "don't build infrastructure the current scale doesn't need yet" stance (see the WebSocket decision above). This carries forward the platform-wide risk already flagged as **T12** in `LIVETRACKER_V1.md` and **AT13** in `LIVETRACKER2_V1.md`: a mass exam-start write spike could starve `auth-service`/`user-service` login traffic on the same instance. The trigger to revisit — moving `assessment_db` to its own dedicated Postgres instance — is empirical, not scheduled: if Task 14.1's load test shows the shared instance can't absorb a realistic exam-day spike without degrading the other 6 services' latency, that is the signal to split it out, not a guess made here in Phase 1 before any real traffic pattern exists.

## Consequences

- **Positive:** No new infrastructure component (reuses Redis/Celery already provisioned for `notification-service`/`analytics-service`). Timer correctness reduces to "is `now()` on the server correct," not "did every client's clock and network stay honest." The sweep and every manual state transition share one race-safe update pattern, so there is exactly one place that implements "safely transition a session," not three.
- **Negative / accepted tradeoff:** Up to ~30 seconds of lag between a session's true deadline and the sweep catching it. This is bounded and monitored (Task 13.2's "sweep lag" SLA metric), and harmless from a security standpoint — per-request revalidation (decision point 2) means no write succeeds past the deadline even during that lag window; the lag only delays the session's *status* flipping, not enforcement.
- **Revisit trigger:** If Phase 14 load testing shows the 20–30s polling pattern itself (not scoring, not the sweep) is the bottleneck at real scale, reconsider WebSocket/SSE for the countdown display only — the enforcement model in this ADR does not change either way.
