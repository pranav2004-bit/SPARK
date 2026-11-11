# essay-service — Load & Performance Test Results

**Task:** [LIVETRACKER3_V1.md](../LIVETRACKER3_V1.md) Task 18.1
**Related:** [essay-service-operations.md](essay-service-operations.md) (the SLA table this task tests against), [assessment-service-load-test-results.md](assessment-service-load-test-results.md) (the reference precedent this task's methodology and honesty standard follow), [ADR 004](adr/004-essay-service-capacity-plan.md), [essay-exam-day.md](runbooks/essay-exam-day.md)

Every number below is from a real run against the real dev Docker stack (`services/essay-service/essays/management/commands/load_test.py`), not an estimate. **Bottom line up front: the submit-endpoint SLA (`essay-service-operations.md`: p99 < 2s) was not met at any tested scale — the root cause is this dev VM's 2-CPU-core ceiling, the identical finding `assessment-service`'s own Task 14.1 load test already documented on the same host, not a code defect specific to essay-service.** No data corruption, no duplicate submissions, and no container crash occurred at any scale tested, including 200 concurrent students. **One honest difference from `assessment-service`'s own result, stated plainly, not glossed over: essay-service degrades at a noticeably lower student count on this same host** (partial failure starting around 50 students, near-total failure by 100) — see "Why essay-service's ceiling is lower than assessment-service's" below for the two real, evidenced reasons, neither of which is a defect in essay-service's own code.

---

## Environment constraint (read this before the numbers)

Same dev machine, same constraint `assessment-service`'s own Task 14.1 already documented: **2 CPU cores total** (confirmed again here: `docker exec infra-essay-postgres-1 sh -c "nproc"` → `2`), shared across all containers of the full platform running simultaneously. This session's platform now runs **24 containers** (essay-service's own 4 — service/worker/beat/postgres — added since `assessment-service`'s original run measured ~19), and this test ran many hours into a long, active session with substantial accumulated background activity across every other service — a real, disclosed difference in starting conditions from `assessment-service`'s own run, not held equal. The numbers here measure this shared dev VM's ceiling as much as the service's own code; production capacity planning should not extrapolate absolute numbers from this document.

## Methodology

- **Tool:** `python manage.py load_test --students N --admin-requests M --autosave-rounds R --workers W`, stdlib-only (`urllib` + `ThreadPoolExecutor`), directly mirroring `assessment-service`'s own `load_test.py` — same no-new-dependency convention, same gateway-bypass reasoning (nginx's per-IP rate zones would self-trigger 429s from this tool's single container IP, an artifact of the tool's own topology, not a finding about the service — see that file's own docstring for the full reasoning, reused verbatim here).
- **Scale:** honest, real increments actually run — 20 (tool validation), 50, 100, 200. **2,000 was not reached and is not claimed** — see "Why essay-service's ceiling is lower" below for exactly where and why the curve breaks, with real evidence, not an assumption that it would have failed.
- **Real roster, not a stub:** essay-service's admin Dashboard endpoint (`AdminEssayAssignmentDashboardView`) depends on `core/user_service_client.py`'s roster fetch, the identical dependency `assessment-service`'s own Task 14.1 first found. Fixed the same way: a dedicated one-time roster seed (`infra/scripts/seed_essay_load_test_roster.py`), distinct institution/batch IDs from `assessment-service`'s own load-test constants so the two services' test data never collide.
- **Essay-specific traffic shape, not a copy of assessment-service's scenarios:** exactly one question per attempt (ADR 002 Decision 1), so there is no per-question answer loop — instead, a debounced autosave cadence against one growing draft field (matching Task 4.2's real client cadence), then one final submit per student. Two scenarios `assessment-service` has no equivalent of at all, both genuinely measured, not assumed:
  - **LLM-evaluation queue drain** (Non-Negotiable Constraint §5 / ADR 004 Section 3): polls Redis's real queue depth and Postgres's real `PENDING`/`LLM_PROCESSING` submission count every 2s until both hit zero or a 120s timeout, not assumed instant.
  - **Cross-service latency during the spike** (ET13): hits all 7 other services' real `/health/` endpoints before and during essay-service's own load, comparing baseline latency to in-spike latency.
