# assessment-service — Exam-Day Incident Runbook

**Task:** [LIVETRACKER2_V1.md](../../LIVETRACKER2_V1.md) Task 13.3
**Related:** [assessment-service-operations.md](../assessment-service-operations.md) (SLA thresholds this runbook acts on — do not restate numbers here, link to that doc's table), [ADR 001](../adr/001-assessment-timer-architecture.md), [assessment-service-api.md](../assessment-service-api.md)

Written for someone who did **not** build this service, at 2pm during a live exam, under time pressure. Every command below was actually run against the real running dev stack before being written down — see LIVETRACKER2_V1.md's Task 13.3 verification notes for the real output that confirmed each one, and the disaster-recovery section specifically for a real, tested restore.

---

## 1. First 60 seconds — is this real, or normal sweep-lag jitter?

Before touching anything, check [assessment-service-operations.md](../assessment-service-operations.md)'s SLA table. The sweep runs every 20s by design (ADR 001) — a session sitting a few seconds past its deadline before auto-submitting is **expected**, not an incident.

```bash
# Sessions currently IN_PROGRESS — context, not itself a problem signal
docker exec infra-assessment-service-1 python manage.py shell -c "
from assessments.models import AssessmentSession, SESSION_STATUS_IN_PROGRESS
print(AssessmentSession.objects.filter(status=SESSION_STATUS_IN_PROGRESS).count())
"

# Sweep lag — run the query from assessment-service-operations.md's "Operational
# Queries" section #2. Compare the result against that doc's SLA table:
#   avg < 30s           -> normal, stop here
#   avg 30s-120s         -> elevated but not yet alert-worthy, keep watching
#   avg > 120s sustained, OR any single session's lag > 5 min -> real incident, continue below
```

If sweep lag is genuinely elevated, check the sweep is actually running at all:

```bash
docker ps --filter "name=assessment-beat" --filter "name=assessment-worker" --format "{{.Names}}\t{{.Status}}"
docker logs infra-assessment-beat-1 --tail 20
docker logs infra-assessment-worker-1 --tail 20
```

If either container is down/restarting, that's your incident — restart it and re-check lag after one full cycle (~20-30s):

```bash
docker compose -f infra/docker-compose.dev.yml up -d assessment-worker assessment-beat
```

---

## 2. Submits are failing (students reporting errors, or the error-rate query is elevated)

Run [assessment-service-operations.md](../assessment-service-operations.md)'s query #4 (submit-endpoint status breakdown) to see what students are actually hitting.

**If you see 502/503/504s:** a dependency is down. Check each in order (all three have their own graceful-degradation behavior, Task 13.1 — a submit should never hard-fail just because one of these is degraded, *except* the database itself, which is a genuine hard dependency):

```bash
curl -s http://localhost/api/assessments/health/
# {"status":"ok"|"degraded", "db":"ok"|"error", "redis":"ok"|"error"}
```

- `"redis":"error"` — Analytics/Dashboard will be slower (direct computation) but submits themselves are **unaffected** (Task 13.1's `safe_cache_*` wrappers + `ResilientThrottleMixin` — a Redis outage fails open, never blocks a submit). Restart redis when convenient; not an exam-blocking emergency.
- `"db":"error"` — this **is** exam-blocking. Every write (including submit) needs the database. Check `infra-postgres-1` and `infra-pgbouncer-1` are both up and healthy; check PgBouncer pool utilization (operations doc query #3) for `cl_waiting > 0`, which means the database itself is fine but connections are exhausted (see §4 below).

**If you see 403s on `/submit/`:** this is very likely *not* a bug — `session_is_writable()` (Task 4.2) returns 403 for a session that's already finished, already expired, or whose assignment was closed. Confirm with the affected student's session status before assuming something is broken:

```bash
docker exec infra-assessment-service-1 python manage.py shell -c "
from assessments.models import AssessmentSession
s = AssessmentSession.objects.get(pk='<session_id>')
print(s.status, s.ends_at, s.assignment.status)
"
```

If the session is genuinely still supposed to be open and 403s anyway, that's a real bug — escalate, don't attempt a workaround (this is the timer-integrity code path, AT1).

**If you see 500s:** an unhandled exception. Find the correlation ID from the student's `X-Request-ID` response header (or grep nginx's access log by timestamp/URI — see operations doc's "Correlating a specific student's request" section) and grep both nginx's and assessment-service's logs for it to get the full trace. If Sentry has a DSN configured (Task 15.2), the same ID is a Sentry event tag.

---

## 3. Extending time for an affected student

**Use Task 3.2's per-session endpoint. Never edit `global_expire_time`.**

`global_expire_time` only affects the *assignment* and has zero effect on a session that's already started — its `ends_at` was computed once at session-start time and is deliberately never recomputed from the assignment afterward (ADR 001, Decision #2; also Task 5.1's own comment: *"Computed exactly once at creation... never recomputed"*). Editing `global_expire_time` to "fix" a student who lost time will do nothing for them and may confuse the next admin who looks at the assignment.

```bash
curl -X PATCH "http://localhost/api/assessments/admin/assignments/<assignment_id>/sessions/<session_id>/extend/" \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"extend_minutes": 15}'
```

- `extend_minutes` must be a positive integer, capped at 1440 (24h) — Task 12.2's abuse-hardening fix for what used to be an unbounded-input crash risk. A legitimate exam-day extension is almost always well under this.
- This only extends the **one named session** — every other student's session is untouched. Confirmed live: extending one session moves only that session's `ends_at`; a second student's session in the same assignment is unaffected (see LIVETRACKER2_V1.md's Task 13.3 verification notes for the real test that confirmed this).
- The response includes the new `ends_at` — read it back to the requester so there's no ambiguity about how much time was actually granted.

---

## 4. PgBouncer pool exhaustion (`cl_waiting > 0` sustained)

This is the thundering-herd scenario (AT2/AT13) — many students hitting the database at once (global exam start, or a mass-submit near the deadline).

1. Confirm it's real, not a one-off spike: re-run operations doc query #3 twice, ~10s apart. `cl_waiting` should be near-zero between bursts under normal load.
2. Check Postgres itself isn't independently struggling (this is a *shared* instance across all 7 services — AT13):
   ```bash
   docker exec infra-postgres-1 psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
   ```
3. If genuinely sustained: this is a capacity question the tracker itself defers to Phase 14's real load-test numbers (Task 11.1's own notes on `max_client_conn` — do not guess a new number under incident pressure; that's exactly the mistake the tracker's own discipline is built to prevent). The safe in-the-moment action is to confirm the other 6 services aren't being starved (hit their own `/health/` endpoints) and let the queue drain — PgBouncer queues rather than drops, so requests will complete, just slower.
4. Do **not** restart PgBouncer or Postgres to "fix" this unless you have confirmed one of them is actually unresponsive (§1's health check) — restarting a healthy-but-busy database resets every service's connections simultaneously and would make things worse, not better.

---

## 5. Stuck / failed jobs (Task 13.1's DLQ)

The only real background jobs in this service are the two periodic sweeps. A permanently-failed run (retries exhausted) lands in the `FailedJob` table, never silently dropped.

```bash
docker exec infra-assessment-service-1 python manage.py shell -c "
from assessments.models import FailedJob
for j in FailedJob.objects.filter(resolved_at__isnull=True).order_by('-created_at')[:10]:
    print(j.created_at, j.task_name, j.task_id, '-', j.error[:200])
"
```

**To reprocess:** the two sweep tasks are idempotent by construction (the conditional `UPDATE ... WHERE status=...` pattern, Decision #5/AT5) — simply triggering a fresh run is safe and picks up whatever the failed run should have handled, plus anything that's accumulated since:

```bash
docker exec infra-assessment-service-1 python manage.py shell -c "
from assessments.tasks import sweep_expired_assignments, sweep_expired_sessions
print(sweep_expired_assignments())
print(sweep_expired_sessions())
"
```

**Mark the old entry resolved** once you've confirmed the underlying condition is fixed (don't leave it showing as an open incident for the next person):

```bash
docker exec infra-assessment-service-1 python manage.py shell -c "
from django.utils import timezone
from assessments.models import FailedJob
FailedJob.objects.filter(pk='<failed_job_id>').update(resolved_at=timezone.now())
"
```

If the **same** task keeps landing in the DLQ repeatedly (not a one-off), the retries themselves aren't fixing it — that means the root cause is persistent (e.g. a real code bug, or a dependency that's been down long enough to exceed the retry budget), not transient. Escalate rather than keep re-triggering.

