# essay-service — Exam-Day Incident Runbook

**Task:** [LIVETRACKER3_V1.md](../../LIVETRACKER3_V1.md) Task 17.3
**Related:** [essay-service-operations.md](../essay-service-operations.md) (SLA thresholds this runbook acts on — do not restate numbers here, link to that doc's table), [ADR 002](../adr/002-essay-service-architecture.md), [ADR 003](../adr/003-essay-llm-evaluation-pipeline.md), [ADR 004](../adr/004-essay-service-capacity-plan.md), [assessment-exam-day.md](assessment-exam-day.md) (the structure this runbook follows)

Written for someone who did **not** build this service, mid-exam, under time pressure. Every command below (except §6's disaster-recovery section, which is honestly scoped — see its own note) was actually run against the real dev stack while writing this document.

---

## 1. First 60 seconds — is this real, or normal sweep-lag jitter?

Before touching anything, check [essay-service-operations.md](../essay-service-operations.md)'s SLA table. The auto-submit sweep runs every 20s by design (`core/settings.py`'s `CELERY_BEAT_SCHEDULE`) — an attempt sitting a few seconds past its `ends_at` before auto-submitting is **expected**, not an incident.

```bash
# Submission pipeline breakdown — operations doc query #1
docker exec infra-essay-service-1 python manage.py shell -c "
from essays.models import EssaySubmission
from django.db.models import Count
for row in EssaySubmission.objects.values('status').annotate(n=Count('id')).order_by('status'):
    print(row)
"
```

If attempts are genuinely stuck past their deadline, check the sweep is actually running:

```bash
docker ps --filter "name=essay-beat" --filter "name=essay-worker" --format "{{.Names}}\t{{.Status}}"
docker logs infra-essay-beat-1 --tail 20
docker logs infra-essay-worker-1 --tail 20
```

If either container is down/restarting, that's your incident — restart it and re-check after one full cycle (~20-30s):

```bash
docker compose -f infra/docker-compose.dev.yml up -d essay-worker essay-beat
```

**Gotcha, confirmed live (Task 17.2's own audit):** `essay-service`/`essay-worker`/`essay-beat` build as **three separate Docker images** from the same source — restarting a container alone does *not* pick up a code change; that needs a rebuild first: `docker compose -f infra/docker-compose.dev.yml build essay-service essay-worker essay-beat`, *then* `up -d` all three. See [essay-service-operations.md](../essay-service-operations.md)'s own "Known Gotchas" section for the full reasoning and the sharper no-bind-mount version of this same trap.

---

## 2. Submits are failing (students reporting errors)

Check the essay-specific dev/prod health query — [essay-service-operations.md](../essay-service-operations.md) query #4 — and the health endpoint:

```bash
curl -s http://localhost/api/essay/health/
# {"status":"ok"|"degraded", "db":"ok"|"error", "redis":"ok"|"error"}
```

- **`"redis":"error"`** — autosave and submit are **unaffected** (Task 17.1's live-verified fail-open behavior: `EssayAutosaveRateThrottle` fails open on a Redis outage). The submit-creation throttles (`EssaySubmitRateThrottle` and its two siblings) deliberately **fail closed** instead — a genuine, live-verified design choice (ADR 003 Decision 8 / ADR 004 Section 5), not a bug: during a Redis outage, new submits will correctly 429 rather than risk an unmetered flood against the LLM cost ceiling. Restart Redis when convenient; students who already have a draft saved lose nothing (autosave kept working the whole time).
- **`"db":"error"`** — this **is** exam-blocking, same as every other service on this platform. In this dev environment `essay-service` connects **directly to `essay-postgres`**, not through PgBouncer (see operations doc query #4's own note) — check that container specifically: `docker ps --filter name=essay-postgres`. In production (once the RDS swap-back happens), check RDS's own console status and PgBouncer's `essay_db` pool the same way `assessment-exam-day.md` §4 does for its own database.

**If you see 403s on `/submit/` or `/autosave/`:** very likely not a bug — `attempt_is_writable()` (Task 4.1) returns 403 for an attempt that's already terminal, expired, or whose assignment was closed. Confirm before assuming something is broken:

```bash
docker exec infra-essay-service-1 python manage.py shell -c "
from essays.models import EssayAttempt
a = EssayAttempt.objects.select_related('assignment').get(pk='<attempt_id>')
print(a.status, a.ends_at, a.assignment.status)
"
```

**If you see 500s:** find the correlation ID from the student's `X-Request-ID` response header (or grep nginx's access log by timestamp/URI) and grep every layer for it — this now genuinely works end-to-end (Task 17.2's own live verification), including into the async evaluation task's own log lines:

```bash
docker logs infra-nginx-1 2>&1 | grep "<request_id>"
docker logs infra-essay-service-1 2>&1 | grep "<request_id>"
docker logs infra-essay-worker-1 2>&1 | grep "<request_id>"
```

---

## 3. LLM evaluation backlog or stuck submissions

The one part of this service's own workflow `assessment-service` has no equivalent of. A submission being `PENDING`/`LLM_PROCESSING` for a while is **not itself an incident** — per Non-Negotiable Constraint §5, a student's exam experience is never blocked on evaluation throughput, and ADR 004 Section 3 is explicit that drain time is gated by whatever OpenAI tier is actually provisioned, not a fixed number.

```bash
# Queue depth and worker liveness — operations doc query #3
docker exec infra-essay-service-1 python manage.py shell -c "
import redis
from django.conf import settings
from core.celery import app as celery_app
r = redis.from_url(settings.REDIS_URL)
print('queue_depth:', r.llen(settings.CELERY_TASK_DEFAULT_QUEUE))
pong = celery_app.control.ping(timeout=2.0) or []
print('celery_workers_online:', len(pong))
"
```

**Escalate as a real incident if:** `celery_workers_online` is 0 (the worker itself is down — check `docker ps`/logs, same as §1), *or* the DLQ backlog (operations doc query #2) is genuinely growing rather than draining, *or* a specific submission has sat at `LLM_PROCESSING` for far longer than a single evaluation call should ever take (ADR 003's own `time_limit=90, soft_time_limit=75` per attempt) — that specific shape (stuck mid-processing, not queued) means a worker crashed exactly between two writes; `evaluate_essay`'s own self-healing check (Task 16.1's own final-audit-round finding) repairs this automatically the next time anything re-touches that submission, so simply re-triggering it (below) is the correct, safe fix, not a workaround.

**To manually retrigger one submission** (admin action — `AdminSubmissionRetriggerView`, `Authorization` header required):

```bash
curl -X POST "http://localhost/api/essay/admin/submissions/<submission_id>/retrigger/" \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Manually retriggered during an exam-day incident."}'
```

This clears any existing score/trace and dispatches a fresh evaluation with its own retry budget (Task 17.2's own fix: this retrigger's log lines now correlate to the admin's own request id, not any earlier failed attempt's).

---

## 4. Stuck / failed jobs (the DLQ)

```bash
# Unresolved backlog + oldest age — operations doc query #2
docker exec infra-essay-service-1 python manage.py shell -c "
from essays.notifications import dlq_unresolved_snapshot
print(dlq_unresolved_snapshot())
"

# The actual entries
docker exec infra-essay-service-1 python manage.py shell -c "
from essays.models import EssayFailedJob
for j in EssayFailedJob.objects.filter(resolved_at__isnull=True).order_by('-created_at')[:10]:
    print(j.created_at, j.task_name, j.task_id, j.dlq_retry_count, '-', j.error[:200])
"
```

**The automatic sweeper (every 5 minutes) already retries most of these on its own** — `sweep_dlq_entries` (Task 5.3 / ADR 003 Decision 6), with a circuit breaker at `DLQ_RETRY_CEILING`. An entry that keeps landing back in the DLQ *repeatedly*, not a one-off, means the retries aren't fixing it — the root cause is persistent (a real bug, or a dependency down long enough to exceed the retry budget). Escalate rather than keep re-triggering by hand.

For `evaluate_essay` entries specifically, prefer the admin retrigger endpoint (§3 above) over manually re-dispatching the Celery task — it also clears the stale score/trace and records a proper `EssaySubmissionEvent`, which a raw `.delay()` call from a shell would silently skip.

**A submission stuck at `PENDING` (not `LLM_PROCESSING`) is a different failure mode from the DLQ above** — it means dispatch itself never reached a worker at all (e.g. Redis was unreachable at the exact moment of submit/auto-close), so it never got the chance to fail and land in the DLQ. Found and fixed post-Task 18.2, live evidence in [LIVETRACKER3_V1.md](../../LIVETRACKER3_V1.md)'s "Post-18.2 follow-up" section. **This count is now also visible directly in the admin Submissions page's own pipeline-health tile** ("N undispatched", same live tile the DLQ count already appears in) — the shell query below is still useful for the exact oldest-age figure and for scripting, but an admin no longer has to reach for a terminal to notice this during an incident.

**If a large number of submissions land at `PENDING` all at once** (e.g. a mass-simultaneous exam expiry — many students' timers ending together — overlapping a genuine broker outage), that is expected, bounded behavior, not a worse incident than a single stuck submission. `_create_and_dispatch_submissions` (essays/scoring.py) stops attempting further dispatches for the rest of that batch after the first broker failure, rather than retrying the same outage once per student — confirmed live at 200-attempt scale to cost about the same few seconds as a single failure, not minutes. Every submission in the batch still exists and self-heals via `sweep_undispatched_submissions` the same as a single stuck one. See [LIVETRACKER3_V1.md](../../LIVETRACKER3_V1.md)'s "Post-18.2 follow-up, round 2" section for the live evidence and numbers.

```bash
# Undispatched-submission backlog — operations doc query #3
docker exec infra-essay-service-1 python manage.py shell -c "
from django.utils import timezone
from essays.models import EssaySubmission, SUBMISSION_STATUS_PENDING
qs = EssaySubmission.objects.filter(status=SUBMISSION_STATUS_PENDING)
oldest = qs.order_by('created_at').first()
print('pending_count:', qs.count())
print('oldest_age_seconds:', (timezone.now() - oldest.created_at).total_seconds() if oldest else None)
"
```

`sweep_undispatched_submissions` (every 60s, `UNDISPATCHED_GRACE_MINUTES = 2`) automatically re-dispatches these once the broker recovers — no manual action needed unless the count keeps growing (broker still down) rather than draining.

---

## 5. Disaster recovery — restoring `essay_db`

**Honest, explicit status (2026-09-23), not glossed over — matching this whole tracker's own established discipline for genuinely open items (see ADR 004's LLM-tier gap for the same pattern):** `essay_db` does **not exist on the real RDS instance yet** (Task 1.2's own still-open note — this dev environment connects directly to a dedicated `essay-postgres` container instead, see [essay-service-operations.md](../essay-service-operations.md) query #4). This means:

- There is **no RDS automated backup covering `essay_db` today**, because there is no `essay_db` on RDS to cover. The moment it's created there, it is automatically covered by `spark-primary-db`'s existing instance-level automated backups (14-day retention) with **zero** essay-specific configuration needed — RDS backs up the whole instance, not per-database, exactly the same as every other service's own database.
- `assessment-service`'s own equivalent RDS restore procedure (`assessment-exam-day.md` §6) has itself **never been tested end-to-end** (`PRODUCTION_CHECKLIST.md`: *"Backup restore was never actually tested"*) — there is no platform precedent of a genuine RDS restore to point to, for any service, essay included.
- Creating or restoring real AWS RDS resources is explicitly outside what this session does unprompted (the same standing convention Task 1.2 already applied to creating `essay_db` itself) — a real RDS restore test is **still this platform's own open item**, not something faked here to look complete.

**What was genuinely tested instead, for real, against the real database that does exist (2026-09-23):** a real `pg_dump`/`pg_restore` cycle against the live `essay-postgres` container, into a genuinely separate, isolated database on the same server — the closest real-infrastructure equivalent available in this environment, not a simulation.

```bash
# 1. Backup (MSYS_NO_PATHCONV=1 needed on Windows Git Bash — /tmp/ otherwise gets
#    mangled into a host path before it ever reaches the container)
MSYS_NO_PATHCONV=1 docker exec infra-essay-postgres-1 pg_dump -U essay_db_user -d essay_db -F c -f /tmp/essay_db_backup.dump

# 2. Create an isolated target database — never restore directly over the live one
docker exec infra-essay-postgres-1 psql -U essay_db_user -d postgres -c "CREATE DATABASE essay_db_restore_test OWNER essay_db_user;"

# 3. Restore into it
MSYS_NO_PATHCONV=1 docker exec infra-essay-postgres-1 pg_restore -U essay_db_user -d essay_db_restore_test /tmp/essay_db_backup.dump

# 4. Verify — content, not just "the command exited 0"
docker exec infra-essay-postgres-1 psql -U essay_db_user -d essay_db_restore_test -c "SELECT id, title FROM essay_papers;"
```

**Verified, real results:** a real seeded row's exact id and content matched between the original and the restored database; all 26 tables and all 44 applied Django migrations matched; all 8 of this build's own custom indexes (`idx_ea_status_expire`, `idx_efj_resolved_created`, etc. — Task 16.1's own work) survived identically; `python manage.py migrate essays --check --plan`, run directly against the restored database via `DB_NAME=essay_db_restore_test`, confirmed **"No planned migration operations"** — the real Django app, not just `psql`, genuinely recognizes the restored copy as fully migrated and usable.

**No new gotcha found, despite genuinely trying** — checked ownership (what happens if the target database isn't explicitly created with the right `OWNER`), table/column-level permissions (the `REVOKE PUBLIC`/per-user-`GRANT` model from `infra/init-db.sql`), and sequence continuity (every model here uses a UUID primary key, `default=uuid.uuid4` — there is no integer-sequence-reset gotcha class to hit at all, unlike a typical Django app with auto-incrementing PKs). All came back clean. The one gotcha that **does** apply, already documented once for `assessment-service` and not re-discovered as new here because it's a general PostgreSQL truth, not an essay-specific one: **a backup only contains the schema that existed at backup time** — before treating an old backup as a restore baseline, confirm which migrations had been applied by that backup's timestamp (`django_migrations`, itself included in every backup) and re-apply anything newer after restoring.

**Cutover procedure, once `essay_db` is real on RDS:** follow `assessment-exam-day.md` §6 steps 1, 3, and 4 verbatim (restore-to-point-in-time into a new instance, cut over via `infra/pgbouncer/pgbouncer.ini`'s `host=` — which already has `essay_db`'s pool entry waiting, unused, exactly for this — then delete the temporary instance), substituting `essay_db`/`essay_db_user` for that section's `assessment_db`/`assessment_db_user`.

---

## 6. Alerting-threshold quick reference

Full definitions and rationale live in [essay-service-operations.md](../essay-service-operations.md)'s SLA table — this is only a pointer so you don't have to context-switch documents mid-incident:

| Alert fires on... | Go to section |
|---|---|
| Submit-endpoint p99 > 5s sustained | §2 |
| DLQ backlog entry older than the retry-ceiling window | §4 |
| Undispatched submissions (`PENDING`) older than 2× `UNDISPATCHED_GRACE_MINUTES` | §4 |
| `celery_workers_online` == 0, or DLQ backlog genuinely growing | §3 |
| `essay-postgres`/PgBouncer connection load elevated | §2 |

## Plagiarism flags

A flag from the same-wording checker means one student's answer shares a large share of five-word runs with another student's answer in the same question set. It is a review trigger, not proof of cheating.

- Open the flagged attempt and the pair it matched. Read both answers before deciding anything.
- Do not penalise a student based on the flag alone. Shared topic vocabulary can produce matches between honest students.
- Expect the checker to miss heavy word-swapping and paraphrasing. Its silence is not evidence that an answer is original.
- Record the outcome in your exam-day incident notes. The system does not yet have an admin action to close a flag, so the decision is not stored in the app.
