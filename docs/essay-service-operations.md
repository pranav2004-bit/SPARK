# essay-service — Operations, SLA & Monitoring

**Task:** [LIVETRACKER3_V1.md](../LIVETRACKER3_V1.md) Task 17.2
**Related:** [ADR 002 — Essay Service Architecture](adr/002-essay-service-architecture.md), [ADR 003 — LLM Evaluation Pipeline](adr/003-essay-llm-evaluation-pipeline.md), [ADR 004 — Capacity Plan](adr/004-essay-service-capacity-plan.md), [assessment-service-operations.md](assessment-service-operations.md) (the reference standard this document follows)

No dedicated metrics/APM stack exists for this platform yet — matching `assessment-service`'s own Task 13.2 precedent, this document is the "documented queries" half of that same allowance, not a placeholder for a dashboard that doesn't exist. Every query below was run against the real dev stack before being written down — two of them surfaced genuine bugs in the process (see "Found while writing this document" below), not just numbers to copy in.

---

## SLA Definitions

| Metric | Target | Alert Threshold | Why this number |
|---|---|---|---|
| Submit-endpoint (`POST .../attempts/<id>/submit/`) p99 latency | < 2s | Sustained p99 > 5s over a 5-minute window | A manual submit's `finalize_attempts()` call touches exactly one attempt — near-instant in isolation, matching `assessment-service`'s own equivalent number. 2s gives headroom for DB contention during a submit spike near an assignment's `global_expire_time`; 5s sustained is a genuine problem. |
| Evaluation queue drain time | See ADR 004 Section 3's own table — **no single target**, gated by whatever OpenAI tier is actually provisioned | Any submission sitting at `LLM_PROCESSING`/`PENDING` for longer than 2× the current tier's worst-case drain estimate | ADR 004 is explicit that this number cannot be stated until a real OpenAI tier is provisioned — do not invent one here. Once a tier is confirmed, substitute its real number from ADR 004 Section 3's corrected table into this row. |
| DLQ backlog (`EssayFailedJob`, unresolved) | 0 at rest | Any entry older than `DLQ_GRACE_PERIOD_MINUTES` × (`DLQ_RETRY_CEILING` + 1) that is still unresolved | The automatic sweeper (Task 5.3, every 5 minutes) should self-heal or circuit-break every entry within its own retry ceiling — anything surviving past that window needs a human, not another automatic retry. |
| Undispatched submissions (`EssaySubmission` at `PENDING` whose `evaluate_essay`/`check_text_similarity` never reached a worker at all — e.g. Redis unreachable at the moment of dispatch) | 0 at rest | Any row older than 2× `UNDISPATCHED_GRACE_MINUTES` still `PENDING` | `sweep_undispatched_submissions` (every 60s) re-dispatches these automatically once the broker recovers — a different failure mode from the DLQ row above (which only ever catches a task that *did* reach a worker and failed there), found and fixed post-Task 18.2; see [LIVETRACKER3_V1.md](../LIVETRACKER3_V1.md)'s "Post-18.2 follow-up" section for the live evidence. A large batch landing here at once (e.g. a mass-simultaneous exam expiry overlapping an outage) is expected, bounded behavior, not a worse incident — see that same file's "round 2" section for the live-verified circuit-breaker numbers (200-attempt batch costs the same few seconds as a 1-attempt one). **Now surfaced directly in `AdminSubmissionsPipelineHealthView` / the admin Submissions page's own live tile** (`undispatched_submission_count` / `oldest_undispatched_submission_age_seconds`), added 2026-09-24 — the same place `unresolved_dlq_count` already appears, no longer shell-query-only. |
| PgBouncer pool utilization (`essay_db` pool, once the RDS swap-back happens) | `cl_waiting == 0` | Any sustained `cl_waiting > 0`, or `maxwait > 5` (seconds) | Same reasoning as `assessment-service`'s identical row — the concrete, measurable precursor to DB-connection starvation under load. **Not yet applicable to this dev environment** — see "Found while writing this document" below. |

These are starting targets, not load-tested conclusions — Task 18.1's real load test is the authority on whether they need revising, matching `assessment-service`'s own "don't guess ahead of real data" discipline.

