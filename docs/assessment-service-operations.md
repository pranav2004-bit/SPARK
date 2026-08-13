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

## Sentry

Wired (`core/settings.py`) but the DSN is intentionally empty in dev, matching this platform's existing convention (`docs/secrets.md`) — every deliberate error this service raises is tagged with the same correlation ID described above via a `before_send` hook, so once a real DSN is populated (Task 15.2's pre-launch checklist item, not this task's), a Sentry event and this service's own JSON logs for the same request are cross-referenceable by that one ID.
