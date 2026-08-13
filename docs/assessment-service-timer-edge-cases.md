# assessment-service — Timer Model Q&A & Deferred Edge Cases

**Related:** [ADR 001 — Timer Architecture](adr/001-assessment-timer-architecture.md), [assessment-service-api.md](assessment-service-api.md), [V2_GAPS.md](../V2_GAPS.md) (same "deliberately deferred" convention this file follows)

This document captures a Q&A session about the two-timer model that surfaced a real, currently-unbuilt edge case — not a bug, a deliberate gap, recorded here so it isn't re-discovered from scratch later. Nothing in this file requires code changes; it's a reference for when (if) this edge case needs to become a real feature.

---

## The two-timer model, in plain terms

Every assessment has two independent clocks:

1. **Global timer** (`BatchAssignment.global_expire_time`) — one fixed date+time, set once when the assignment is created. This is the outer hard gate: the assessment does not exist past this moment, for anyone, no exceptions.
2. **Per-student exam timer** (`exam_duration_minutes`) — starts counting the moment *that specific student* clicks start, not before.

A student's actual deadline (`AssessmentSession.ends_at`) is computed **once**, at the moment they start, as:

```
ends_at = min(session_start_time + exam_duration_minutes, global_expire_time)
```

Whichever is stricter wins. Example: global expires 3:00pm, duration is 30 minutes, a student starts at 2:45pm — their duration alone would carry them to 3:15pm, but the global gate closes first, so they're cut off at 3:00pm and lose those last 15 minutes. This is correct, intended behavior, not a bug.

**The critical design point:** once `ends_at` is computed at start time, it is never recomputed. Editing `global_expire_time` after a student has started has **zero effect** on that student — this is deliberate (ADR 001, Decision #2), not an oversight.

---

## Q&A

**Q: Can a student's own exam time be extended after they've already started?**
A: Yes. `PATCH .../admin/assignments/<id>/sessions/<session_id>/extend/` extends one specific session's `ends_at` directly. This is the real, tested, documented mechanism for "this one student needs more time" (capped at 1440 minutes / 24h — Task 12.2's abuse-hardening fix). See the [exam-day runbook](runbooks/assessment-exam-day.md) §3.

**Q: Can the global timer (`global_expire_time`) be edited after the assignment is created — during the live window, or after it expires?**
A: No, in both cases. There is no endpoint for it. `AdminAssignmentDetailView` only supports `GET`, not `PATCH`, on this field. Even if such an endpoint existed, editing it would do nothing for students already in progress (see above) — it would only matter for the small window of students who haven't started yet but are still within the (new) time. Once expired, `StudentAssignmentStartSessionView` independently refuses new session starts past `global_expire_time` regardless of what the field says, so a bare field edit wouldn't even reopen the door for late-starters.

**Q: 100 students were assigned an exam. Only 60 took it before the global timer expired; 40 never started. Can we extend the global timer to let those 40 in?**
A: Not today — no mechanism exists for this. The intended path today is to **create a new `BatchAssignment`** (same paper, new global time window) scoped to just those 40 students. This already works, is already tested, and doesn't touch the original (now-closed) assignment at all.

**Q: Why not just let admins reopen/extend a closed assignment — what's actually stopping it?**
A: Not a technical limitation so much as a deliberate integrity boundary. "Closed" is currently treated as **permanent** by design, for three reasons:
1. **Fairness/leak risk** — the 60 who already took it could describe questions/answers to the 40 taking it "again" later. A hard, permanent close prevents this.
2. **Result finality** — dashboards, exports, and backups all treat a closed assignment's results as a settled, trustworthy record. Reopening blurs "was this the real exam."
3. **Paper-lock assumptions** — `QuestionPaper.is_locked()` and related logic assume once any assignment referencing a paper reaches SCHEDULED/LIVE/CLOSED, that history is permanent. Several other features build on "closed means closed" as a given.

---

## Deferred: "reopen for unstarted students only"

**Status: not built, not scheduled. Documented so a future request for this doesn't require re-deriving the reasoning above from scratch.**

If this is ever wanted, it is buildable — but as a real, carefully-scoped feature, not a quick status flip. What it would actually require:

- A new admin action (not simply un-doing `status=CLOSED`) that:
  - Extends `global_expire_time` to a new value, **only** for a CLOSED assignment where no session for the reopened target students exists yet.
  - Explicitly excludes any student who already has an `AssessmentSession` (submitted or auto-submitted) — those 60 must stay locked out, or the fairness problem above reappears.
- Re-verifying the Celery beat sweep (`sweep_expired_assignments`/`sweep_expired_sessions`) against a status transition it doesn't currently expect (CLOSED → LIVE again) — today's sweep logic and its tests assume CLOSED is terminal and reached at most once per assignment.
- Deciding whether `QuestionPaper.is_locked()`'s semantics need a carve-out, or whether this is fine as-is (a reopened assignment still references the same, still-locked paper — probably fine, but worth confirming, not assuming).
- New dedicated tests for the reopened-assignment path specifically (mirroring the rigor of the existing IDOR/race/timer-spoofing suites), not an assumption that existing tests already cover it.

**Until this is built, the supported way to handle "some students missed the exam"** is to create a new assignment for them — zero new code, zero new risk, already working today.
