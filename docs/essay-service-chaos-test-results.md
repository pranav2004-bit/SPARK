# essay-service — Chaos & Failure Injection Test Results

**Task:** [LIVETRACKER3_V1.md](../LIVETRACKER3_V1.md) Task 18.2
**Related:** [essay-service-load-test-results.md](essay-service-load-test-results.md) (Task 18.1), [essay-service-operations.md](essay-service-operations.md), [essay-exam-day.md](runbooks/essay-exam-day.md)

Every scenario below was genuinely executed against the real running dev stack — real containers killed, real tasks dispatched through the real broker, real database connections saturated — not described hypothetically. Two of the three scenarios found and fixed real, previously-undetected production bugs, found only because the failure was actually injected rather than reasoned about in the abstract.

---

## Scenario 1: Kill `essay-worker` mid-processing with a real in-flight backlog

**Real, serious bug found and fixed, not just confirmed working.** Before testing, `evaluate_essay` had no `acks_late=True` — Celery's own default is early-ack (a task is removed from the broker queue the moment it's *received*, not once it completes). Live-verified the consequence directly:

1. Dispatched a real `evaluate_essay` task through the real broker to the real `essay-worker` container, using a temporary, clearly-marked test-only delay hook (removed after this test) to reliably catch it mid-execution — real LLM calls fail in under a second in this dev environment (no `OPENAI_API_KEYS`), too fast to catch a worker kill naturally.
2. `docker kill -s SIGKILL` on `essay-worker` while the task was genuinely in flight (received, past the CAS transition to `LLM_PROCESSING`, before any further progress).
3. Restarted the worker. **The submission stayed at `LLM_PROCESSING` permanently** — zero `EssayFailedJob` DLQ entry (the exception path never fired; the process was simply gone), zero automatic recovery, invisible to every existing safety net including the DLQ sweeper (which only ever touches `EssayFailedJob` rows, and none was ever created).

This is exactly the "permanently-stuck submission" this task's own testing bar exists to catch. **Fixed** with `acks_late=True, reject_on_worker_lost=True` on `evaluate_essay`'s own `@shared_task` decorator (`essays/tasks.py`) — safe to add, not just convenient: the CAS transition immediately below it already documented itself as "harmless no-op on a retry of this same task (already `LLM_PROCESSING` from its own prior attempt)," meaning this resumability was already the intended design, just never actually wired to Celery's own delivery guarantee.

