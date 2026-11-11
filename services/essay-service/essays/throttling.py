from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle

from core.throttling_resilience import ResilientThrottleMixin, FailClosedThrottleMixin, FailClosedUserRateThrottle


class EssayAutosaveRateThrottle(ResilientThrottleMixin, UserRateThrottle):
    """Per-student rate limit on the draft-autosave endpoint. Rate: 120/min
    (DEFAULT_THROTTLE_RATES["essay_autosave"], ADR 004 Section 4) — sized
    like assessment-service's own answer-submit throttle, generous headroom
    for a debounced single-question autosave cadence (Task 4.2)."""
    scope = "essay_autosave"


class EssaySubmitRateThrottle(FailClosedUserRateThrottle):
    """Per-student burst-control rate limit on the manual-submit endpoint.
    Rate: 10/min (DEFAULT_THROTTLE_RATES["essay_submit"], ADR 004 Section
    4) — deliberately tight: a genuine submit happens once per assignment,
    this only needs to absorb a handful of legitimate client retries on a
    flaky network, not sustained traffic.

    Fail-CLOSED (Phase 5, ADR 003 Decision 8 / ADR 004 Section 5) — this
    endpoint is essay-service's one "submission-creation" entry point
    (finalize_attempts() is dispatched from here, from the beat sweep, and
    from admin close; only this one is a public HTTP endpoint an attacker
    could flood), so it's the deliberate exception to every other throttle
    on this platform's "fail open" default. Was fail-open (via
    ResilientThrottleMixin) before Phase 5 — changed here, not left as an
    oversight once the real cost risk (an unmetered flood exhausting the
    LLM budget) existed to guard against."""
    scope = "essay_submit"


class EssaySubmitPerStudentHourlyThrottle(FailClosedUserRateThrottle):
    """ADR 004 Section 5's per-student ceiling — 500/hour
    (DEFAULT_THROTTLE_RATES["essay_submit_hourly_student"]), CLAP's own
    default, adopted as-is per that section's reasoning: already generous
    relative to a single-question assessment's realistic volume, so
    re-deriving a smaller number risks legitimate false positives with no
    real benefit. A distinct time window/scope from EssaySubmitRateThrottle
    above (per-hour business-logic ceiling vs. per-minute burst control),
    not a duplicate of it."""
    scope = "essay_submit_hourly_student"


class EssaySubmitPerInstitutionHourlyThrottle(FailClosedThrottleMixin, SimpleRateThrottle):
    """ADR 004 Section 5's per-institution/batch ceiling — 5,000/hour
    (DEFAULT_THROTTLE_RATES["essay_submit_hourly_institution"]), CLAP's own
    default, adopted as-is (re-derive only if a real institution's expected
    concurrent batch size would exceed it, which ADR 002 Decision 4's own
    scoped batch-size assumption makes unlikely)."""
    scope = "essay_submit_hourly_institution"

    def get_cache_key(self, request, view):
        institution_id = getattr(request.user, "institution_id", None)
        if not institution_id:
            return None
        return self.cache_format % {"scope": self.scope, "ident": institution_id}


class EssayMalpracticeEventRateThrottle(ResilientThrottleMixin, SimpleRateThrottle):
    """Per-attempt (not per-user, not per-IP) rate limit on the
    malpractice-event ingestion endpoint — matches assessment-service's own
    ActivityLogRateThrottle exactly: a compromised/buggy client hammering
    this endpoint must not degrade the service for other students in the
    same exam. Rate: 20/min (DEFAULT_THROTTLE_RATES["essay_malpractice_event"])."""
    scope = "essay_malpractice_event"

    def get_cache_key(self, request, view):
        attempt_id = view.kwargs.get("pk")
        if not attempt_id:
            return None
        return self.cache_format % {"scope": self.scope, "ident": attempt_id}
