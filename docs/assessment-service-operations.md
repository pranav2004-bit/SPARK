# assessment-service — Operations, SLA & Monitoring

**Task:** [LIVETRACKER2_V1.md](../LIVETRACKER2_V1.md) Task 13.2
**Related:** [ADR 001 — Timer Architecture](adr/001-assessment-timer-architecture.md), [assessment-service-api.md](assessment-service-api.md)

No dedicated metrics/APM stack exists for this platform yet — this document is the "documented queries" half of Task 13.2's own explicit "operational dashboard (or documented queries)" allowance, not a placeholder for a dashboard that doesn't exist. Every query below was run against the real running dev stack before being written down here, not authored from assumption — see LIVETRACKER2_V1.md's Task 13.2 verification notes for the exact commands and real output that confirmed each one.

Task 13.3's exam-day runbook links back to this document's specific sections for the alerting thresholds it acts on — do not restate the numbers there; reference them here so there is exactly one place to update if a threshold ever changes.

---

## SLA Definitions

| Metric | Target | Alert Threshold | Why this number |
|---|---|---|---|
| Submit-endpoint (`POST .../submit/`) p99 latency | < 2s | Sustained p99 > 5s over a 5-minute window | A single manual submit's `finalize_sessions()` call touches exactly one session — near-instant in isolation (confirmed: real dev-stack samples were 46–151ms). 2s gives generous headroom for DB contention during a thundering-herd submit spike (AT2); 5s sustained is a genuine problem, not normal jitter. |
| Sweep lag (time between a session's `ends_at` and its actual auto-submit) | Average < 30s | Average > 120s sustained, **or** any single session's lag > 5 minutes | The sweep runs every 20s (ADR 001's 15–30s window), so ~30s average lag is just "one sweep cycle," expected and fine. Task 13.1's DLQ retry backoff (10s/20s/30s) means even a transient failure should self-resolve within ~90s — 120s sustained means something is structurally broken, not just cadence jitter. A single session stuck past 5 minutes is worth paging on even if the *average* looks fine, since it means one specific student is stuck, not just a slow cycle. |
| PgBouncer pool utilization (`assessment_db` pool) | `cl_waiting == 0` | Any sustained `cl_waiting > 0`, or `maxwait > 5` (seconds) | A client actually queueing for a PgBouncer connection slot is the concrete, measurable precursor to AT2/AT13 (thundering-herd DB starvation) — this is the number that would move *before* requests start timing out, not after. |

These are starting targets, not load-tested conclusions — Task 14.1's real load-test numbers are the authority on whether they need revising (matching the same "don't guess ahead of real data" discipline Task 11.1 applied to PgBouncer's `max_client_conn`). Revisit after Phase 14.

**Update, post-Task 14.1:** the submit p99 target above was tested at real concurrent load (200/400/600 students) and was **not met** on this dev machine's Docker Desktop VM (2 CPU cores shared across ~19 containers) — see [assessment-service-load-test-results.md](assessment-service-load-test-results.md) for the full numbers and root-cause analysis. PgBouncer pool exhaustion and DB lock contention were both individually ruled out with live evidence; the bottleneck is this VM's CPU ceiling, not application code. Treat the target above as **production-scoped and not yet dev-environment-verified** — re-validate on hardware with real CPU headroom before relying on it operationally.

---

## Operational Queries

### 1. Sessions currently `IN_PROGRESS`

A live gauge of exam-taking load right now — useful context alongside the other metrics, not itself an SLA target (there's no "correct" number, it's whatever's actually happening).

```bash
docker exec infra-assessment-service-1 python manage.py shell -c "
from assessments.models import AssessmentSession, SESSION_STATUS_IN_PROGRESS
print(AssessmentSession.objects.filter(status=SESSION_STATUS_IN_PROGRESS).count())
"
```

### 2. Sweep lag

```bash
docker exec infra-assessment-service-1 python manage.py shell -c "
from django.db.models import F, ExpressionWrapper, DurationField, Avg, Max
from assessments.models import ResultSummary, SESSION_STATUS_AUTO_SUBMITTED

qs = ResultSummary.objects.filter(status=SESSION_STATUS_AUTO_SUBMITTED).annotate(
    lag=ExpressionWrapper(F('ended_at') - F('session__ends_at'), output_field=DurationField())
)
agg = qs.aggregate(avg_lag=Avg('lag'), max_lag=Max('lag'))
print('count:', qs.count(), 'avg_lag:', agg['avg_lag'], 'max_lag:', agg['max_lag'])
for r in qs.order_by('-lag')[:5]:
    print(' worst:', r.session_id, 'lag=', r.lag)
"
```

To scope this to a specific exam window (recommended during/after a real live exam, rather than all-time history), add `.filter(ended_at__gte=<exam_start_time>)` to the queryset.

### 3. PgBouncer pool utilization

```bash
MSYS_NO_PATHCONV=1 docker exec -e PGPASSWORD=<postgres_password> infra-pgbouncer-1 \
  psql -h 127.0.0.1 -p 5432 -U postgres pgbouncer -c "SHOW POOLS;"
```

Look at the `assessment_db` row specifically. `cl_active`/`cl_waiting` are client-side (this service's own connections to PgBouncer); `sv_active`/`sv_idle` are PgBouncer's own connections to real Postgres (bounded by `default_pool_size=10`, see `infra/pgbouncer/pgbouncer.ini` and ADR 001's Task 1.2 addendum). `cl_waiting > 0` means clients are queueing — the concrete signal in the SLA table above.

### 4. Submit-endpoint status breakdown & latency

Read from nginx's own JSON access log (`gateway/nginx.conf`/`nginx.dev.conf`'s `log_format json_access` — already includes `request_time` and `status` per line, no extra instrumentation needed):

```bash
# Status code breakdown for the submit endpoint
docker logs infra-nginx-1 --since 1h 2>&1 \
  | grep -o '"uri":"[^"]*submit/"[^}]*"status":[0-9]*' \
  | grep -o '"status":[0-9]*' | sort | uniq -c

# Slowest submit calls in the window (for a rough p99 read — sort numerically, take the tail)
docker logs infra-nginx-1 --since 1h 2>&1 \
  | grep '/submit/"' | grep -o '"request_time":[0-9.]*' \
  | sort -t: -k2 -n | tail -20
```

For a real p99 (not "top 20, eyeball it"), pipe the full `request_time` list through a proper percentile calculation — the commands above are what's actually practical to run by hand during an incident, per this document's own "practical, not automated" scope.

### Correlating a specific student's request end to end

Every request carries one correlation ID (`core/logging_utils.py`, Task 13.2) from nginx's own `$request_id` through this service's structured JSON logs and back to the client as the `X-Request-ID` response header — ask the affected student/admin for that header value (or find it in nginx's access log by timestamp/URI) and grep every layer for it:

```bash
docker logs infra-nginx-1 2>&1 | grep "<request_id>"
docker logs infra-assessment-service-1 2>&1 | grep "<request_id>"
```

Celery task log lines use the task's own Celery `task_id` as this same field (there's no HTTP request to inherit an ID from for a periodic sweep run) — find it via `celery.app.trace`'s own success/failure log lines, or via a `FailedJob.task_id` row for a permanently-failed run (Task 13.1's DLQ).

---

## Known Incident — Stale Inter-Service Connections (2026-08-17)

**Symptom:** `GET /api/assessments/admin/papers/` (and, transiently, other admin endpoints across the platform) failed with "Failed to load..." toasts in the UI, twice in a row, with no corresponding completion line in this service's own access log for the failing requests — the request was dropped, not just slow.

**Root cause, confirmed with real evidence, not guessed:**
- `docker ps` showed `auth-service` (and several other services) `Up ~40h (unhealthy)` — containers had sat idle a long time without traffic.
- `docker logs infra-assessment-service-1` showed `core.auth_service_client` hitting its full 5s timeout calling auth-service's `/api/auth/admin/users/lookup/` (the "Created by <name>" enrichment on the papers list, added earlier the same day) — `Auth service read timeout — Not retrying.`
- `docker logs infra-auth-service-1` had **no corresponding log line at all** for that specific request — it never arrived, while a manual `docker exec` test to the same endpoint immediately after did arrive and got a real response. This is consistent with a stale connection/network-state issue after long idle, not an application bug in the endpoint itself (confirmed separately: `docker stats` showed auth-service at <2% CPU/memory the whole time — not a resource-exhaustion cause).
- `docker restart infra-auth-service-1 infra-assessment-service-1` alone fixed it — the same manual lookup call that had timed out at 5s dropped to ~0.15s immediately after.

**Fix (this service and user-service, dev only — see below for prod):**
1. `core/auth_service_client.py`'s per-attempt timeout: 5s → 2s, retries 3 → 2 (cosmetic "Created by" lookup — cheap to fail fast on, never worth blocking the whole papers list for).
2. `core/user_service_client.py`'s per-attempt timeout: 5s → 3s, retries 3 → 2 (roster-fetch, a hard blocker for assignment creation — kept slightly more patient than the cosmetic lookup above).
3. `user-service/core/auth_client.py`'s same knobs: 5s → 3s, retries 3 → 2 (student-account sync calls to auth-service).
4. An `autoheal` sidecar was added to `infra/docker-compose.dev.yml`, then **removed the same day** — see "Autoheal — tried and reverted" below.

**Production is deliberately unaffected by the timeout tightening** — `infra/docker-compose.prod.yml` pins explicit `AUTH_SERVICE_TIMEOUT`/`AUTH_SERVICE_RETRIES` (and, on assessment-service, `USER_SERVICE_TIMEOUT`/`USER_SERVICE_RETRIES`) environment overrides back to the original 5s/3-retry values on both `user-service` and `assessment-service`, since real production network hops have legitimate variance the same-host dev Docker network doesn't — only the dev compose file (and any environment that doesn't override these vars) inherits the tighter defaults.

**Autoheal — tried and reverted (2026-08-17, same day):** an `autoheal` sidecar (`willfarrell/autoheal`, watches every container's Docker health status, restarts anything reported `unhealthy`) was added right after the incident above, then removed a few hours later once real evidence showed it wasn't working:
- Its own log showed **12 separate "unhealthy" events in under an hour** across nginx, redis, both assessment-service and user-service, auth-service, analytics-service, resource-service, and practice-service — this dev host's containers flip unhealthy far more often than the original ~40h-stale incident suggested, most likely from ordinary CPU contention on this VM under concurrent load (already documented as a real bottleneck — see [assessment-service-load-test-results.md](assessment-service-load-test-results.md)), not each one being a fresh version of the original staleness bug.
- **8 of those 12 restart attempts failed outright** ("Restarting container X failed" in autoheal's own log) — restarting a container costs CPU/memory on a host that's already contended, the same resource pressure that likely caused the unhealthy flip in the first place, so autoheal's own fix attempt competed with the actual cause rather than resolving it.
- Separately, `redis`, `assessment-service`, and `user-service` were all found fully **crashed** (`docker ps -a`: exit code 137, consistent with an out-of-memory kill) around the same window — `restart: always` (already on every service, no autoheal needed) should handle that case on its own; it isn't yet confirmed why it didn't recover them here, and is the next real thing to look into if it recurs, not the autoheal question.
- Net effect: autoheal added a moving part that failed more than it succeeded and didn't address the real cause (host resource contention), so it was removed rather than tuned further — the timeout tightening above (which makes any individual slow/stale call fail fast and degrade gracefully instead of hanging) is the part of this incident's response that's actually carrying weight; a container-restart supervisor is not, on this host, and re-adding one should wait for real evidence it would help rather than repeating the same attempt.

**Not fixed, only mitigated.** This dev host runs Docker Desktop 29.2.1 on the default `bridge` driver, backed by WSL2 (`docker info`: `6.6.87.2-microsoft-standard-WSL2`) — Docker-Desktop-on-WSL2's network virtualization (the WSL2 VM's own NAT layer, and the VM itself being throttled/suspended during host idle to save resources) has long-documented issues with inter-container TCP connections silently going stale after periods of inactivity, without a clean RST/FIN either side can detect until the next real attempt times out. That matches this incident's exact shape (fine under active use, breaks after ~31h idle, a plain restart fixes it instantly, no resource exhaustion). This was not independently reproduced or filed upstream as *the* confirmed cause — it's the best-fit explanation given the evidence gathered, not a certainty. If this recurs even with `autoheal` in place, the next real test is whether the same staleness reproduces on a non-Docker-Desktop host (a real Linux Docker Engine, or a cloud VM) — if it doesn't, that confirms WSL2's networking layer as the cause; if it does, look elsewhere (app-level connection pooling, `pgbouncer`, etc.).

**Known related gap, not fixed by this incident's response:** every service in `infra/docker-compose.dev.yml` runs `UVICORN_WORKERS: "1"` — a single worker thread means one slow/blocked call (like the one above) stalls literally every other concurrent request to that same service, not just the one that triggered it. This is a dev-only setting (each service's `entrypoint.sh` defaults to 3 workers, and production's compose file has no override, so production was never affected). Raising it in dev has real tradeoffs (more memory per service, and any code that assumes single-worker in-process state would need auditing first) — left as an explicit, deliberate decision for whoever picks it up next rather than changed reflexively here.

---

## Known Incident — Unprotected Throttles Crashing Live Exams (2026-08-17)

**Found by**: a full live-exam scenario audit (positive/negative/edge/worst-case), triggered by the login-crash incident above. The question asked: does the *same* class of Redis-outage bug threaten anything a student depends on mid-exam, not just the admin-facing papers list?

**Finding, confirmed with a real reproduction, not inferred:** `ACCESS_TOKEN_LIFETIME` is 15 minutes (auth-service `core/settings.py`), but exams routinely run 30–60+ minutes — so the frontend's axios interceptor silently calls `POST /api/auth/token/refresh/` partway through virtually every real exam. That endpoint (SimpleJWT's stock `TokenRefreshView`, inheriting auth-service's `DEFAULT_THROTTLE_CLASSES`) had the exact same unprotected-throttle gap that crashed login: reproduced by patching the cache backend to raise `redis.exceptions.ConnectionError` and hitting the real endpoint — same unhandled 500. The consequence chain, every link confirmed: Redis blip → 15-minute token expires mid-exam (guaranteed on any real exam) → silent refresh → refresh 500s → frontend's `catch (refreshError) { ...; forceLogout() }` treats *any* refresh failure as a dead session → **student is force-logged-out of a live, in-progress exam**, even though their session, timer, and autosaved answers are all completely intact server-side the whole time.

Root cause of the asymmetry: assessment-service already had this exact bug class fixed (`core/throttling_resilience.py`, Task 13.1, explicitly built for this) — but it was scoped to that one service. auth-service, and in fact every other service (`user-service`, `practice-service`, `resource-service`, `notification-service`, `analytics-service`), still used DRF's raw `AnonRateThrottle`/`UserRateThrottle` directly.

**Fix:** the same `ResilientThrottleMixin` pattern (fail *open* — allow the request, unthrottled — rather than 500 when Redis is unreachable; nginx's own per-IP rate limiting remains the primary defense throughout the outage) was mirrored into all 6 remaining services' own `core/throttling_resilience.py`, wired into each `DEFAULT_THROTTLE_CLASSES`, and additionally applied to auth-service's custom per-account `LoginAttemptThrottle` (the one that crashed originally). Re-ran the exact same reproduction against the fixed code: login now correctly returns `401` on a wrong password (not 500) and `200` on a real one; refresh now correctly returns `200` with a fresh token — both under the identical simulated outage that previously crashed them. New regression tests in `services/auth-service/tests/test_redis_resilience.py`. All 7 services' full test suites re-run clean after the fix (auth-service's twice, matching this platform's resilience-testing convention).

**Also found in the same pass, lower severity:** `AssessmentSession.SESSION_STATUS_EXPIRED_UNSTARTED` is defined and documented in ADR 001 but never actually gets set anywhere — a no-show student just reads as `exam_status: pending` indefinitely via a simpler read-time computation that ships instead. Not a functional bug (admins can still tell "never attempted" from assignment status + pending), just a design/implementation mismatch — left as a clarifying code comment on the constant rather than building the originally-documented write path, since that would mean auditing every completion-rate/analytics aggregate that currently assumes "a ResultSummary row exists" means "actually completed."

**Follow-up (same day) — multi-tab lockout evasion, frontend.** A further audit of the exam-taking UI's client-side lockout mechanism (the tab-switch/fullscreen-exit auto-submit feature) found it tracked violation counts in plain React state — reset the instant the tab closed, so a student could open a fresh tab of the same exam specifically to dodge it. The *server-side* malpractice flag was never fooled (it's computed from cumulative `ActivityLog` rows against the one shared session, not a per-tab count), but the client-side auto-submit consequence was evadable. Fixed by persisting the counts to `localStorage` keyed by session id (same convention as `assessmentOfflineQueue.ts`), with a `storage` event listener so a currently-open sibling tab of the same exam also stays in sync, and explicit cleanup only at a genuine terminal session status (not on every component unmount, which would also fire on an ordinary in-app navigation away from a still-active exam and silently re-open the same hole). This does not and cannot fix the separate, inherent Visibility API limitation that a student switching between two tabs of their *own* same exam is indistinguishable from switching to a different application — both legitimately count as a tab switch, same as always. `tsc`/jest (152 tests, twice) clean after the change.

**Follow-up (same day) — timer extension audit.** A dedicated audit of the admin "extend a student's exam time" action (used for genuine technical-difficulty cases) found two gaps, both closed: (1) no frontend UI existed for it at all — the backend endpoint (`PATCH .../sessions/<id>/extend/`) was reachable but no admin screen called it; added an "Extend Time" action + modal to the results table (`frontend/src/app/admin/assessments/results/[assignment_id]/page.tsx`), and a `lastExtension` detection in `useServerTimeSync.ts` (compares each poll's `ends_at` against the previous poll's) that surfaces a toast — "your exam time was extended by N minute(s)" — to the affected student's own screen and keeps their countdown in sync, within one poll cycle (~20s, ADR 001 — no push channel). (2) A real TOCTOU race in the endpoint itself: it read `session.status`, decided whether to allow the extension, and only then wrote `ends_at` — the beat sweep could finalize that exact session in the gap between the read and the write, and the write would still land unconditionally on an already-terminal, already-scored session. Fixed with the same conditional-`UPDATE ... WHERE status=...` pattern used everywhere else in this file (`AdminAssignmentExtendSessionView.patch`) — whichever write wins the race is what actually happens, instead of trusting a status read from moments earlier. Full suite + `tsc`/jest clean after the fix.

## Known Feature — Plain-English Activity Timeline + 15-Day Retention Purge (2026-08-17)

**What:** an "eye icon" column ("Logs/Tracking") in the admin results table opens a popup showing one student's exam activity — start, each anti-cheat event, then submit/auto-submit — as short, non-technical sentences ("Switched away to another browser tab", not `tab_switch`), so a non-IT admin can audit behaviour without needing to understand the raw event taxonomy. Backed by a new endpoint, `GET /api/assessments/admin/sessions/<session_id>/timeline/` (`AdminSessionTimelineView`, `assessments/views.py`) — keyed by `session_id`, not `result_id`, specifically so it also works for a student still mid-exam (`exam_status="writing"`, no `ResultSummary` yet). IDOR-scoped through `assignment__institution_id`, same as the extend-session endpoint. Response is capped at 2000 events (`_SESSION_TIMELINE_EVENT_CAP`) with a `truncated`/`total_event_count` pair the UI surfaces — a popup, not a paginated table, so it caps rather than paginates; 2000 events is far beyond any real exam's worst case.

**Retention:** the raw `ActivityLog` audit trail (tab-switch/copy/paste/etc. — *not* `AssessmentResponse`, `ResultSummary`, or any score/pass-fail value, which are permanent academic records) is deleted 15 days after the fact (`ACTIVITY_LOG_RETENTION_DAYS`, `assessments/models.py` — the single source of truth the purge task and the popup's own "erased after 15 days" notice both read from, so the two can never silently drift apart). A new daily Celery beat task, `purge_old_activity_logs` (`assessments/tasks.py`, registered in `CELERY_BEAT_SCHEDULE` as `purge-old-activity-logs`, 86400s), batches the deletion (1000 rows/batch, same discipline as `allocation.py`'s `bulk_create`) and — belt-and-suspenders, even though 15 days vastly exceeds any real exam's duration — excludes any session still `IN_PROGRESS` no matter how old its logs are, on principle. Uses the same `DeadLetteringTask` base as the two sweep tasks, so an exhausted-retry failure lands in the `FailedJob` DLQ rather than silently vanishing.

**Verified live**, not just by unit tests: dispatched `purge_old_activity_logs.delay()` through the real Celery broker/worker (not an in-process call) against a real throwaway stale `ActivityLog` row and confirmed deletion; separately confirmed a fresh (14-day-old) log survives and a stale (20-day-old) log on a still-`IN_PROGRESS` session survives the safety guard; hit the new timeline endpoint against a real auto-submitted session with 6 real `ActivityLog` rows and confirmed the plain-English translation, the malpractice flag, and the 404 IDOR guard against a cross-institution admin and a nonexistent session id. Backend: 14 new tests (`tests/test_admin_results.py::TestSessionTimeline`, `tests/test_sweep.py::TestPurgeOldActivityLogs`), full suite (361 tests) clean twice consecutively. Frontend: new `src/tests/adminResultsTimeline.test.tsx`, `tsc`/jest (157 tests) clean twice consecutively.

**Gotcha found and fixed while shipping this:** `assessment-worker` and `assessment-beat` build as **separate Docker images** from `assessment-service` in `infra/docker-compose.dev.yml` (each has its own `build:` block, same Dockerfile/context, no shared `image:` tag) — `docker compose build assessment-service` only rebuilds the API image. A code change that only the worker/beat processes execute (like a new Celery task) silently never reaches them unless `assessment-worker`/`assessment-beat` are *also* explicitly rebuilt — confirmed live: after rebuilding only `assessment-service`, the new task was registered and callable via the API-serving container's own shell, but absent from `django_celery_beat`'s `PeriodicTask` table and from the real worker's `[tasks]` list, because those two containers were still running the previous image. Any future change to `assessments/tasks.py` (or anything else the worker/beat processes import) must rebuild all three: `docker compose build assessment-service assessment-worker assessment-beat`.

---

## Sentry

Wired (`core/settings.py`) but the DSN is intentionally empty in dev, matching this platform's existing convention (`docs/secrets.md`) — every deliberate error this service raises is tagged with the same correlation ID described above via a `before_send` hook, so once a real DSN is populated (Task 15.2's pre-launch checklist item, not this task's), a Sentry event and this service's own JSON logs for the same request are cross-referenceable by that one ID.
