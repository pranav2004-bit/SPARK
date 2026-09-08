"""
scoring.py — the single race-safe "finalize a session" primitive (Task 4.1,
completed with real scoring in Task 5.2).

Per ADR 001, every path that can end a session — the beat sweep
(sweep_expired_sessions), the admin close/ cascade (Task 3.2), and the
manual submit endpoint (Task 5.2) — must share exactly one implementation of
"safely transition IN_PROGRESS -> a terminal status and score it," not three
independent ones. finalize_sessions() is that implementation.

Race safety: a single conditional `UPDATE ... WHERE status='IN_PROGRESS'`
against the whole candidate batch. Whichever caller's UPDATE lands first wins
each row; any session already claimed by a concurrent caller (the sweep, an
admin close/, a manual submit) simply won't match anymore and is silently
excluded from that caller's result — no double-scoring, no lost session.

Scoring policy (Decision #1, docs/assessment-service-api.md): exact-match
required for full marks on a question, zero credit otherwise — a student's
selected_option_ids must equal the question's correct-option-id set exactly
(as sets, order irrelevant). This one rule handles both single- and
multi-select questions uniformly: single-select just has exactly one correct
option, so "exact match" reduces to "picked the one right answer."
AssessmentResponse rows are scored once, here, at finalize time — NOT
continuously as the student autosaves (PUT .../answer/ only ever writes
selected_option_ids, never is_correct/marks_awarded) — matching the spec's
"scoring computed at submit/auto-submit time from the frozen
AssessmentResponse set."

Malpractice flagging (Decision #5, docs/assessment-service-api.md — Task
6.2): three fixed, explainable thresholds, also computed here at finalize
time so a session is only ever fully scored once. The cadence threshold
(average time-per-answered-question < 3s) doubles as Task 12.2's bot-defense
signal (AT9 — scripted/automated submission bypassing the exam UI) — the
design doc is explicit that this is "one threshold, not two
independently-invented ones," so no separate bot-detection logic exists.
Also see Decision #5's "what this does and does not guarantee" note: these
flags are a signal for human review, never a claim that cheating occurred.
"""

from django.db.models import Count, Sum
from django.utils import timezone

from core.cache_utils import safe_cache_delete
from .models import (
    AssessmentSession, AssessmentResponse, ResultSummary, Question, QuestionOption,
    ActivityLog, ACTIVITY_EVENT_TAB_SWITCH, ACTIVITY_EVENT_FULLSCREEN_EXIT,
    SESSION_STATUS_IN_PROGRESS, SESSION_TERMINAL_STATUSES,
)

# Decision #5 — fixed global constants for V1, not per-institution
# configurable (avoids building a tuning UI nobody asked for).
TAB_SWITCH_THRESHOLD = 5
FULLSCREEN_EXIT_THRESHOLD = 3
CADENCE_THRESHOLD_SECONDS = 3


def _score_responses(finalized_ids):
    """
    Scores every AssessmentResponse belonging to the given finalized session
    ids: computes is_correct/marks_awarded per response, bulk_updates them,
    and returns (score_by_session, answered_by_session) — the second dict
    is a plain count of answered questions per session, reused by the
    cadence malpractice check so it isn't computed twice.

    A question with no AssessmentResponse row at all (the student never
    answered it) simply contributes nothing to score and isn't counted as
    "answered" — same as a wrong answer would contribute nothing to score.
    """
    responses = list(
        AssessmentResponse.objects.filter(session_id__in=finalized_ids)
        .values("id", "session_id", "question_id", "selected_option_ids")
    )
    if not responses:
        return {}, {}

    question_ids = {r["question_id"] for r in responses}
    marks_by_question = dict(
        Question.objects.filter(id__in=question_ids).values_list("id", "marks")
    )
    correct_options_by_question: dict = {qid: set() for qid in question_ids}
    for question_id, option_id in QuestionOption.objects.filter(
        question_id__in=question_ids, is_correct=True,
    ).values_list("question_id", "id"):
        correct_options_by_question[question_id].add(str(option_id))

    to_update = []
    score_by_session: dict = {}
    answered_by_session: dict = {}
    for r in responses:
        selected = {str(oid) for oid in (r["selected_option_ids"] or [])}
        correct = correct_options_by_question.get(r["question_id"], set())
        is_correct = bool(correct) and selected == correct
        marks = marks_by_question.get(r["question_id"], 0) if is_correct else 0

        to_update.append(AssessmentResponse(id=r["id"], is_correct=is_correct, marks_awarded=marks))
        score_by_session[r["session_id"]] = score_by_session.get(r["session_id"], 0) + marks
        answered_by_session[r["session_id"]] = answered_by_session.get(r["session_id"], 0) + 1

    # batch_size=500 (Task 11.1's bulk-write audit): at exam-end, a single
    # sweep pass can score every response for thousands of sessions at
    # once (dozens of questions each) — unlike bulk_create, bulk_update
    # always emits one UPDATE per row internally regardless of batching,
    # but batch_size still caps how many of those go out per round-trip/
    # transaction chunk, bounding lock duration instead of holding the
    # whole finalize pass in one giant transaction.
    AssessmentResponse.objects.bulk_update(to_update, ["is_correct", "marks_awarded"], batch_size=500)
    return score_by_session, answered_by_session


