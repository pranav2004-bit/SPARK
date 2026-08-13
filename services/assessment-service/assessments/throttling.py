from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle

from core.throttling_resilience import ResilientThrottleMixin


class AnswerSubmitRateThrottle(ResilientThrottleMixin, UserRateThrottle):
    """Per-student rate limit on the answer-autosave endpoint (Task 11.2).

    Previously this endpoint only got the generic DEFAULT_THROTTLE_RATES
    "user" bucket (300/min), shared across every endpoint the student's JWT
    touches — not a number anyone had actually reasoned about for this
    specific hot path, and not documented per this task's explicit
    requirement to state the threshold and its rationale. A dedicated scope
    gives answer-submission its own budget, independent of whatever else
    the student's client is calling (server-time polling, activity-log
    batches, etc.).

    Rate: 120/min (see DEFAULT_THROTTLE_RATES["answer_submit"] in
    core/settings.py), derived like this — Decision #5's
    CADENCE_THRESHOLD_SECONDS=3 (scoring.py) already defines "humanly
    implausible" as averaging under 3s/question over a whole session, i.e.
    a floor of ~20/min; a live per-request throttle that sits anywhere near
    that floor risks throttling a genuinely fast (but human) student
    mid-exam, which is a far worse failure mode here than under-throttling
    a script — nginx is this service's *primary* rate limiter
    (core/settings.py's own comment), this DRF-level throttle is
    documented defense-in-depth, and the cadence check itself already
    flags scripted-speed answering for admin review after the fact
    (ties into Task 12.2's bot-defense work). 120/min (2/s) sits at 6x
    that floor — comfortable headroom above any plausible burst of a
    student clicking through several already-decided answers in a row,
    while still meaningfully capping a naive scripted flood far above
    what any legitimate exam-taking pattern would ever produce.
    """
    scope = "answer_submit"


class ActivityLogRateThrottle(ResilientThrottleMixin, SimpleRateThrottle):
    """Per-session (not per-user, not per-IP) rate limit on the activity-log
    ingestion endpoint (Task 6.2) — a compromised/buggy client hammering
    this endpoint must not degrade the service for other students sharing
    the same exam. Rate is configured via DEFAULT_THROTTLE_RATES['activity_log']
    in core/settings.py."""
    scope = "activity_log"

    def get_cache_key(self, request, view):
        session_id = view.kwargs.get("pk")
        if not session_id:
            return None
        return self.cache_format % {"scope": self.scope, "ident": session_id}