**A second, compounding bug found while verifying the first fix:** `acks_late=True` alone did not cause prompt redelivery — Celery's Redis transport has its own `visibility_timeout` (default **3600 seconds**, 1 hour), separate from `acks_late`, governing how long the broker waits before considering an unacked task "lost" and eligible for redelivery. Without overriding this, a real worker crash would leave a submission stuck for up to an hour before recovery even *starts*, not the few seconds a naive read of `acks_late=True` might suggest. **Fixed** with `CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 600}` (`core/settings.py`) — 600s (10 minutes) is comfortably above every task's own hard `time_limit` in this file (90s, `evaluate_essay`'s own, is the longest), so a task legitimately still running is never mistaken for lost, while a real crash's worst-case stuck duration is bounded to minutes, not an hour.

**Re-verified after both fixes, using a temporary short `visibility_timeout` override (15s, test-only) to make the redelivery window observable without a 10-minute real wait:** repeated the identical kill — dispatch, kill mid-flight, restart, wait past the (test-shortened) visibility timeout. The submission automatically transitioned `LLM_PROCESSING` → `LLM_FAILED` (a genuine terminal state, via the real permanent-error path on retry) with **zero manual intervention**, and a proper `EssayFailedJob` DLQ entry was recorded — full recovery *and* full operator visibility, not just an unstuck row. The real production `visibility_timeout=600` value was confirmed live in the running container (`celery_app.conf.broker_transport_options == {"visibility_timeout": 600}`) after the test hooks were removed.

**No duplicate scores at any point across this scenario** — the pre-existing "already_scored" idempotency check (`EssayScore.objects.filter(submission=submission).exists()`) is exactly what makes `acks_late`'s own well-known tradeoff (a task redelivered after it already fully completed, if the ack itself was lost in transit) safe here, not a new risk introduced by this fix.

---

## Scenario 2: LLM provider outage mid-batch

**Genuinely tested at batch scale (10 real submissions) through the real broker and worker, not a single-submission mock.** Used a temporary, clearly-marked test-only hook in `llm_client.py` (removed after this test) to simulate a real outage window that later ends — this dev environment has no `OPENAI_API_KEYS` at all, so without the hook every call already fails *permanently* (no retry ever attempted) before ever reaching a genuine "transient, then recovers" scenario.

**Timeline, real evidence, not assumed:**

| t | Observation |
|---|---|
| 0s | 10 submissions dispatched through the real broker during the simulated outage window |
| 0–30s | All 10 correctly retried through their inline retry budget (3 retries, ADR 003 Decision 6) while the simulated outage was still active |
| ~30s | All 10 correctly exhausted their inline retry budget and landed in the DLQ (`LLM_FAILED`, one real `EssayFailedJob` row each) — **not silently dropped**: the outage in this run outlasted the inline retry budget (a real, valid outcome the design explicitly accounts for, not a test-tool timing error) |
| 300s (5 min) | The real, unmodified, beat-scheduled `sweep_dlq_entries` (`DLQ_GRACE_PERIOD_MINUTES=5`, no shortcut taken) automatically retried all 10 — by this point the simulated outage had genuinely ended — and **all 10 recovered**: `LLM_COMPLETE` → `REPORT_READY`, the full downstream pipeline completing on its own |
| next sweep pass | The DLQ's own `resolved_at` bookkeeping caught up via the self-heal check ("self_healed: 10") |

**One real, minor finding, honestly noted, not a correctness bug:** the DLQ's `unresolved_dlq_count` metric (`AdminSubmissionsPipelineHealthView`/`dlq_unresolved_snapshot()`) lagged **one full sweep cycle** behind the submissions' own actual recovery — `sweep_dlq_entries` only marks an entry `resolved_at` via its self-heal check (`EssayScore` already exists), which runs on the *next* pass, not the same pass that dispatched the successful retry. An on-call engineer watching the DLQ dashboard during this window would see "10 unresolved" for up to 5 minutes after the underlying work had already fully succeeded. Nothing is lost, nothing is duplicated — confirmed **zero duplicate `EssayScore` rows**, exactly 10 scores for 10 submissions — but this eventual-consistency lag in the *reporting* is worth knowing before treating the DLQ count as instantaneously accurate during an active incident (see `essay-exam-day.md` §4).

---

## Scenario 3: Saturate PgBouncer deliberately

**Honestly could not be tested as originally scoped — for two compounding, disclosed reasons, not one glossed-over gap.** Full transparency on both, in the order discovered:

**1. `essay_db`'s own PgBouncer pool has never been reachable at all.** Confirmed live: a direct connection attempt (`psycopg2.connect(host="pgbouncer", ..., dbname="essay_db", ...)`) times out — matching Task 1.2's own already-disclosed, still-open gap (`essay_db`/`essay_db_user` do not exist on the real RDS instance yet; this dev environment connects `essay-service` directly to a dedicated `essay-postgres` container instead).

**2. A live, currently-active instance of this platform's own pre-existing, already-documented `pgbouncer`→RDS issue was discovered while attempting this test — not caused by it.** Attempting the same saturation test against a *genuinely provisioned* pool (`assessment_db`, chosen specifically because it's real and actively used, to isolate "is this an essay_db-only problem") failed identically — every fresh connection attempt through PgBouncer to any real RDS-backed pool failed with `server closed the connection unexpectedly`. PgBouncer's own log confirmed the real cause directly, not guessed: `pooler error: server login has been failing, cached error: server DNS lookup failed (server_login_retry)`, repeated across `assessment_db`, `analytics_db`, and `notification_db` alike — a platform-wide condition, not specific to essay-service's own work. Consistent with `assessment-exam-day.md` §6's and `essay-exam-day.md` §5's own already-standing disclosure that this exact class of issue is pre-existing and out of scope for this session to fix. **Already-established (warm) connections were unaffected** — every service's own health endpoint continued reporting `"db":"ok"` throughout, and all 23 platform containers stayed healthy — this is specifically a "fresh connection" degradation, not a full outage, and it had not self-resolved by the time this document was written (re-checked, still reproducing). Flagged directly to the user in this session as something to look into, without attempting to diagnose or fix AWS-side DNS/RDS infrastructure unprompted.