def _compute_malpractice(finalized_ids, duration_by_session: dict, answered_by_session: dict) -> dict:
    """
    Returns {session_id: (malpractice_flag, malpractice_reasons)} for every
    id in finalized_ids, evaluating the three pinned thresholds (Decision
    #5). All three counts are fetched in bulk (one query each across every
    finalized session), not per-session — this runs inside the same
    finalize_sessions() call the beat sweep uses, which must stay fast even
    when finalizing thousands of sessions in one pass (Task 4.1's load
    requirement).
    """
    tab_switch_counts = dict(
        ActivityLog.objects.filter(session_id__in=finalized_ids, event_type=ACTIVITY_EVENT_TAB_SWITCH)
        .values("session_id").annotate(c=Count("id")).values_list("session_id", "c")
    )
    fullscreen_counts = dict(
        ActivityLog.objects.filter(session_id__in=finalized_ids, event_type=ACTIVITY_EVENT_FULLSCREEN_EXIT)
        .values("session_id").annotate(c=Count("id")).values_list("session_id", "c")
    )

    result = {}
    for sid in finalized_ids:
        reasons = []
        if tab_switch_counts.get(sid, 0) > TAB_SWITCH_THRESHOLD:
            reasons.append("tab_switch")
        if fullscreen_counts.get(sid, 0) > FULLSCREEN_EXIT_THRESHOLD:
            reasons.append("fullscreen_exit")
        answered = answered_by_session.get(sid, 0)
        if answered > 0 and (duration_by_session.get(sid, 0) / answered) < CADENCE_THRESHOLD_SECONDS:
            reasons.append("cadence")
        result[sid] = (bool(reasons), reasons)
    return result