**Update, post-Task 18.1:** the submit p99 target above was tested at real concurrent load (20/50/100/200 students) and was **not met** on this dev machine's Docker Desktop VM (2 CPU cores shared across 24 containers) — see [essay-service-load-test-results.md](essay-service-load-test-results.md) for the full numbers and root-cause analysis (the identical 2-CPU-core ceiling `assessment-service`'s own load test already found on this same host, not a code defect). No data corruption, no duplicate submissions, and no container crash occurred at any scale tested. Treat the target above as **production-scoped and not yet dev-environment-verified** — re-validate on hardware with real CPU headroom before relying on it operationally, matching `assessment-service-operations.md`'s own identical caveat for its equivalent target.

---

## Operational Queries

### 1. Submission pipeline status breakdown

A live gauge of where every submission currently sits in the pipeline — useful context, not itself an SLA target.

```bash
docker exec infra-essay-service-1 python manage.py shell -c "
from essays.models import EssaySubmission
from django.db.models import Count
for row in EssaySubmission.objects.values('status').annotate(n=Count('id')).order_by('status'):
    print(row)
"
```

### 2. DLQ backlog — unresolved count and oldest age

Reuses the exact helper `AdminPipelineHealthSummaryView`/the notifications sweep already call — one function, not a second hand-rolled query that could silently drift from the real dashboard's own number.

```bash
docker exec infra-essay-service-1 python manage.py shell -c "
from essays.notifications import dlq_unresolved_snapshot
count, oldest_age_seconds = dlq_unresolved_snapshot()
print('unresolved:', count, 'oldest_age_seconds:', oldest_age_seconds)
"
```

### 3. Undispatched-submission backlog — stuck-at-PENDING count and oldest age

**Added 2026-09-24: this is now also a live number in the admin UI** (`AdminSubmissionsPipelineHealthView`'s own `undispatched_submission_count`/`oldest_undispatched_submission_age_seconds`, rendered in the admin Submissions page's pipeline-health tile) — that one is scoped to genuinely *stuck* rows (past `UNDISPATCHED_GRACE_MINUTES`), matching `sweep_undispatched_submissions`'s own definition exactly. The query below counts every `PENDING` row regardless of age, a broader, purely diagnostic number — normal, healthy operation always has a few (a submission is briefly `PENDING` for milliseconds before a worker picks it up), so don't read a small nonzero count here as an incident by itself.

```bash
docker exec infra-essay-service-1 python manage.py shell -c "
from django.utils import timezone
from essays.models import EssaySubmission, SUBMISSION_STATUS_PENDING
qs = EssaySubmission.objects.filter(status=SUBMISSION_STATUS_PENDING)
oldest = qs.order_by('created_at').first()
print('pending_count:', qs.count())
print('oldest_age_seconds:', (timezone.now() - oldest.created_at).total_seconds() if oldest else None)
"
```

### 4. Celery queue depth and worker liveness

```bash
docker exec infra-essay-service-1 python manage.py shell -c "
import redis
from django.conf import settings
from core.celery import app as celery_app
r = redis.from_url(settings.REDIS_URL)
print('queue_depth:', r.llen(settings.CELERY_TASK_DEFAULT_QUEUE))
pong = celery_app.control.ping(timeout=2.0) or []
print('celery_workers_online:', len(pong), [list(p.keys())[0] for p in pong])
"
```

**`celery_workers_online` is only trustworthy as of this task's own fix (2026-09-23)** — see "Found while writing this document" below for why it was silently counting workers from unrelated services before that.

### 5. Database connection load (dev: `essay-postgres` direct; prod: PgBouncer `essay_db` pool)

This dev environment connects directly to a dedicated `essay-postgres` container, **not** through PgBouncer (see `infra/docker-compose.dev.yml`'s own comment on the `essay-service`/`essay-worker`/`essay-beat` blocks, and Task 1.2's tracker note) — the `essay_db` PgBouncer pool already exists in `infra/pgbouncer/pgbouncer.ini` but is genuinely unused until the real RDS swap-back happens. Use the query that matches whichever backend is actually live:

```bash
# Dev (essay-postgres direct) — the real query for THIS environment today:
docker exec infra-essay-postgres-1 psql -U essay_db_user -d essay_db -c \
  "SELECT count(*) AS active_connections, max(now() - query_start) AS longest_query_age FROM pg_stat_activity WHERE datname='essay_db';"

# Prod (once the RDS swap-back happens, PgBouncer's essay_db pool becomes real):
MSYS_NO_PATHCONV=1 docker exec -e PGPASSWORD=<postgres_password> infra-pgbouncer-1 \
  psql -h 127.0.0.1 -p 5432 -U postgres pgbouncer -c "SHOW POOLS;"
# Look at the essay_db row specifically — cl_waiting > 0 is the concrete signal in the SLA table above.
```