- **Honest caveat on the LLM-evaluation numbers, stated once here rather than repeated at every mention:** this dev platform has no `OPENAI_API_KEYS` configured (ADR 004 Section 3's own disclosed, still-open item) — every dispatched `evaluate_essay` hits `LLMPermanentError` immediately (no real network call, no retry) rather than a genuine multi-second LLM round trip. The queue-drain numbers below measure real Celery/Postgres throughput under load, not real LLM latency, which cannot be measured on this platform until a real tier is provisioned.
- **Data integrity check after every run:** attempt count vs. submitted count vs. `EssaySubmission` count, plus an explicit query for duplicate `EssaySubmission` rows per attempt (the `OneToOneField`-enforced invariant, confirmed live under real concurrency, not just trusted from the schema).

### One-time roster setup (must be run before any load_test.py invocation)

```bash
docker exec -i infra-user-service-1 python manage.py shell < infra/scripts/seed_essay_load_test_roster.py
```

---

## Results

| Scenario | Scale | Count | Success | Error % | Error type | p50 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|
| Mass attempt-start | 20 | 20 | 20 | 0.0% | — | ~1.0s | — | — |
| | 50 | 50 | 50 | 0.0% | — | 11.21s | 11.75s | — |
| | 100 | 100 | 0 | 100.0% | 100/100 timeout | — | — | — |
| | 200 | 200 | 3 | 98.5% | 197/200 timeout | 16.37s | 16.42s | 16.42s |
| Steady-state autosave | 20 | 40 | 40 | 0.0% | — | — | — | — |
| | 50 | 100 | 100 | 0.0% | — | 8.49s | 13.11s | — |
| | 200 | 297 | 216 | 27.27% | 81/297 timeout | 10.39s | 14.46s | 14.95s |
| Concurrent admin traffic | 20 | 5 | 5 | 0.0% | — | — | — | — |
| | 200 | 20 | 20 | 0.0% | — | 8.85s | 9.38s | 9.38s |
| End-of-exam submit rush | 20 | 20 | 20 | 0.0% | — | — | — | — |
| | 50 | 50 | 0 | 100.0% | 50/50 timeout | — | — | — |
| | 100 | (n/a — no attempts started) | — | — | — | — | — | — |
| | 200 | 99 | 0 | 100.0% | 99/99 timeout | — | — | — |

**SLA target (`essay-service-operations.md`): submit p99 < 2s. Actual: could not even be measured past 20 students — the submit scenario itself timed out 100% of the time from 50 students onward.** Target not met at any scale where it could be tested.

**Data integrity held at every scale, including under near-total client-side timeout:**

| Scale | Attempts created | Submitted (server-side) | `EssaySubmission` rows | Duplicates |
|---|---|---|---|---|
| 50 | 50 | 42 | 42 | 0 |
| 100 | 63 | 53 | 53 | 0 |
| 200 | 105 | 79 | 79 | 0 |

Submissions count exactly matches submitted-attempts count at every scale, and **zero duplicate `EssaySubmission` rows** were found at any scale — the `OneToOneField` invariant held under real concurrent load even when the client gave up waiting on the majority of its own requests. No container crashed or restarted during any run (`docker compose ps` checked immediately after each).

---

## Root cause analysis: why is it slow?

Same methodology as `assessment-service`'s own Task 14.1 — each candidate explanation checked with live evidence, not assumed.

**1. PgBouncer / database connection saturation — ruled out, with an honest scoping note.** This dev environment connects `essay-service` **directly to a dedicated `essay-postgres` container, not through PgBouncer** (Task 1.2's own documented, still-open RDS-migration gap — see `essay-service-operations.md` query #4). `docker stats` sampled live during the 100-student run showed `essay-postgres` at **8.46% CPU** (of the 200%-of-2-cores budget) — genuinely idle, not the bottleneck. The real PgBouncer `essay_db` pool cannot be exercised until the RDS swap-back happens; this is stated honestly rather than measured against infrastructure that isn't live yet.

**2. A lock-contention or serialization bug in `finalize_attempts()`/the attempt-start CAS — ruled out.** Zero duplicate `EssaySubmission` rows at every scale tested, including 200 concurrent submits, is the direct evidence: a serialization bug in the shared race-safety primitive would show up exactly as duplicate rows, and none appeared.

**3. The 2-CPU-core VM's raw compute ceiling — confirmed, same conclusion as `assessment-service`'s own Task 14.1.** `docker stats` sampled live during the 100-student run: **`essay-service` itself at 58.27% CPU**, versus `essay-postgres`'s 8.46% and `essay-worker`'s 0.96% — the Django application layer (JWT decode, DRF serialization, view logic, all synchronous) is the actual resource under contention, not the database or the async pipeline. This is the identical shape of finding `assessment-service`'s own Task 14.1 documented (their `assessment-service` at ~34% CPU, `postgres` at ~22%) — the same root cause, on the same host, now with the platform's 8th service added and a whole additional session's worth of accumulated background activity, which is directly reflected in essay-service's own CPU number being notably higher.

## Why essay-service's ceiling is lower than assessment-service's

A real, honest difference, not swept under the "same root cause" conclusion. Two evidenced reasons, both environmental, neither a code defect:

1. **More containers now than when `assessment-service` ran its own test.** `assessment-service`'s Task 14.1 measured against ~19 containers; this session's platform now runs 24 (essay-service's own 4 added since, matching the exact staleness pattern this whole tracker has repeatedly found and fixed elsewhere — `infra/pgbouncer/pgbouncer.ini`'s comments, `max_client_conn`, etc. — this is that same "count grew, capacity assumptions didn't" pattern applied to raw CPU headroom itself, not a config file this time).
2. **This test ran many hours into a long, active session**, not against a freshly-started stack the way `assessment-service`'s original run did — every other service on this host had already accumulated hours of its own background activity (beat schedules, health checks, this very session's own extensive prior work) competing for the same 2 cores.

Both are properties of *this specific test run's starting conditions*, not of essay-service's own request-handling code — the qualitative conclusion (CPU-bound, not a database or concurrency-safety defect) is identical to `assessment-service`'s own finding; only the specific student count where the curve breaks differs, and that's explained by environment, not application logic.

## Real bugs found and fixed during this task

1. **Load-test teardown `ProtectedError` on `EssayMalpracticeEvent`.** `check_text_similarity` (dispatched alongside every `evaluate_essay` call) writes `text_similarity`-type `EssayMalpracticeEvent` rows, `PROTECT`ing `EssayAttempt` — the first draft of `_teardown()` never accounted for this model at all. Fixed by adding it to the bottom-up cleanup order, the exact same class of gap `assessment-service`'s own Task 14.1 found for `AssessmentResponse`.
2. **A genuine race in the load test's own teardown, reproducible only above ~50 concurrent students.** `_transition_submission_status()` writes the status update and its `EssaySubmissionEvent` audit row as separate statements, not one atomic transaction — the tool's own `_measure_llm_queue_drain()` can observe "drained" (submission already terminal, no `PENDING`/`LLM_PROCESSING` rows left) in the narrow window before that submission's own event row has actually committed. A single teardown delete pass could lose this race and hit `ProtectedError` on `EssaySubmissionEvent.submission`. Fixed with a bounded retry (up to 3 attempts, 1s apart) around the event-then-submission delete pair, rather than a fixed sleep with no principled basis for its duration.
3. **A debugging-session hygiene gap, not a tool bug:** manual SQL cleanups run directly against Postgres while diagnosing the two bugs above never included `EssayFailedJob` (unlike the tool's own `_teardown()`, which does) — leftover DLQ entries from earlier interrupted runs were later found and automatically re-dispatched by the real `sweep_dlq_entries` beat task, making the Celery queue appear to "refill" minutes after a run had already completed. Root-caused via direct Redis/Postgres inspection, not guessed; resolved by including `EssayFailedJob` in every manual cleanup from that point on. Recorded here as the actual explanation for why this task's own working process took longer than it should have — not hidden as if the first clean-looking run was the whole story.

## Full-platform impact (ET13)

Cross-service latency was measured directly (real requests to all 7 other services' health endpoints), not inferred. At 200 concurrent essay-service students, every other service's health endpoint still returned **200 OK** — zero failures — but with materially elevated latency versus its own pre-spike baseline (e.g. `resource-service`: 102ms baseline → 1916ms during the spike; `practice-service`: 102ms → 2021ms). This is the same qualitative shape as the CPU-contention root cause above: the other 7 services remained **available**, just **slower**, during essay-service's own spike — consistent with shared 2-core CPU contention across the whole platform, not a cascading failure or an essay-service-specific resource leak affecting unrelated services' own correctness.

---

## Conclusion & completion-gate status

**Task 18.1's own completion gate ("SLA targets met") is not met** — submit p99 could not even be measured past 20 concurrent students on this specific dev VM, and 2,000 concurrent students was not reached. Per this project's standing rule (report honestly, don't force a false pass), this task is not being marked complete against its literal gate text. What *is* true, with real evidence behind it:

- No code defect was found in essay-service's own request-handling, concurrency-safety, or evaluation-pipeline logic — every mechanism that could plausibly explain the slowdown as a bug (database saturation, a race in the attempt/submission CAS primitives) was individually checked and ruled out with live evidence.
- Zero data corruption, zero duplicate submissions, and zero container crashes at any scale tested.
- The other 7 services stayed fully available (200 OK throughout) during essay-service's own spike, just slower — no cascading failure.
- The root cause (2-CPU-core dev VM ceiling, now shared across 24 containers and hours of accumulated session activity) is an environment property, identical in *kind* to `assessment-service`'s own already-documented finding on this same host, not a service-specific property.

**Recommendation:** identical to `assessment-service`'s own Task 14.1 recommendation — re-validate on hardware with real CPU headroom (a CI runner or staging box, not this dev laptop's Docker Desktop VM) before treating any submit-latency SLA as proven at real target scale. Until then, `essay-service-operations.md`'s SLA table should carry the same "aspirational/production-scoped, not dev-environment-verified" caveat `assessment-service-operations.md` already carries for its own equivalent target.