def finalize_sessions(queryset, new_status: str) -> int:
    """
    Finalize every session in `queryset` that is still IN_PROGRESS into
    `new_status` (must be a terminal status — SUBMITTED or AUTO_SUBMITTED),
    scoring its AssessmentResponse set and creating a ResultSummary for each
    one actually finalized by this call.

    `queryset` supplies the *candidate selection* only (e.g. the sweep
    passes `AssessmentSession.objects.filter(ends_at__lte=now())`, Task
    3.2's close/ cascade passes `AssessmentSession.objects.filter(assignment=assignment)`)
    — this function itself always additionally filters to
    `status=IN_PROGRESS` and only touches rows that still match at UPDATE
    time, regardless of what the caller's queryset otherwise selected.

    Returns the number of sessions this call actually finalized (0 is a
    valid, expected result — e.g. every candidate was already claimed by a
    concurrent caller, or there were no candidates at all).
    """
    if new_status not in SESSION_TERMINAL_STATUSES:
        raise ValueError(f"new_status must be a terminal status, got {new_status!r}")

    candidates = list(
        queryset.filter(status=SESSION_STATUS_IN_PROGRESS).values(
            "id", "assignment_id", "student_id", "set_id", "started_at",
            "assignment__institution_id",
            # Fallback source of institution_id for a trial session
            # (assignment is None, 2026-08-27) — a real session's
            # assignment__institution_id already covers it, but a trial has
            # no assignment to resolve that from.
            "set__paper__institution_id",
        )
    )
    if not candidates:
        return 0

    candidate_ids = [c["id"] for c in candidates]

    # The one race-safe write in this whole function — every other query
    # here is read-only or a downstream insert/update gated by its result.
    updated_count = AssessmentSession.objects.filter(
        id__in=candidate_ids, status=SESSION_STATUS_IN_PROGRESS,
    ).update(status=new_status)

    # Task 12.1's concurrency audit (real OS-thread test, not just a
    # sequential double-call) caught a genuine bug here: this early-out
    # didn't exist before, and without it, a caller whose own UPDATE
    # touched zero rows (every one of its candidates had already been
    # claimed by a concurrent caller between this function's SELECT and
    # UPDATE) would still fall through to the status-only recheck below,
    # which can't tell "I just flipped this row" apart from "it already
    # matches new_status because someone else flipped it" — so the loser
    # of a race would falsely claim credit for the winner's session,
    # redundantly re-scoring it and reporting an inflated finalized count.
    # ResultSummary's unique-session constraint + bulk_create's
    # ignore_conflicts already stopped that from ever producing a
    # duplicate DB row, but the wasted recomputation and the wrong return
    # value were real. update()'s own return value has no such ambiguity —
    # it's exactly how many rows THIS call's WHERE clause matched — so 0
    # means every candidate was already claimed elsewhere and there is
    # nothing left for this call to do.
    if not updated_count:
        return 0

    # Re-check which of OUR candidates actually landed in new_status — a
    # session might have been claimed by a *different* concurrent caller
    # (targeting a different new_status) between our SELECT and UPDATE
    # above; only score the ones that are now in the state THIS call meant
    # to put them in.
    finalized_ids = set(
        AssessmentSession.objects.filter(
            id__in=candidate_ids, status=new_status,
        ).values_list("id", flat=True)
    )
    if not finalized_ids:
        return 0

    set_ids = {c["set_id"] for c in candidates if c["id"] in finalized_ids}
    total_marks_by_set = dict(
        Question.objects.filter(set_id__in=set_ids)
        .values("set_id").annotate(total=Sum("marks"))
        .values_list("set_id", "total")
    )

    score_by_session, answered_by_session = _score_responses(finalized_ids)

    now = timezone.now()
    duration_by_session = {
        c["id"]: max(int((now - c["started_at"]).total_seconds()), 0)
        for c in candidates if c["id"] in finalized_ids
    }
    malpractice_by_session = _compute_malpractice(finalized_ids, duration_by_session, answered_by_session)

    results = []
    for c in candidates:
        if c["id"] not in finalized_ids:
            continue
        flag, reasons = malpractice_by_session.get(c["id"], (False, []))
        results.append(ResultSummary(
            session_id=c["id"],
            assignment_id=c["assignment_id"],
            student_id=c["student_id"],
            institution_id=c["assignment__institution_id"] or c["set__paper__institution_id"],
            started_at=c["started_at"],
            ended_at=now,
            duration_seconds=duration_by_session[c["id"]],
            score=score_by_session.get(c["id"], 0),
            total_marks=total_marks_by_set.get(c["set_id"]) or 0,
            status=new_status,
            malpractice_flag=flag,
            malpractice_reasons=reasons,
        ))

    if results:
        # ignore_conflicts: a defensive backstop against ResultSummary's
        # OneToOneField unique constraint — not the primary safety
        # mechanism (that's the conditional UPDATE above), but harmless
        # insurance against an exotic double-attempt slipping through.
        # batch_size=500 — Task 11.1's bulk-write audit, same rationale and
        # convention as allocation.py's bulk_create.
        ResultSummary.objects.bulk_create(results, ignore_conflicts=True, batch_size=500)

        # Task 9.1: the dashboard KPI cache is explicit-invalidation, not
        # pure TTL — every assignment that just gained a new ResultSummary
        # row must have its cached dashboard dropped so the next read
        # recomputes fresh, rather than serving stale KPIs for up to the
        # full defensive-backstop TTL.
        # Trial results (assignment_id is None, 2026-08-27) have no
        # dashboard to invalidate — filtered out rather than deleting a
        # nonsense "assessment_dashboard:None" key.
        for assignment_id in {r.assignment_id for r in results if r.assignment_id}:
            # safe_cache_delete (Task 13.1): this sits on the critical
            # exam-submit path — a Redis outage must never be able to fail
            # a student's submit or the sweep's finalize pass just because
            # the dashboard-invalidation side effect couldn't run.
            safe_cache_delete(f"assessment_dashboard:{assignment_id}")

    return len(results)