### 6. Nginx rate-zone status (once the real gateway is reachable)

The dedicated zones from ADR 004 Section 4 / Task 15.2 (`essay_autosave_zone`, `essay_submit_zone`, `essay_admin_bulk_zone`) follow `assessment-service`'s own `token_refresh_zone`-style pattern — status/latency breakdown reads from nginx's own JSON access log the same way:

```bash
docker logs infra-nginx-1 --since 1h 2>&1 \
  | grep -o '"uri":"[^"]*/submit/"[^}]*"status":[0-9]*' \
  | grep -o '"status":[0-9]*' | sort | uniq -c
```

**Not yet live-verifiable against the real gateway container in this dev environment** — `infra-nginx-1` sits `Created`, never started, blocked by the same pre-existing, already-documented `pgbouncer`→RDS crash-loop noted throughout Phase 15's own audits. The query itself is correct (same `log_format json_access` every other service's doc reads from) and ready the moment that infra gap is resolved; it was not skipped here, just genuinely blocked the same way it was for Task 15.2.

### Correlating a specific student's request end to end

Every request carries one correlation ID (`core/logging_utils.py`, mirroring `assessment-service`'s Task 13.2 pattern exactly) from nginx's own `$request_id` through this service's structured JSON logs, into the async evaluation pipeline's own Celery task logs, and back to the client as the `X-Request-ID` response header:

```bash
docker logs infra-nginx-1 2>&1 | grep "<request_id>"
docker logs infra-essay-service-1 2>&1 | grep "<request_id>"
docker logs infra-essay-worker-1 2>&1 | grep "<request_id>"
docker logs infra-essay-beat-1 2>&1 | grep "<request_id>"
```

**Live-verified genuinely end-to-end (2026-09-23), not assumed from the code:** a real student submit request carrying a simulated nginx `X-Request-ID` header produced the exact same id in the HTTP response's `X-Request-ID` header AND in the asynchronously-dispatched `evaluate_essay` Celery task's own log line in `essay-worker`'s real container output — see "Found while writing this document" below for the two real bugs this verification found and fixed along the way, and why the id is threaded through explicitly as a task argument (`correlation_id`) rather than relying on `self.request.id`, unlike this platform's periodic sweep tasks (`sweep_expired_assignments` etc.), which correctly use their own Celery task id since they have no originating HTTP request to recover.

The DLQ sweep's own retried `evaluate_essay` dispatches (Task 5.3) tag the retried evaluation with the *sweep run's own* correlation id, not the original (long-gone) submission's — that's the deliberately correct choice, not a limitation: an on-call engineer tracing a DLQ-driven retry wants "which sweep run retried this," and the original failure's own history is still fully recoverable from `EssayFailedJob`/`EssaySubmissionEvent`, just not via live log grep years later.

---

## Found while writing this document (2026-09-23)

Two genuine, previously-undetected bugs, both found because this task's own standard — "verified against real data before being documented," not copied from `assessment-service`'s doc and assumed to also hold here — was actually followed, not treated as a formality.

**1. Celery's real worker process was silently discarding structured JSON logging entirely.** `core/celery.py` never overrode `worker_hijack_root_logger` (Celery's own default is `True`), so the real `essay-worker`/`essay-beat` container processes installed their own plain-text root logger on startup, overriding `core/settings.py`'s `LOGGING` dict (the JSON formatter + `CorrelationIdLogFilter` that gives every log line its `request_id`). Every task in `essays/tasks.py` dutifully called `bind_request_id(...)` the whole time — the *value* was always computed correctly — but it was never actually visible in the real worker's own log output, only under `manage.py shell` (which never starts a real Celery worker, so nothing ever hijacked the root logger there, silently hiding the gap from every manual spot-check that used that shortcut). Fixed with `app.conf.worker_hijack_root_logger = False`. Inherited verbatim from `assessment-service`'s own `core/celery.py`, which has the identical, never-overridden default — out of this task's own scope, a platform-wide follow-up has been flagged separately.

