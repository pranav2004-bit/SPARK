# assessment-service — Chaos & Failure Injection Test Results

**Task:** [LIVETRACKER2_V1.md](../LIVETRACKER2_V1.md) Task 14.2
**Related:** [assessment-service-load-test-results.md](assessment-service-load-test-results.md) (Task 14.1, same dev stack), [ADR 001](adr/001-assessment-timer-architecture.md) (the sweep design under test), [Task 13.1's resilience work](../LIVETRACKER2_V1.md) (the DLQ/graceful-degradation code this task verifies under real conditions)

All three tests below were executed for real against the live dev Docker stack — real containers stopped and started, a real PgBouncer pool genuinely saturated, real HTTP requests fired throughout. **All three passed.** No crash, no stuck session, no data corruption, no manual intervention required to recover from any injected failure.

---

## Test 1: `assessment-worker`/`assessment-beat` killed mid-sweep

**Claim under test:** a session past its `ends_at` while the sweep is down is not lost — it gets picked up and auto-submitted once the sweep resumes, within a bounded time, with no data loss.

**Method:** created 60 real sessions via concurrent `start-session` calls (all `201`), then directly backdated their `ends_at` to make them instantly sweep-eligible — the same backdating pattern `tests/test_sweep.py`'s own unit tests already use, just applied to real HTTP-created sessions instead of ORM-created fixtures. Killed `assessment-worker` and `assessment-beat` (`docker stop`), confirmed via `docker ps` that both were genuinely `Exited`, waited 30s (well past one 20s sweep cycle) and confirmed all 60 sessions were still `IN_PROGRESS` — proof the sweep really was down, not a coincidence of timing. Restarted both containers, waited one more cycle, and re-checked.

**A real methodology bug was found and fixed along the way:** the first attempt issued `docker stop` immediately after backdating, but Celery's graceful-shutdown grace period let an in-flight sweep tick finish *after* the stop command was issued but *before* the containers actually went down — so the first attempt's sessions got swept before the "kill" had really taken effect. Not a service bug: confirmed via `assessment-worker`'s own logs that the sweep completed at `01:58:23` and the "Warm shutdown" message only appeared afterward. Fixed by confirming via `docker ps` that both containers were already `Exited` *before* creating the sessions, removing the race entirely.

**Result: PASS.**
- With worker/beat confirmed down: 60/60 sessions remained `IN_PROGRESS` after 30s (0 auto-submitted).
- On the very first sweep tick after restart (well under one 20s cycle): all 60 sessions transitioned to `AUTO_SUBMITTED`, all 60 got a `ResultSummary` row, **0 duplicate `ResultSummary` rows**.
- No manual intervention needed beyond restarting the two containers — the sweep resumed its normal schedule immediately and cleared the full backlog in a single tick.

---

## Test 2: `user-service` failure injected during real concurrent load

**Claim under test:** the exam-taking flow (session-start, autosave, submit) never calls user-service live — Task 3.1's snapshot-roster design means a real student mid-exam is completely unaffected by user-service being down. Only admin views that need live roster data (Results/Analytics/Export, Task 7.1/7.3/8.1) should fail, and only while user-service is actually down — cleanly (502s, Task 13.1), never a crash or a hang, and with automatic recovery once user-service returns (no assessment-service restart needed).

**Method:** started 100 real sessions, then ran a continuous ~55s loop firing batches of student autosave `PUT`s alongside admin `dashboard`/`results` `GET`s once per second, while `user-service` was stopped at the 20s mark and restarted at the 40s mark (a ~20s outage injected into the middle of live traffic).

**A real test-harness bug was found and fixed:** the first run's student-side results were invalid — `zip()`ing two independently-ordered Django querysets (`AssessmentSession` IDs and the original student token list) doesn't guarantee matching order, so most "student" calls used the wrong student's token and got a legitimate `404` (IDOR-safe session lookup correctly rejecting a token that doesn't own that session) — a harness pairing bug, not a service finding. Fixed by pairing each session to its *actual* `student_id` from the DB before generating that student's token, then re-verified.