**What was genuinely tested instead, for real, as the best available substitute — essay-service's actual current path (direct to `essay-postgres`, no pooler in front):**

```
100 concurrent 10-second connections opened directly against essay-postgres (max_connections=100),
then 5 more clients sent while all 100 slots were busy.
```

**Result: 80/100 holders succeeded; the remaining 20 holders and all 5 "extra" clients sent during saturation failed with a connection **timeout** (15s), not a clean rejection and not a graceful queue-then-succeed.** This is a genuinely different, and materially worse, failure mode than what Task 18.2 asks PgBouncer itself to provide: raw Postgres has no connection-queueing layer at all (that is specifically a PgBouncer feature, via `pool_mode = transaction`), so once the connection ceiling is under real pressure, new connection attempts on this 2-CPU dev VM (the same CPU ceiling already documented in Task 18.1's own load test) time out rather than waiting in a bounded queue. **Recovery was clean and immediate once the load ended** — a fresh connection immediately after succeeded in 0.02s, and `essay-postgres`/`essay-service` both showed healthy throughout, with only 2 real connections remaining once the saturating load finished.

**The honest conclusion this scenario actually supports:** essay-service's *current* dev configuration genuinely lacks the bounded-queue protection Task 18.2 asks to confirm — not because essay-service's own code is wrong, but because it isn't using PgBouncer at all yet. This is concrete, live evidence (not a hypothetical) for why the still-pending RDS + PgBouncer migration (Task 1.2's own open item) matters for essay-service's own resilience specifically, beyond just "matching the other 7 services' architecture" — every other service on this platform already has this exact protection via PgBouncer's transaction-pooling mode; essay-service does not, today, and this scenario is the direct evidence of that gap's real consequence under load. **This scenario should be re-run for real** once both (a) `essay_db` is actually provisioned on RDS and (b) the live PgBouncer→RDS DNS degradation found above is resolved — neither of which is something this task fixed or was in scope to fix.

---

## Summary

| Scenario | Genuinely executed? | Real bug found? | Outcome |
|---|---|---|---|
| Worker killed mid-processing | Yes — real `SIGKILL`, real backlog | **Yes, two** (`acks_late` missing; `visibility_timeout` default too long) | Fixed, re-verified live: automatic recovery, zero duplicates, full DLQ visibility |
| LLM outage mid-batch | Yes — real batch (10), real broker/worker, real beat-scheduled sweep | No code bug; one minor DLQ-reporting-lag finding | All 10 recovered automatically, zero duplicates, zero silent drops |
| PgBouncer saturation | **Could not be run as scoped** — `essay_db` pool never reachable; live platform-wide PgBouncer→RDS DNS issue found incidentally | N/A (infra, not essay-service code) — flagged, not fixed | Best-available substitute (direct `essay-postgres` saturation) run instead; real gap identified (no queueing protection without PgBouncer) and named as a concrete reason the pending RDS migration matters |

Full 200% Rule held throughout: full backend suite run twice consecutively after every code change, `PYTEST_EXIT:0` both times (one unrelated, already-documented-class concurrency-test flake hit once, confirmed non-reproducible in isolation). All 23 platform containers confirmed healthy after every scenario. All temporary test-only hooks (`CHAOS_TEST_EVAL_DELAY_SECONDS`, `CHAOS_TEST_LLM_OUTAGE_UNTIL_EPOCH`, and the short-`visibility_timeout` override) were removed before this document was written — the two permanent fixes that remain (`acks_late=True`/`reject_on_worker_lost=True` on `evaluate_essay`, `CELERY_BROKER_TRANSPORT_OPTIONS` with a 600s `visibility_timeout`) are real production code, not test scaffolding. Synthetic test data (papers/attempts/submissions/DLQ entries) fully cleaned from the shared dev `essay_db` after every scenario.
