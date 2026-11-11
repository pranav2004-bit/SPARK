# ADR 002 — Essay Service: Boundary, Data Ownership, Timer Reuse & Anti-Cheat Scoping

**Status:** Accepted
**Date:** 2026-09-19
**Task:** [LIVETRACKER3_V1.md](../../LIVETRACKER3_V1.md) Tasks 0.1, 0.3, 1.4
**Deciders:** essay-service design (Phase 0)

## Context

`essay-service` is the platform's 8th microservice: LLM-evaluated essay-writing assessments. Structurally it is one admin-defined question per "set" (a prompt variant), assigned to a batch/department, taken once by each student under a server-enforced deadline, and scored asynchronously by an LLM against an admin-authored rubric. This is deliberately a **narrower** shape than `assessment-service` (one question type, one domain, no MCQ/audio/multi-component structure) and a **narrower** shape than the CLAP reference platform this project's design patterns were audited against (CLAP scores five domains per test; this service scores exactly one).

Three architectural questions must be settled before any model or endpoint exists, because every later phase depends on the answers:

1. What does `essay-service` own outright, and what must it only ever read from elsewhere?
2. Is exam timing re-derived from scratch, or reused from `assessment-service`'s already-built, already-load-tested design?
3. What is the actual, scale-aware shape of the plagiarism/text-similarity check, given CLAP's reference implementation was correctly documented as O(N) per trigger but is O(N²) in aggregate across a full cohort?

## Decision 1 — Service Boundary & Data Ownership

`essay-service` owns exactly one new database, `essay_db`, on the existing shared RDS instance, behind the existing PgBouncer (its own pool, sized in ADR 004). It owns:

- `EssayPaper`, `EssaySet`, `EssayQuestion` (Question Bank)
- `EssayAssignment` (batch/department scope, timer configuration, lifecycle state)
- **`EssayStudentSetAllocation`** (found missing during this ADR's Phase-3 self-audit, 2026-09-20 — the same class of omission as `EssayAttempt` below, caught the same way: this section named the set-distribution requirement without ever naming the model that stores its result). The per-student, per-assignment record of which `EssaySet` a student was allocated to — the direct analog of `assessment-service`'s `StudentSetAllocation`. Kept as its own model, separate from `EssayAttempt`, for the same reason `assessment-service` keeps them separate: allocation happens once for the whole roster at assignment-creation time (a batch operation, before any student has acted), while an attempt is created lazily per student action. Folding allocation into `EssayAttempt` would lose the ability to snapshot the whole roster's set assignments up front.
- **`EssayAttempt`** (found missing from this ADR's first draft during its own self-audit — a real gap, not a stylistic one) — the per-student, per-assignment record tracking `started_at`/`ends_at`/attempt status (`NOT_STARTED`/`IN_PROGRESS`/`SUBMITTED`/`AUTO_SUBMITTED`/`EXPIRED_UNSTARTED`, Decision 2 below). This is the direct analog of `assessment-service`'s `AssessmentSession` and CLAP's `StudentClapAssignment` — a **separate model from `EssaySubmission`**, exactly as both reference systems keep attempt/timer state and pipeline/scoring state as two distinct models rather than one. Decision 2's state machines were describing this model without ever naming it; that omission is fixed here.
- `EssaySubmission`, `EssayScore` (the one-domain equivalents of CLAP's `AssessmentSubmission`/`SubmissionScore` — pipeline/LLM-scoring state, created once an `EssayAttempt` reaches `SUBMITTED`/`AUTO_SUBMITTED`, never before)
- `EssayMalpracticeEvent`, foreign-keyed to `EssayAttempt` (mirroring `assessment-service`'s `ActivityLog`→`AssessmentSession` and CLAP's `MalpracticeEvent`→`StudentClapAssignment` relationships — malpractice is an attempt-time concern, not a post-submission pipeline concern, so it belongs on the attempt record, not the submission record)
- `EssayFailedJob` (reusing `assessment-service`'s `FailedJob`/`DeadLetteringTask` DLQ shape directly, per the tracker's Task 5.3 — **citation corrected during this ADR's second self-audit pass**: this reuse mandate is a task-level design decision, not one of the tracker's 9 numbered Non-Negotiable Constraints, which this ADR's first draft incorrectly cited as "§1")

It does **not** own, and never gains a foreign key into, student/batch/institution/department records. Those are read at request time from `user-service`'s API or directly off the request's own JWT claims (`institution_id`, `student_id`, `department`, `batch_id`) — identical to `practice-service` and `assessment-service`'s existing convention. This is not a new pattern; it is the same isolation rule every service on this platform already follows, restated here so `essay-service`'s own code review has an explicit citation rather than an assumed convention.

**Consequence:** a student roster or department list is never queried from `essay_db` directly. Any admin screen needing "which students are in batch X" makes a real API call to `user-service`, exactly as `assessment-service` already does.

## Decision 2 — Timer Enforcement: Reuse ADR 001, Simplified for One Question

`essay-service` adopts [ADR 001](001-assessment-timer-architecture.md)'s server-authoritative timing model **by reference, not by re-derivation**:

- `EssayAttempt.ends_at` is computed **once**, server-side, at the moment the student starts (`now() + duration_minutes`, or `min(that, EssayAssignment.global_deadline)` if a global deadline is also configured) — never recomputed on resume, never trusted from the client.
- Every mutating student call (autosave, submit) revalidates `now() < ends_at` server-side on every request, exactly as ADR 001's decision point 2 specifies. A client-supplied timestamp is never read.
- A Celery beat sweep (same 15–30s cadence as `assessment-service`'s) transitions any `EssayAttempt` where `now() >= ends_at AND status = 'IN_PROGRESS'` to `AUTO_SUBMITTED`, via the same conditional `UPDATE ... WHERE status = <current>` pattern — race-safe against a concurrent manual submit for the identical reason ADR 001's decision point 3 documents (whichever write lands second is a no-op).
- No WebSocket-per-student. Same reasoning as ADR 001's decision point 5, unchanged.

**What's genuinely simpler here, and why that simplicity is deliberate, not an oversight:** `assessment-service` has a two-layer timer (`BatchAssignment` global window + per-`AssessmentSession` exam duration) because a single sitting spans many questions across many timed components. `essay-service` has exactly one question per assignment. There is no "per-component" sub-timer to track, no `ComponentAttempt`-equivalent model, and — critically — **no chord/group synchronization need in the eventual scoring pipeline**, because there is only one thing to finish before scoring can start, not several running in parallel. Do not port `assessment-service`'s two-layer timer model or CLAP's per-component `ComponentAttempt` model into this service; both exist to solve a multi-part-exam problem this service does not have.

### State Machines

**`EssayAssignment.status`** (mirrors `assessment-service`'s `BatchAssignment`, unchanged):

```
SCHEDULED → LIVE → CLOSED
```

- `SCHEDULED → LIVE`: admin's explicit `start/` action only — never automatic on a schedule passing, matching the same manual-gating principle ADR 001 established for `assessment-service` (student access is gated on a deliberate admin action, not a schedule alone) — adopted here for consistency, not because it has been separately verified as a platform-wide rule beyond that one service.
- `LIVE → CLOSED`: the beat sweep (`global_deadline` passed) or an admin's explicit `close/` action, which cascades to auto-submit any `IN_PROGRESS` student attempts.
- `CLOSED` is terminal. A second attempt is a new `EssayAssignment` unless retests are explicitly in scope (see Decision 3).

**Per-student attempt status** (the `essay-service` equivalent of `AssessmentSession.status`):

```
NOT_STARTED → IN_PROGRESS → SUBMITTED
                           → AUTO_SUBMITTED   (sweep, or admin close/ cascade)
            → EXPIRED_UNSTARTED
```

Identical shape and identical reasoning to ADR 001 §"Session & Assignment State Machines" — reproduced here rather than only cross-referenced because this is the state machine `essay-service`'s own migrations and beat task implement directly, not `assessment-service`'s.

**`EssaySubmission.status`** (the CLAP-derived pipeline state machine, reduced to one LLM domain):

```
PENDING → LLM_PROCESSING → LLM_COMPLETE → REPORT_READY
                          → LLM_FAILED  (permanent failure → DLQ; recoverable via
                                          admin retrigger, automatic DLQ sweep retry,
                                          or a manual score override — see ADR 003)
```

CLAP's own state machine has additional stages (`RULES_COMPLETE`, `REPORT_GENERATING`, `EMAIL_SENDING`) that exist because CLAP scores multiple domains (some rule-based, some LLM-based) and generates a combined multi-domain PDF. `essay-service` has one domain and no rule-based component, so those intermediate stages collapse — there is nothing for a `RULES_COMPLETE` stage to mean here. Retain `REPORT_READY` as a distinct terminal-ish stage (rather than conflating it with `LLM_COMPLETE`) because Phase 11's report generation/regeneration and Phase 11.2's email delivery tracking are still separate concerns from evaluation itself, exactly as they are in CLAP, and collapsing them would lose the ability to regenerate a report independently of re-scoring (a real, verified CLAP capability — see `report_management.py::regenerate_report`).

A `SUPERSEDED_<original_status>` prefix convention (verified from CLAP's `grant_retest`) is adopted **only if** Decision 3 puts retests in scope for V1.

## Decision 3 — Retest Support: Deferred Past V1

CLAP's `grant_retest` mechanism (verified in full) is well-designed: mandatory admin reason (≤500 chars), refuses mid-attempt, atomically wipes prior responses/attempts, marks prior submissions `SUPERSEDED_` rather than hard-deleting (audit trail preserved), increments an `attempt_number` so idempotency keys never collide across attempts.

**Decision: retest support is explicitly out of scope for the MVP/Pilot-Batch stages of this tracker's Phase 20 lifecycle**, revisited at the Beta gate once real usage shows whether it's actually needed. Rationale: a single-question essay assessment is cheap to re-issue as a *new* `EssayAssignment` to one student manually (an admin action that already exists via normal assignment creation) without needing the full wipe/supersede machinery CLAP built for its five-domain, much-longer-duration test — building the general retest mechanism now, before any real usage has confirmed it's needed, is exactly the over-engineering this project's own standing instructions warn against. If Beta usage shows this manual-reissue workaround is a genuine operational pain point, CLAP's `grant_retest` design (already fully documented above and in the tracker) is the adopted reference for building it then, not a redesign from zero.

## Decision 4 — Text-Similarity / Plagiarism Check Scope (Task 0.3)

CLAP's `check_text_similarity` (fully verified) is, per its own accurate docstring, **O(N) per individual trigger** — one newly-completed student's essay compared against N already-completed peers via `difflib.SequenceMatcher`, flagging ratio ≥ 0.85. The O(N²) concern is real only in **aggregate across a full cohort finishing the same assignment**: student 2 checks against 1 prior, student 3 against 2, … student N against N−1, summing to N(N−1)/2 total comparisons spread across however long the exam window actually runs (not N² work happening at one instant — a 2,000-student cohort does not all finish in the same second).

**Decisions:**

1. **Scope every comparison to one `EssayAssignment` + the same assigned set/prompt variant.** This alone bounds N to one assignment's cohort (realistically tens to low hundreds of students per batch/department, not the platform's entire historical student population) rather than CLAP's platform-wide, all-tests-ever comparison scope.
2. **No pre-filter (MinHash/shingling) for V1.** At the scoped cohort sizes this service actually expects (a department/batch, not a 2,000-student platform-wide cohort in one assignment), plain pairwise `difflib` against a bounded N is genuinely fast enough — adding a pre-filtering layer before any real measurement has shown pairwise comparison is too slow would be solving a problem that doesn't yet exist. Task 5.4's own testing checklist requires a real timing measurement at the assumed batch size before this decision is treated as final; if that measurement shows a problem, revisit this decision with real numbers, not in advance of them.
3. **Similarity threshold: adopt CLAP's 0.85 as the starting value**, but make it a configurable setting rather than a hardcoded literal (CLAP hardcodes it) — a longer essay naturally has more room for two genuinely-different answers to still score moderately similar on a whole-text ratio than a short one does, and this platform's actual word-limit configuration (admin-configurable per Question Bank Task 2.1) may differ enough from CLAP's assumptions that the right threshold should be tunable without a code change once real data exists.

   **Amendment (2026-09-24), exactly the revisit this decision's own text anticipated:** two things changed. First, a real, serious bug was found and fixed — `difflib.SequenceMatcher` was being called with Python's own `autojunk=True` default, which treats frequently-occurring characters as noise for any text over 200 chars (true of nearly every real essay). Confirmed live: two essays sharing 3 of 5 sentences verbatim scored 80% with autojunk correctly disabled, but only 1.1% with the buggy default — the checker was effectively non-functional for anything short of a complete, word-for-word copy. Fixed with `autojunk=False`. Second, since 0.85 was calibrated against ratios the bug itself produced (not real ones), it was re-derived empirically against the corrected calculation — tested at two essay lengths and two topics, honest independent writing lands ~20-30%, a genuine partial copy lands 47-62%. **`ESSAY_TEXT_SIMILARITY_THRESHOLD` changed to 0.60.** Still explicitly not a permanently-settled number (same "tunable, not final" spirit as this decision's own original text) — based on synthetic test essays, not real student submissions, and doesn't yet account for narrow/factual question types where honest answers may converge more (this decision's own point about essay length/word-limit affecting the right number applies equally to question narrowness, untested here). Full reasoning and live-measured numbers in `LIVETRACKER3_V1.md`'s own dated entry and `PRODUCTION_CHECKLIST.md`.
4. **Minimum-length floor before comparing at all:** reuse CLAP's implicit floor (responses under ~50 characters are excluded, since short overlapping phrases produce false-positive high-ratio matches on trivial content) — make this a named setting, not a magic number buried in the comparison function.

## Decision 5 — Storage: No S3, No ClamAV (Task 1.4)

**Gap found and closed during this ADR's final audit pass:** this document's own header has listed Task 1.4 among the tasks it settles since its first draft, but the decision itself was never actually written down until now.

**Decision: `essay-service` wires no file storage of any kind.** Every submission is plain text (the student's typed response) — there is no audio, image, or document upload anywhere in this service's scope (unlike CLAP, which stores audio recordings and admin-uploaded audio clips via S3, and unlike `assessment-service`/`resource-service`, which store question images/materials via the platform's real S3 bucket + ClamAV scan pipeline). Wiring S3 credentials, a bucket policy, or a ClamAV dependency into a service that will never receive a byte of binary content is exactly the over-engineering this tracker's own instructions warn against — infrastructure provisioned for a capability that does not exist.

**Revisit trigger:** if a future phase adds a genuinely new capability requiring file upload (e.g. an admin attaching a reference image to a question prompt), that is a new, explicit ADR decision at that time — not something to pre-provision speculatively now.

## Consequences

- **Positive:** Zero new timing-enforcement design risk — ADR 001's model has already been genuinely load-tested (`LIVETRACKER2_V1.md` Phase 14, real concurrent-submit conditions up to 600 students on the dev environment available at the time) and its race-safety primitive is already proven correct under that real concurrency, including surviving a real chaos test (worker/beat killed mid-sweep). **Correction, not overclaimed here:** that same load test honestly found the submission-endpoint p99 latency SLA was *not* met at 200+ concurrent on that dev hardware, root-caused to the test environment's 2-CPU-core ceiling rather than the code — reused correctness is proven, reused performance-at-target-scale is not yet proven on production-equivalent hardware for either service. This service inherits that same open item, not a clean bill of health.
- **Negative / accepted tradeoff:** Deferring retest support means an admin who needs to re-issue an essay to one student does so via a normal new assignment, which does not preserve the "attempt 1 vs. attempt 2" grouping CLAP's model provides. Accepted for V1 given the low expected frequency of this need for a single-question format; revisit at the Beta gate (Task 20.2) with real usage data.
- **Revisit trigger:** If Task 5.4's real timing measurement at actual batch sizes shows the scoped pairwise comparison is not fast enough, add a pre-filter stage then — not speculatively now.

**Second amendment (2026-10-04) — algorithm replaced, threshold re-derived.** The whole-text `difflib.SequenceMatcher` comparison described above was found to be unusable in production. Disabling `autojunk` fixed the accuracy bug but made each comparison about 100x slower on realistic essays (about 600ms each; roughly an hour per 2,000 peers), and the `quick_ratio()` pre-filter did not help because every pair passed it. The sequence comparison was also order-sensitive, scoring a fully copied but paragraph-reordered essay at 33-42%. **`check_text_similarity` now uses word 5-gram containment** (the share of the student's 5-word runs that also appear in a peer's essay), which is order-independent and runs in about 0.02ms per comparison at 2,000 peers. Threshold `ESSAY_TEXT_SIMILARITY_THRESHOLD` is now **0.30**, measured on synthetic essays: honest same-topic writing 0%, a weak partial copy (2 of 5 sentences) 34%, a stronger partial copy (3 of 5) 62%, a reordered full copy 79%. This is a review trigger for a human, not a verdict, and must be tuned against real submissions because common five-word phrases on a narrow prompt could cause false positives.