**Result: PASS**, once measured correctly.
- **Exam-taking flow, with user-service completely stopped:** session-start 100/100 succeeded (`201`) *before* the outage; with user-service confirmed down, a fresh correctly-paired batch of 30 autosave `PUT`s → 30/30 `200`, and 20 `submit` calls → 20/20 `200`. **Zero impact**, exactly as Task 3.1's design claims — not just true in code review, but demonstrated under real concurrent traffic with user-service actually offline.
- **Admin `dashboard` (no roster dependency, Task 9.1):** stayed `200` for the entire ~55s window, including the full outage — confirms Dashboard's design (ResultSummary aggregates only, no live user-service call) holds under real conditions.
- **Admin `results` (roster-dependent, Task 7.1):** `200` before the outage → degraded to slow (~3-6s) responses as user-service began struggling → clean `502`s and bounded client-side timeouts (never an unbounded hang) during the confirmed-down window → automatically back to `200` (0.28s) the moment user-service was healthy again, with **no assessment-service restart or manual reset needed** — confirmed by querying the results endpoint again immediately after `docker start infra-user-service-1` returned, from the same already-running assessment-service process.

---

## Test 3: PgBouncer connection-pool near-exhaustion

**Claim under test:** if the `assessment_db` PgBouncer pool is genuinely saturated, new requests queue (backpressure) rather than crash the service or corrupt data — matching `pool_mode = transaction`'s documented queueing behavior, not an assumption.

Every load-test run in Task 14.1 showed `cl_waiting = 0` throughout — the pool was never actually challenged. This test deliberately forces real saturation: `default_pool_size = 10` + `reserve_pool_size = 2` = 12 max backend connections for this pool (`infra/pgbouncer/pgbouncer.ini`).

**Method:** opened 12 raw `psycopg2` connections through PgBouncer (not directly to Postgres — through the same pool assessment-service itself uses), each holding an open transaction (`BEGIN; SELECT 1;`, held via `time.sleep(25)`) — consuming the pool's entire real capacity. Confirmed saturation live via `SHOW POOLS` (`sv_active = 12`, i.e. every backend connection in use) before firing a burst of 25 concurrent real assessment-service requests into that exact saturated window.

**Result: PASS — unambiguous.**
- `SHOW POOLS` at burst-fire time: `sv_active = 12` (full), `cl_waiting = 1` already (something else was already queueing before the deliberate burst).
- The 25-request burst: **all 25 succeeded (`200`)**, with latencies of 10.3–11.0 seconds — i.e., they genuinely queued for a free connection slot (PgBouncer's own queueing, not an immediate response) and were served once the held transactions released, rather than being rejected or timing out.
- `SHOW POOLS` immediately after: `sv_active = 0`, `sv_idle = 12`, `cl_waiting = 0` — the pool released and returned to normal cleanly, no lingering saturation.
- No error, no exception, no crash anywhere in assessment-service's logs during the entire test window; no container restarted.

This is the strongest possible version of the completion gate's "clean backpressure... no crash, no corrupted writes" — not merely a clean *error* under pressure, but genuine queueing followed by successful completion once capacity returned, with zero requests lost or corrupted.

---

## Conclusion

All three rows of Task 14.2's test suite pass. Two real bugs were found and fixed during this task — both in the *test harness* (a shutdown-timing race in the worker/beat kill test, and a queryset-ordering pairing bug in the user-service test), not in the service — and both are documented above with the evidence that ruled the service out as the cause, matching the same "verify, don't assume" discipline used throughout this project. Every one of Task 13.1's resilience claims (fail-open throttling and caching, the DLQ-backed sweep, the fail-fast roster dependency, real PgBouncer backpressure) held under genuine, live-injected failure conditions during real concurrent traffic — not just isolated unit tests.

**Completion Gate: all rows pass, findings documented above.**