---

## 6. Disaster recovery — restoring `assessment_db`

`assessment_db` is included in the platform's existing daily/monthly backup schedule (`infra/scripts/backup.sh`, run by the `db-backup` container) — nothing exam-specific to configure, it was already wired in before this task.

**Tested restore procedure** (run for real against a real backup as part of this task, not just written from the script's logic):

```bash
# 1. Restore into an ISOLATED test database — never restore directly over
#    a live database as your first step, even in a real disaster; confirm
#    the dump is good first.
docker exec -e PGPASSWORD=<postgres_password> infra-postgres-1 \
  psql -U postgres -c "CREATE DATABASE assessment_db_restore_test;"

docker exec -e PGPASSWORD=<postgres_password> infra-db-backup-1 sh -c "
  pg_restore -h postgres -p 5432 -U postgres -d assessment_db_restore_test \
    --no-owner --no-privileges \
    /backups/daily/assessment_db_<TIMESTAMP>.dump
"

# 2. Verify — row counts on the tables that matter, plus a spot-check that
#    actual content (not just row counts) survived intact.
docker exec -e PGPASSWORD=<postgres_password> infra-postgres-1 \
  psql -U postgres -d assessment_db_restore_test -c "
    SELECT 'assessment_question_papers', count(*) FROM assessment_question_papers
    UNION ALL SELECT 'assessment_sessions', count(*) FROM assessment_sessions
    UNION ALL SELECT 'assessment_result_summaries', count(*) FROM assessment_result_summaries;
  "

# 3. Only once satisfied: this is the point where you'd cut over the real
#    database. That's a bigger, riskier operation (stopping every
#    assessment-service/worker/beat container, renaming/dropping the live
#    DB, renaming the restored one into place, running any migrations
#    applied since the backup) — deliberately not scripted as a one-liner
#    here; a real cutover during an actual incident should be done
#    carefully with a second person, not copy-pasted under pressure.

# 4. Clean up the test database once done verifying.
docker exec -e PGPASSWORD=<postgres_password> infra-postgres-1 \
  psql -U postgres -c "DROP DATABASE assessment_db_restore_test;"
```

**Known gotcha, confirmed while testing this exact procedure:** a backup only contains whatever tables/schema existed *at backup time*. A backup taken before a migration was applied will not include the tables/columns that migration added — this is correct, expected pg_dump/pg_restore behavior, not a bug, but it means: **before treating an old backup as a full restore baseline, confirm which migrations had been applied by that backup's timestamp** (`django_migrations` table, included in every backup) **and re-apply any migrations newer than the backup after restoring, before pointing the service at it.** Do not assume a restored database has the current schema.

---

## 7. Alerting-threshold quick reference

Full definitions and rationale live in [assessment-service-operations.md](../assessment-service-operations.md)'s SLA table — this is only a pointer so you don't have to context-switch documents mid-incident:

| Alert fires on... | Go to section |
|---|---|
| Submit-endpoint p99 > 5s sustained | §2 |
| Sweep lag average > 120s, or any session > 5 min | §1 |
| PgBouncer `cl_waiting > 0` sustained, or `maxwait > 5s` | §4 |
| A `FailedJob` DLQ entry | §5 |
