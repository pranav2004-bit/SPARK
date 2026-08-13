# assessment-service — Retake / Re-Attempt Q&A & Deferred Edge Cases

**Related:** [Data Model & API Contract](assessment-service-api.md) (Decision #3 — the original V1 scope call this file expands on), [Timer Model Q&A & Deferred Edge Cases](assessment-service-timer-edge-cases.md) (same "deliberately deferred" documentation convention), [ADR 001](adr/001-assessment-timer-architecture.md), [V2_GAPS.md](../V2_GAPS.md)

This document captures a Q&A session about what happens when a student's session ends *not* because they finished, but because of a system/internet/technical failure mid-exam — and whether they can be given a genuine retake. Like the timer edge-cases doc, this records a real, currently-unbuilt gap, not a bug — so the reasoning doesn't need re-deriving from scratch later.

---

## The scenario

Student A starts a real exam. Partway through, their internet drops, their laptop crashes, or some other technical failure occurs — through no fault of their own answering. Either:
- the session sits unanswered past `ends_at` and the sweep auto-submits it, or
- a retry/reconnect attempt itself triggers a submit,

and the student ends up with a low or zero score for reasons that have nothing to do with their knowledge of the material.

**Question:** can this specific student be given a real retake of *this* assessment, with the earlier broken attempt's data superseded by the new one, and some record of "this was attempt #2" kept?

---

## Current state: not implemented

Confirmed against the actual data model and views, not assumed:

1. **One session per student per assignment, enforced at the database level.** `AssessmentSession` has `unique_together = [("assignment", "student_id")]`. A second `start-session` call for the same student on the same assignment doesn't create a new attempt — it returns the *existing* session (the API's own resume behavior, by design, for the ordinary "page refresh mid-exam" case). There is no code path that deletes or resets an existing session to allow a genuine second attempt.
2. **No attempt-number field anywhere.** Neither `AssessmentSession` nor `ResultSummary` has any concept of "attempt 1," "attempt 2," etc. There is exactly one result per (assignment, student), full stop.
3. **No merge/replace logic.** Because a second real attempt under the same assignment isn't possible at all today, there's naturally no logic for "supersede the old attempt's score/answers with the new one" either.

This traces back to an explicit, deliberate V1 scope decision made at the very start of this project (Task 0.2, Decision #3): *"Retake/re-attempt policy: out of scope for V1. One session per student per BatchAssignment, no reset/re-issue mechanism. An admin needing to give a student another attempt creates a new BatchAssignment."* This document is about how much that stated workaround actually covers — and where it falls short of what a real institution needs.

---

## What the existing workaround actually gives you (and doesn't)

The documented V1 answer is: *create a new `BatchAssignment` for the affected student.* This works, today, with zero new code. But it's worth being precise about what it does and doesn't provide, since "it's possible" and "it's the same as a real retake feature" are different claims:

| What you get | What you don't get |
|---|---|
| The student can genuinely take the exam again | No link between the new attempt and the original broken one — they're two unrelated database rows |
| A real, scored `ResultSummary` for the new attempt | No "attempt #2" tag anywhere — nothing distinguishes this from an ordinary first-time assignment |
| Works today, no code changes | The original (failed) attempt's `ResultSummary` still exists as a separate row — if it's ever included in analytics/exports/dashboards for the *original* assignment, it looks like a real, valid low score, not a known technical failure |
| Institution-level control (an admin decides case by case) | No audit trail of *why* a retake was granted — that context lives only wherever the admin happens to write it down outside the system |

---

## Is this a real gap?

Yes — flagged directly, not softened. "My internet dropped mid-exam" is one of the single most common real support requests during any live, timed, high-stakes assessment. An institution running real graded exams will hit this on essentially every exam day at some scale. The current workaround (new assignment) is functional but manual, untracked, and leaves the original broken attempt sitting in the data as if it were a genuine result unless an admin remembers to manually exclude or annotate it.

---

## Deferred: a real retake/attempt-history feature

**Status: not built, not scheduled.** If this becomes a priority, here is what it would actually require — recorded so the scoping conversation doesn't start from zero:

- **Schema change:** either allow multiple `AssessmentSession` rows per (assignment, student) with an `attempt_number` field, or introduce a separate `RetakeGrant` concept that explicitly authorizes and links a second session to the first. The current `unique_together` constraint would need to change either way — carefully, since that constraint is also part of what keeps AT4 (duplicate/replayed submission) closed today; loosening it needs its own dedicated re-audit, not an assumption that AT4's existing protections still fully apply once multiple legitimate sessions per student are possible.
- **A policy decision, not just code:** when a student has two attempts, which one counts? Latest? Highest score? Does an admin have to explicitly mark one as "the valid attempt for grading"? This is an institutional policy question as much as a technical one, and needs an answer before the schema can be finalized.
- **Explicit admin action, scoped to one student under the existing assignment** — not the current all-or-nothing "spin up a whole new assignment" — e.g. `POST .../admin/assignments/<id>/students/<student_id>/grant-retake/`, logged with who approved it and why (the audit trail the current workaround lacks).
- **Results/Analytics/Dashboard rework.** Every aggregation in Tasks 7.1/8.1/9.1 today assumes exactly one `ResultSummary` per (assignment, student). Multiple attempts means deciding, and then implementing, how each of those views treats a student with 2+ rows — this is not a small addition, it touches the core query of three separate modules.
- **CSV export** would need an attempt-number column once more than one row per student is possible, or it silently becomes ambiguous which row is which.
- **ActivityLog treatment across attempts** — kept per-attempt (so a malpractice flag from a broken first attempt doesn't unfairly follow the legitimate retake), which the current model already supports naturally since logs are session-scoped, but this should be verified deliberately once retakes exist, not assumed.

**Until this is built, the supported way to handle "this student's attempt was ruined by a technical failure"** is the same one used for "students who missed the exam entirely": create a new assignment for them. It works, but it's a manual, untracked substitute for a real retake feature — that gap is the point of this document.