**2. `celery_workers_online` (`AdminSubmissionsPipelineHealthView`) was counting workers from unrelated services.** `control_exchange` also defaults to the literal string `"celery"` for every Celery app regardless of its own name — since all 8 services share one Redis broker, and Celery's remote-control/pidbox mechanism (what `control.ping()` uses) routes through a channel keyed off `control_exchange`, not the app's own name, every service's worker replied to every other service's ping. Confirmed live: essay-service's own `control.ping()` returned 5 distinct container hostnames before the fix, 1 (correctly, just `essay-worker`'s own) after. Fixed with `app.conf.control_exchange = "essay-service"`. Same platform-wide follow-up flagged for the other 7 services.

Both fixes are two lines in `services/essay-service/core/celery.py`; full reasoning and the exact live-verification commands are in that file's own inline comments. Full backend suite re-run twice consecutively after each fix, `PYTEST_EXIT:0` both times.

---

## Known Gotchas (essay-service specific)

**`essay-service`/`essay-worker`/`essay-beat` build as three separate Docker images** from the same `services/essay-service` context (`infra/docker-compose.dev.yml`, each with its own `build:` block) — the identical pattern already documented in `assessment-service-operations.md`'s own "Gotcha" note for that service's worker/beat. `docker compose build essay-service` alone does **not** reach the worker or beat processes; any change to `essays/tasks.py` (or anything else those two processes import) needs all three rebuilt together: `docker compose build essay-service essay-worker essay-beat`. Every rebuild cycle across this entire tracker has followed this three-service pattern for exactly this reason.

**None of the three has a dev bind-mount** (confirmed directly in `infra/docker-compose.dev.yml` — no `volumes:` key on any of them), which is a real, sharper version of the gotcha above: a file generated *inside* a running container (most importantly, a Django migration via `python manage.py makemigrations` run through `docker exec`) is written only to that container's writable layer and is **silently lost** the next time the image is rebuilt — the container's filesystem is rebuilt fresh from host disk, which never received the generated file. Phase 16's own audit lost a real migration this way before catching it. The only safe pattern: immediately `docker cp <container>:/app/<generated-file> <host-path>` right after generating anything inside these containers, before any subsequent `docker compose build` can discard it.

---

## Sentry

Wired (`core/settings.py`, mirroring `assessment-service`'s own setup) but the DSN is intentionally empty in dev, matching this platform's existing convention (`docs/secrets.md`) — deliberate errors are tagged with the same correlation ID described above via a `before_send` hook, so once a real DSN is populated pre-launch, a Sentry event and this service's own JSON logs for the same request are cross-referenceable by that one ID, the same as `assessment-service`.

## Running the test suite

- Default (what CI runs): `docker exec infra-essay-service-1 python -m pytest -q`. Uses in-memory SQLite (`core/test_settings.py`). Every test runs, except the Postgres-only concurrency test, which is skipped.
- Postgres-only concurrency test, against the real dev Postgres container: `docker exec -e TEST_USE_POSTGRES=1 infra-essay-service-1 python -m pytest -q tests/test_admin_results.py::TestGeneralScoreOverride::test_two_concurrent_overrides_never_lose_an_update`. Required before any change to row-locking in the admin override path, because SQLite cannot exercise `select_for_update`.
- Migration safety, the same checks CI runs: `python manage.py makemigrations --check --dry-run --settings=core.test_settings` and `python manage.py lintmigrations --settings=core.test_settings --exclude-apps django_celery_beat token_blacklist`.
- Any test-file change needs an image rebuild first, because the test files are baked into the image and are not bind-mounted.

## Same-wording plagiarism checker

- **What it does:** compares each newly submitted essay against the already-finished essays in the same assignment and question set, and flags pairs that share enough wording.
- **How it measures:** it counts runs of five consecutive words that appear in the same order in both essays. The score is the share of the student's five-word runs that also appear in the other essay.
- **Threshold:** a score of 0.30 or higher flags the attempt for review (`ESSAY_TEXT_SIMILARITY_THRESHOLD`). A flag is a review trigger, not a verdict, and it doesn't change any score or notify the student.
- **Caught:** exact copying, partial copying of several sentences, reordered paragraphs, and phrases reordered within sentences.
- **Known miss:** light word swaps. Changing one word in every four drops the score to 0% and is not flagged. Decision: keep five-word runs for now, because three-word runs would flag more innocent students who share common phrases. Revisit with real essay data.
- **Not detected:** paraphrasing (same meaning, different words), and copying from outside the platform.
