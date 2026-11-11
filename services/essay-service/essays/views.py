import csv
import io
import logging
import zipfile
from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import HttpResponse, StreamingHttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.generics import get_object_or_404

from core.permissions import IsAdminOrSuperAdmin, IsStudentUser
from core.responses import success_response, error_response
from core.pagination import StandardResultsPagination, SubmissionsListPagination
from core.cache_utils import safe_cache_get, safe_cache_set, safe_cache_delete
from core.celery_utils import safe_task_dispatch

from django.db import transaction, IntegrityError
from django.utils import timezone

from django.utils.dateparse import parse_datetime, parse_date

from .models import (
    EssayPaper, EssaySet, EssayQuestion, EssayAssignment, EssayStudentSetAllocation, EssayAttempt,
    EssayMalpracticeEvent, MALPRACTICE_EVENT_TYPE_CHOICES, MALPRACTICE_EVENT_TEXT_SIMILARITY,
    ASSIGNMENT_STATUS_SCHEDULED, ASSIGNMENT_STATUS_LIVE, ASSIGNMENT_STATUS_CLOSED,
    ATTEMPT_STATUS_IN_PROGRESS, ATTEMPT_STATUS_SUBMITTED, ATTEMPT_STATUS_AUTO_SUBMITTED,
    ATTEMPT_TERMINAL_STATUSES,
    EssaySubmission, EssayFailedJob, EssayScore, EssayLLMTrace, EssaySubmissionEvent,
    SUBMISSION_STATUS_PENDING, SUBMISSION_STATUS_LLM_PROCESSING,
    SUBMISSION_STATUS_LLM_COMPLETE, SUBMISSION_STATUS_LLM_FAILED,
    SUBMISSION_STATUS_REPORT_GENERATING, SUBMISSION_STATUS_REPORT_READY,
    SUBMISSION_EVENT_ADMIN_RETRIGGER, SUBMISSION_EVENT_ADMIN_OVERRIDE,
    SUBMISSION_EVENT_EMAIL_BOUNCED, SUBMISSION_EVENT_EMAIL_COMPLAINT, SUBMISSION_EVENT_DLQ_RECORDED,
    EVALUATED_BY_ADMIN,
)
from .serializers import (
    EssayPaperSerializer, EssaySetSerializer, EssayQuestionSerializer, EssayAssignmentSerializer,
    StudentEssayQuestionSerializer, EssaySubmissionListSerializer, EssaySubmissionDetailSerializer,
    EssayLLMTraceSerializer,
)
from .validators import get_assignment_readiness_blockers
from .allocation import snapshot_roster_and_allocate
from core.user_service_client import fetch_batch_roster
from .enforcement import attempt_is_writable, strip_client_timestamps
from .scoring import finalize_attempts
from .throttling import (
    EssayAutosaveRateThrottle, EssaySubmitRateThrottle, EssayMalpracticeEventRateThrottle,
    EssaySubmitPerStudentHourlyThrottle, EssaySubmitPerInstitutionHourlyThrottle,
)

logger = logging.getLogger("essays.submissions")


def _get_institution_id(request):
    return getattr(request.user, "institution_id", None)


PAPER_LOCKED_MSG = "This paper is assigned and locked."


class _RosterSnapshotFailed(Exception):
    pass


# ── Health ─────────────────────────────────────────────────────────────────────
# Phase 1 scaffolding only — Question Bank / Assign / student exam-taking /
# LLM evaluation / the remaining 9 admin modules are built in later phases
# per LIVETRACKER3_V1.md. This mirrors assessment-service's HealthView
# exactly (DB + Redis reachability, no auth required, never throttled).

class HealthView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = []  # never throttle — polled at high frequency by health checks

    def get(self, request):
        from django.db import connection

        db_ok = False
        try:
            connection.ensure_connection()
            db_ok = True
        except Exception:
            pass

        redis_ok = False
        try:
            cache.set("health_check", "ok", 5)
            redis_ok = cache.get("health_check") == "ok"
        except Exception:
            pass

        status = "ok" if (db_ok and redis_ok) else "degraded"
        return success_response(data={
            "status": status,
            "service": "essay-service",
            "db": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
        })


# ── Admin: Essay Papers (Phase 2 — Question Bank) ───────────────────────────────
# Mirrors assessment-service's Admin{Paper,Set,Question} views: institution-
# scoped via get_object_or_404's filtered queryset (cross-institution access
# → 404, not 403 — verified against assessment-service's real code, not
# assumed). No per-paper ownership restriction (see core/permissions.py's
# IsAdminOrSuperAdmin docstring). Lock-enforcement (paper.is_locked(), added
# in Phase 3 per Task 2.1/3.2's correction notes) now guards every create/
# edit/delete path below — GET/list are never blocked, matching
# assessment-service's own convention exactly.

class AdminPaperListCreateView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        institution_id = _get_institution_id(request)
        papers = EssayPaper.objects.filter(
            institution_id=institution_id
        ).annotate(set_count=Count("sets"))

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(papers, request)
        data = EssayPaperSerializer(page, many=True).data
        return paginator.get_paginated_response(data)

    def post(self, request):
        institution_id = _get_institution_id(request)
        s = EssayPaperSerializer(data=request.data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save(institution_id=institution_id, created_by=request.user.id)
        return success_response(data=s.data, status_code=201, message="Paper created")


class AdminPaperDetailView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def _get(self, pk, institution_id):
        return get_object_or_404(EssayPaper, pk=pk, institution_id=institution_id)

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        paper = self._get(pk, institution_id)
        sets = paper.sets.annotate(
            has_question=Count("question", distinct=True)
        )
        return success_response(data={
            "paper": EssayPaperSerializer(paper).data,
            "sets": EssaySetSerializer(sets, many=True).data,
        })

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        paper = self._get(pk, institution_id)
        if paper.is_locked():
            return error_response(PAPER_LOCKED_MSG, status_code=403)
        s = EssayPaperSerializer(paper, data=request.data, partial=True)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save()
        return success_response(data=s.data, message="Paper updated")

    def delete(self, request, pk):
        institution_id = _get_institution_id(request)
        paper = self._get(pk, institution_id)
        if paper.is_locked():
            return error_response(PAPER_LOCKED_MSG, status_code=403)
        paper.delete()
        return success_response(message="Paper deleted")


# ── Admin: Essay Sets ────────────────────────────────────────────────────────────

class AdminPaperSetsView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        paper = get_object_or_404(EssayPaper, pk=pk, institution_id=institution_id)
        if paper.is_locked():
            return error_response(PAPER_LOCKED_MSG, status_code=403)

        data = {**request.data, "paper": str(paper.id)}
        if not data.get("order"):
            from django.db.models import Max
            max_order = paper.sets.aggregate(m=Max("order"))["m"] or 0
            data["order"] = max_order + 1

        s = EssaySetSerializer(data=data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save()
        return success_response(data=s.data, status_code=201, message="Set created")


class AdminSetDetailView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def _get(self, pk, institution_id):
        return get_object_or_404(
            EssaySet.objects.select_related("paper"),
            pk=pk, paper__institution_id=institution_id,
        )

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        eset = self._get(pk, institution_id)
        question = EssayQuestion.objects.filter(set=eset).first()
        return success_response(data={
            "set": EssaySetSerializer(eset).data,
            "paper": EssayPaperSerializer(eset.paper).data,
            "question": EssayQuestionSerializer(question).data if question else None,
        })

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        eset = self._get(pk, institution_id)
        if eset.paper.is_locked():
            return error_response(PAPER_LOCKED_MSG, status_code=403)
        s = EssaySetSerializer(eset, data=request.data, partial=True)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save()
        return success_response(data=s.data, message="Set updated")

    def delete(self, request, pk):
        institution_id = _get_institution_id(request)
        eset = self._get(pk, institution_id)
        if eset.paper.is_locked():
            return error_response(PAPER_LOCKED_MSG, status_code=403)
        eset.delete()
        return success_response(message="Set deleted")


# ── Admin: Essay Questions ───────────────────────────────────────────────────────
# Exactly one question per set (EssayQuestion.set is a OneToOneField) —
# AdminSetQuestionView's post() rejects a second create explicitly rather
# than letting the database's own IntegrityError surface as an opaque 500.

class AdminSetQuestionView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        eset = get_object_or_404(
            EssaySet.objects.select_related("paper"),
            pk=pk, paper__institution_id=institution_id,
        )
        if eset.paper.is_locked():
            return error_response(PAPER_LOCKED_MSG, status_code=403)
        if EssayQuestion.objects.filter(set=eset).exists():
            return error_response(
                "This set already has a question. Edit or delete it first.",
                status_code=400,
            )
        data = {**request.data, "set": str(eset.id)}
        s = EssayQuestionSerializer(data=data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save(set=eset)
        return success_response(data=s.data, status_code=201, message="Question created")


class AdminQuestionDetailView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def _get(self, pk, institution_id):
        return get_object_or_404(
            EssayQuestion.objects.select_related("set__paper"),
            pk=pk, set__paper__institution_id=institution_id,
        )

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        question = self._get(pk, institution_id)
        if question.set.paper.is_locked():
            return error_response(PAPER_LOCKED_MSG, status_code=403)
        s = EssayQuestionSerializer(question, data=request.data, partial=True)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save()
        return success_response(data=s.data, message="Question updated")

    def delete(self, request, pk):
        institution_id = _get_institution_id(request)
        question = self._get(pk, institution_id)
        if question.set.paper.is_locked():
            return error_response(PAPER_LOCKED_MSG, status_code=403)
        question.delete()
        return success_response(message="Question deleted")


# ── Admin: Essay Assignments (Phase 3 — Assessment Assign Module) ──────────────
# Mirrors assessment-service's Admin{Assignment}* views.
#
# Close() DOES cascade-finalize in-progress attempts (see
# AdminEssayAssignmentCloseView below) — added in Phase 4 once EssayAttempt
# existed, exactly as promised in this section's own Task 3.2-era note
# (superseded here, not left stale): "Phase 4 needs to add the cascade once
# EssayAttempt exists."
#
# Still genuinely missing, and NOT part of Phase 4's own task list (4.1–4.4
# never named it, so building it now would be unscoped, unrequested work):
# a per-student timer-extension endpoint, the essay-service equivalent of
# assessment-service's AdminAssignmentExtendSessionView. EssayAttempt exists
# now, so nothing blocks building this anymore — it just hasn't been asked
# for by any phase's checklist yet. Flagged here for whoever plans a future
# phase, not silently dropped.

class AdminEssayAssignmentListCreateView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        institution_id = _get_institution_id(request)
        qs = EssayAssignment.objects.filter(institution_id=institution_id).select_related("paper")
        paper_id = request.query_params.get("paper_id")
        if paper_id:
            qs = qs.filter(paper_id=paper_id)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(EssayAssignmentSerializer(page, many=True).data)

    def post(self, request):
        institution_id = _get_institution_id(request)
        paper = get_object_or_404(
            EssayPaper, pk=request.data.get("paper"), institution_id=institution_id
        )

        blockers = get_assignment_readiness_blockers(paper)
        if blockers:
            return error_response(
                "Cannot assign: " + " ".join(blockers),
                errors={"assign": blockers},
                status_code=400,
            )

        # Same paper -> the SAME batch twice while still SCHEDULED/LIVE has
        # no legitimate use case (double-allocates the same students into
        # two independently-tracked attempts) — matches assessment-service's
        # exact rule. A CLOSED assignment doesn't count, so reassigning
        # later (e.g. a retake) is still allowed.
        batch_id = request.data.get("batch_id")
        if batch_id and EssayAssignment.objects.filter(
            paper=paper, batch_id=batch_id, institution_id=institution_id,
            status__in=[ASSIGNMENT_STATUS_SCHEDULED, ASSIGNMENT_STATUS_LIVE],
        ).exists():
            return error_response(
                "This paper is already assigned to this batch and hasn't been closed yet.",
                status_code=400,
            )

        s = EssayAssignmentSerializer(data=request.data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        try:
            with transaction.atomic():
                assignment = s.save(institution_id=institution_id, created_by=request.user.id)
                try:
                    snapshot_roster_and_allocate(assignment, auth_header)
                except RuntimeError as exc:
                    # Roll back the whole transaction — the assignment must
                    # not exist if its roster snapshot failed (no partial/
                    # corrupt allocation state, matching assessment-service).
                    raise _RosterSnapshotFailed(str(exc)) from exc
        except _RosterSnapshotFailed as exc:
            return error_response(f"Could not create assignment: {exc}", status_code=502)

        return success_response(
            data=EssayAssignmentSerializer(assignment).data, status_code=201, message="Assignment created",
        )


class AdminEssayAssignmentDetailView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(EssayAssignment, pk=pk, institution_id=institution_id)
        return success_response(data=EssayAssignmentSerializer(assignment).data)


class AdminEssayAssignmentStartView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(EssayAssignment, pk=pk, institution_id=institution_id)

        # Conditional UPDATE ... WHERE status=SCHEDULED — race-safe against
        # concurrent Start clicks, matching assessment-service's own pattern.
        updated = EssayAssignment.objects.filter(
            pk=assignment.pk, status=ASSIGNMENT_STATUS_SCHEDULED,
        ).update(
            status=ASSIGNMENT_STATUS_LIVE,
            global_start_time=assignment.global_start_time or timezone.now(),
        )
        assignment.refresh_from_db()

        # Phase 10's own dashboard cache — real gap found by that phase's
        # own second final-audit round: this view changes
        # EssayAssignment.status directly, which the dashboard's own
        # assignment_status/time_remaining_seconds fields read straight
        # from — none of the five hooks that phase originally built
        # touch EssayAssignment.status at all (they're all about
        # EssaySubmission), so a dashboard opened for a still-SCHEDULED
        # assignment (time_remaining_seconds: null) and then cached would
        # keep showing that stale shape for up to the full 300s TTL after
        # an admin clicks Start, even though the exam is now genuinely
        # live. Only invalidate on a real transition (`updated` truthy)
        # — a redundant Start click that hits the "already live" branch
        # below changed nothing, so there's nothing to invalidate.
        if updated:
            safe_cache_delete(f"essay_dashboard:{assignment.id}")

        if not updated:
            if assignment.status == ASSIGNMENT_STATUS_LIVE:
                return success_response(
                    data=EssayAssignmentSerializer(assignment).data, message="Assignment is already live",
                )
            return error_response(
                f"Cannot start an assignment with status {assignment.status}.", status_code=409,
            )

        return success_response(data=EssayAssignmentSerializer(assignment).data, message="Assignment started")


class AdminEssayAssignmentCloseView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(EssayAssignment, pk=pk, institution_id=institution_id)

        was_already_closed = assignment.status == ASSIGNMENT_STATUS_CLOSED
        EssayAssignment.objects.filter(pk=assignment.pk).exclude(
            status=ASSIGNMENT_STATUS_CLOSED,
        ).update(status=ASSIGNMENT_STATUS_CLOSED)
        assignment.refresh_from_db()

        # Phase 10's own dashboard cache — real gap found by that phase's
        # own second final-audit round: this view changes
        # EssayAssignment.status directly. The cascade below (via
        # finalize_attempts() -> _create_and_dispatch_submissions())
        # DOES invalidate the cache, but only when at least one attempt
        # actually gets auto-submitted — the common case where an admin
        # closes an assignment with zero students still IN_PROGRESS
        # (everyone already finished, or nobody ever started) would
        # finalize nothing and silently skip invalidation entirely,
        # leaving the dashboard showing assignment_status: "LIVE" with a
        # ticking time_remaining_seconds for up to the full 300s TTL
        # after the exam has genuinely already ended — exactly backwards
        # from what "Close" is supposed to communicate. Invalidated here
        # directly, independent of whatever the cascade below does, and
        # only on a real transition (not a redundant Close on an
        # already-CLOSED assignment, which changes nothing).
        if not was_already_closed:
            safe_cache_delete(f"essay_dashboard:{assignment.id}")

        # Cascade added in Phase 4, per Task 3.2's own note: every
        # IN_PROGRESS attempt under this now-CLOSED assignment is finalized
        # immediately, not left dangling until its own ends_at — mirrors
        # assessment-service's AdminAssignmentCloseView calling
        # finalize_sessions(), reusing the exact same primitive the beat
        # sweep uses, not a separate implementation.
        auto_submitted = finalize_attempts(assignment.attempts.all(), ATTEMPT_STATUS_AUTO_SUBMITTED)

        return success_response(
            data={**EssayAssignmentSerializer(assignment).data, "attempts_auto_submitted": auto_submitted},
            message="Assignment closed",
        )


class AdminEssayAssignmentResyncRosterView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(EssayAssignment, pk=pk, institution_id=institution_id)
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        try:
            new_count = snapshot_roster_and_allocate(assignment, auth_header)
        except RuntimeError as exc:
            return error_response(f"Could not resync roster: {exc}", status_code=502)
        # Phase 10's own dashboard cache — real gap found by that phase's
        # own FOURTH final-audit round: new allocations change
        # total_allocated, which completion_rate_percentage is computed
        # from — only when new_count is actually nonzero, so a resync
        # that finds nothing new to allocate doesn't churn the cache for
        # no reason.
        if new_count:
            safe_cache_delete(f"essay_dashboard:{assignment.id}")
        return success_response(
            data={"new_allocations": new_count}, message="Roster resynced",
        )


# ── Student: Essay-Writing Exam Experience (Phase 4) ────────────────────────
# Mirrors assessment-service's Student{ServerTime,AssignmentList,
# AssignmentStartSession,Answer,Submit}View exactly, adapted for
# essay-service's single-question-per-attempt shape: no per-question
# sub-resource (StudentAnswerView's <qid>) since there is exactly one
# question per attempt — autosave writes EssayAttempt.draft_response
# directly, no separate response model to address by question id.

def _student_attempt_data(attempt):
    return {"attempt_id": str(attempt.id), "ends_at": attempt.ends_at, "status": attempt.status}


class StudentEssayServerTimeView(APIView):
    """GET /api/essay/student/server-time/ — the client's countdown is
    cosmetic only; it renders from this endpoint so client clock drift,
    tampering, or a paused tab never affects what the server will actually
    accept on a write (enforcement.attempt_is_writable() is the real
    enforcement)."""
    permission_classes = [IsStudentUser]

    def get(self, request):
        data = {"server_time": timezone.now()}
        attempt = (
            EssayAttempt.objects.filter(student_id=request.user.id, status=ATTEMPT_STATUS_IN_PROGRESS)
            .order_by("-started_at")
            .first()
        )
        if attempt is not None:
            data["attempt_id"] = str(attempt.id)
            data["ends_at"] = attempt.ends_at
        return success_response(data=data)


class StudentEssayAssignmentListView(APIView):
    """GET /api/essay/student/assignments/ — everything this student has
    been allocated to, gated purely by EssayStudentSetAllocation existing
    (IDOR-safe: filtered by the requesting student's own JWT identity)."""
    permission_classes = [IsStudentUser]

    def get(self, request):
        allocations = (
            EssayStudentSetAllocation.objects.filter(student_id=request.user.id)
            .select_related("assignment__paper", "set")
        )
        assignment_ids = [a.assignment_id for a in allocations]

        attempt_status_by_assignment = dict(
            EssayAttempt.objects.filter(
                student_id=request.user.id, assignment_id__in=assignment_ids,
            ).values_list("assignment_id", "status")
        )

        results = []
        for alloc in allocations:
            assignment = alloc.assignment
            results.append({
                "assignment_id": str(assignment.id),
                "paper_title": assignment.paper.title,
                "status": assignment.status,
                "global_start_time": assignment.global_start_time,
                "global_expire_time": assignment.global_expire_time,
                "attempt_status": attempt_status_by_assignment.get(assignment.id),
                "word_limit": getattr(getattr(alloc.set, "question", None), "word_limit", None),
                "time_limit_minutes": getattr(getattr(alloc.set, "question", None), "time_limit_minutes", None),
            })

        return success_response(data=results)


class StudentEssayAttemptStartView(APIView):
    """POST /api/essay/student/assignments/<id>/start-attempt/ — idempotent
    create-or-resume. A page refresh mid-write calls this again and gets
    the SAME attempt back, same ends_at, never a reset."""
    permission_classes = [IsStudentUser]

    def post(self, request, pk):
        assignment = get_object_or_404(EssayAssignment.objects.select_related("paper"), pk=pk)

        # IDOR + allocation guard, in one query: 404 for both "no such
        # assignment" and "not allocated to it."
        allocation = EssayStudentSetAllocation.objects.filter(
            assignment=assignment, student_id=request.user.id,
        ).select_related("set__question").first()
        if allocation is None:
            return error_response("Assessment not found.", status_code=404)

        existing = EssayAttempt.objects.filter(
            assignment=assignment, student_id=request.user.id,
        ).first()
        if existing is not None:
            return success_response(data=_student_attempt_data(existing), message="Attempt resumed")

        if assignment.status != ASSIGNMENT_STATUS_LIVE:
            return error_response("This assessment is not yet live.", status_code=403)
        if timezone.now() >= assignment.global_expire_time:
            return error_response("This assessment has expired.", status_code=403)

        question = getattr(allocation.set, "question", None)
        if question is None:
            # Should never happen if Task 3.2's readiness gate ran at
            # assignment-creation time — defensive, not the primary guard.
            return error_response("This assessment's prompt is not available.", status_code=409)

        ends_at = min(
            timezone.now() + timedelta(minutes=question.time_limit_minutes),
            assignment.global_expire_time,
        )
        try:
            attempt = EssayAttempt.objects.create(
                assignment=assignment, student_id=request.user.id,
                set=allocation.set, ends_at=ends_at,
            )
        except IntegrityError:
            # Lost a create race against a concurrent request for the same
            # student+assignment (unique_together) — resume from the winner.
            attempt = EssayAttempt.objects.get(assignment=assignment, student_id=request.user.id)
            return success_response(data=_student_attempt_data(attempt), message="Attempt resumed")

        # Phase 10's own dashboard cache — real gap found by that phase's
        # own FOURTH final-audit round: a brand-new attempt is the very
        # FIRST event in the whole pipeline (before any submission exists
        # at all), and changes in_progress_count, a dashboard KPI, on its
        # own — none of the eight hooks already built cover attempt
        # CREATION at all (they're all about later pipeline stages). Only
        # on the genuine create path (status 201), not the "resumed" one
        # above, which doesn't change in_progress_count at all.
        safe_cache_delete(f"essay_dashboard:{assignment.id}")
        return success_response(data=_student_attempt_data(attempt), status_code=201, message="Attempt started")


class StudentEssayAttemptDetailView(APIView):
    """GET /api/essay/student/attempts/<id>/ — the question + this
    student's own current draft, for the exam-taking UI (Task 4.2). Uses
    StudentEssayQuestionSerializer, which never includes llm_rubric_prompt."""
    permission_classes = [IsStudentUser]

    def get(self, request, pk):
        attempt = get_object_or_404(
            EssayAttempt.objects.select_related("set__question"),
            pk=pk, student_id=request.user.id,
        )
        question = getattr(attempt.set, "question", None)
        return success_response(data={
            "attempt_id": str(attempt.id),
            "ends_at": attempt.ends_at,
            "status": attempt.status,
            "draft_response": attempt.draft_response,
            "question": StudentEssayQuestionSerializer(question).data if question else None,
        })


class StudentEssayAutosaveView(APIView):
    """PUT /api/essay/student/attempts/<id>/autosave/ — idempotent draft
    upsert, mirroring assessment-service's StudentAnswerView. No
    per-question sub-resource: exactly one question per attempt, so the
    draft is a direct field on EssayAttempt, not a separate response row
    addressed by question id."""
    permission_classes = [IsStudentUser]
    throttle_classes = [EssayAutosaveRateThrottle]

    def put(self, request, pk):
        attempt = get_object_or_404(
            EssayAttempt.objects.select_related("assignment"), pk=pk, student_id=request.user.id,
        )
        ok, reason = attempt_is_writable(attempt, attempt.assignment)
        if not ok:
            return error_response(reason, status_code=403)

        data = strip_client_timestamps(request.data)
        draft_response = data.get("draft_response", "")
        if not isinstance(draft_response, str):
            return error_response("draft_response must be a string.", status_code=400)

        # Word-limit enforcement is also done client-side (Task 4.2), but
        # the server is the authoritative check — a client bypassing its
        # own UI must not be able to persist an over-limit draft.
        question = getattr(attempt.set, "question", None)
        if question is not None:
            word_count = len(draft_response.split())
            if word_count > question.word_limit:
                return error_response(
                    f"Response exceeds the {question.word_limit}-word limit.", status_code=400,
                )

        attempt.draft_response = draft_response
        attempt.save(update_fields=["draft_response"])
        return success_response(data={"attempt_id": str(attempt.id)}, message="Draft saved")


class StudentEssaySubmitView(APIView):
    """POST /api/essay/student/attempts/<id>/submit/ — final manual
    submit. Reuses finalize_attempts() (Task 4.1) — the exact same
    race-safe primitive the beat sweep and the admin close/ cascade use, so
    a submit racing either of those can never double-finalize or corrupt
    state."""
    permission_classes = [IsStudentUser]
    # All three fail CLOSED (Phase 5) — this is essay-service's one
    # public "submission-creation" entry point (ADR 003 Decision 8 / ADR
    # 004 Section 5). Three distinct scopes, not redundant: a per-minute
    # burst throttle, a per-student hourly ceiling, and a per-institution
    # hourly ceiling.
    throttle_classes = [EssaySubmitRateThrottle, EssaySubmitPerStudentHourlyThrottle, EssaySubmitPerInstitutionHourlyThrottle]

    def post(self, request, pk):
        attempt = get_object_or_404(
            EssayAttempt.objects.select_related("assignment"), pk=pk, student_id=request.user.id,
        )
        ok, reason = attempt_is_writable(attempt, attempt.assignment)
        if not ok:
            return error_response(reason, status_code=403)

        # A final draft_response payload may accompany the submit itself
        # (Task 4.2's "Submit" button sends whatever's currently in the
        # textarea, not just whatever the last autosave happened to catch).
        data = strip_client_timestamps(request.data)
        if "draft_response" in data and isinstance(data["draft_response"], str):
            attempt.draft_response = data["draft_response"]
            attempt.save(update_fields=["draft_response"])

        finalize_attempts(EssayAttempt.objects.filter(pk=attempt.pk), ATTEMPT_STATUS_SUBMITTED)

        attempt.refresh_from_db()
        return success_response(
            data={"attempt_id": str(attempt.id), "status": attempt.status},
            message="Submitted",
        )


_MALPRACTICE_EVENT_TYPES = {c[0] for c in MALPRACTICE_EVENT_TYPE_CHOICES}
_MAX_MALPRACTICE_EVENTS_PER_BATCH = 100


def _parse_occurred_at(raw):
    """Client-reported event time, falling back to server now() if
    missing/unparseable — matches assessment-service's
    ActivityLog.occurred_at convention exactly."""
    if raw:
        dt = parse_datetime(str(raw))
        if dt is not None:
            return dt if timezone.is_aware(dt) else timezone.make_aware(dt, timezone.utc)
    return timezone.now()


class StudentEssayMalpracticeEventBulkCreateView(APIView):
    """POST /api/essay/student/attempts/<id>/malpractice-events/ —
    bulk-insert a batch of client-captured integrity events (Task 4.3),
    mirroring assessment-service's StudentActivityLogBulkCreateView exactly."""
    permission_classes = [IsStudentUser]
    throttle_classes = [EssayMalpracticeEventRateThrottle]

    def post(self, request, pk):
        attempt = get_object_or_404(
            EssayAttempt.objects.select_related("assignment"), pk=pk, student_id=request.user.id,
        )
        ok, reason = attempt_is_writable(attempt, attempt.assignment)
        if not ok:
            return error_response(reason, status_code=403)

        events = request.data.get("events")
        if not isinstance(events, list) or not events:
            return error_response("events must be a non-empty list.", status_code=400)
        if len(events) > _MAX_MALPRACTICE_EVENTS_PER_BATCH:
            return error_response(
                f"Too many events in one batch (max {_MAX_MALPRACTICE_EVENTS_PER_BATCH}).", status_code=400,
            )

        to_create = []
        for e in events:
            if not isinstance(e, dict):
                continue
            event_type = e.get("event_type")
            if event_type not in _MALPRACTICE_EVENT_TYPES:
                continue
            metadata = e.get("metadata")
            to_create.append(EssayMalpracticeEvent(
                attempt=attempt,
                event_type=event_type,
                occurred_at=_parse_occurred_at(e.get("occurred_at")),
                metadata=metadata if isinstance(metadata, dict) else {},
            ))

        if to_create:
            EssayMalpracticeEvent.objects.bulk_create(to_create)

        return success_response(data={"logged": len(to_create)}, status_code=201)


# ── Admin: Submissions Module (Phase 6, Task 6.1) ───────────────────────────
# Reference (verified — actually read, not inferred): CLAP's
# django-backend/api/views/admin/submissions_monitor.py.
#
# Retest handling (this task's own checklist item): explicitly OUT OF
# SCOPE, not silently skipped — ADR 002 Decision 3 already deferred retake
# support platform-wide for V1 (EssayAttempt.unique_together=
# [("assignment", "student_id")] enforces exactly one attempt per student
# per assignment, ever; there is no attempt_number field to increment,
# matching that decision's own accepted tradeoff: "an admin who needs to
# re-issue an essay to one student does so via a normal new assignment").
# Re-litigating that call here, one phase later, isn't this task's job.
#
# Pipeline health widget (this task's own checklist item): simple client
# polling, not Server-Sent Events. CLAP pushes this via SSE every 10s;
# adopting that here would mean holding a long-lived ASGI connection open
# per admin viewer for a widget only a handful of institution admins ever
# have open at once (Task 0.4's own capacity numbers size this service for
# tens-to-low-hundreds of STUDENTS per assignment, not a large concurrent
# admin audience) — SSE's operational cost (connection/worker pressure)
# buys nothing a 10-15s poll interval doesn't already deliver at this
# scale. Not copied reflexively, per this task's own explicit instruction.

_SUBMISSION_STATUS_BUCKETS = {
    "pending":    [SUBMISSION_STATUS_PENDING],
    # Phase 11: REPORT_GENERATING added here — a real gap this phase's own
    # audit found. This bucket dict predates Phase 11 (its own original
    # comment, below, claimed "this service has no REPORT_GENERATING...
    # stage of its own", which Task 11.1 made false the moment it added
    # SUBMISSION_STATUS_REPORT_GENERATING to the model). Without this, a
    # submission transiently in REPORT_GENERATING (normally sub-second —
    # local HTML rendering, not an LLM call) matched NO bucket at all,
    # silently vanishing from both its own count and the overview's
    # "total" sum. Grouped into "processing", matching CLAP's own
    # reference rollup exactly (verified: it collapses LLM_PROCESSING +
    # REPORT_GENERATING + EMAIL_SENDING into "processing" the same way).
    "processing": [SUBMISSION_STATUS_LLM_PROCESSING, SUBMISSION_STATUS_REPORT_GENERATING],
    "completed":  [SUBMISSION_STATUS_LLM_COMPLETE, SUBMISSION_STATUS_REPORT_READY],
    "failed":     [SUBMISSION_STATUS_LLM_FAILED],
}


class AdminSubmissionsOverviewView(APIView):
    """GET /admin/submissions/overview/ — counts bucketed into the 4
    summary states (pending/processing/completed/failed), collapsing
    LLM_COMPLETE + REPORT_READY into "completed" and (as of Phase 11)
    LLM_PROCESSING + REPORT_GENERATING into "processing", the same way
    CLAP's own submission_status_overview rolls up its own finer-grained
    pipeline statuses (verified: that endpoint's own reference collapses
    LLM_PROCESSING + REPORT_GENERATING + EMAIL_SENDING into "processing" —
    this service has no EMAIL_SENDING stage of its own since email sending
    is synchronous within `send_essay_report_email`, not a separate
    tracked pipeline stage, so its own rollup is correspondingly smaller,
    not a partial port)."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        institution_id = _get_institution_id(request)
        qs = EssaySubmission.objects.filter(attempt__assignment__institution_id=institution_id)
        counts = dict(qs.values_list("status").annotate(c=Count("id")).values_list("status", "c"))

        overview = {
            bucket: sum(counts.get(s, 0) for s in statuses)
            for bucket, statuses in _SUBMISSION_STATUS_BUCKETS.items()
        }
        overview["total"] = sum(overview.values())
        return success_response(data=overview)


def _roster_by_uid(batch_ids, auth_header):
    """Best-effort merge of every given batch's roster into one
    {user_id: roster_entry} dict, for the department/student-search
    filters below. Department (and a student's roll number/name) live in
    user-service's roster, not locally — matches assessment-service's own
    documented reasoning for its equivalent admin list filter exactly
    (see that service's views.py, the student-roster admin list).

    Deliberately best-effort, NOT a hard failure like Task 3.1's roster
    snapshot at assignment creation: that's a one-time write that must
    never proceed on incomplete data, this is a read-only browse/filter
    endpoint where one batch's roster call failing should degrade that
    batch's rows out of a department/name filter, not 500 the whole list."""
    merged = {}
    for batch_id in batch_ids:
        try:
            roster = fetch_batch_roster(str(batch_id), auth_header)
        except RuntimeError:
            logger.warning(
                "AdminSubmissionsListView: roster fetch failed for batch %s — "
                "department/student-search filtering may be incomplete for this batch.",
                batch_id,
            )
            continue
        for entry in roster:
            uid = entry.get("user_id")
            if uid:
                merged[str(uid)] = entry
    return merged


class AdminSubmissionsListView(APIView):
    """GET /admin/submissions/ — paginated (30/page, Task 6.1's own
    explicit number), filterable by status (the 4-bucket rollup above, so
    a click-through from the overview widget composes directly), student
    (exact student_id, or a roster-backed free-text roll-number/name
    search), batch, department (roster-backed), and a created_at date
    range."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        institution_id = _get_institution_id(request)
        qs = EssaySubmission.objects.filter(
            attempt__assignment__institution_id=institution_id
        ).select_related("attempt__assignment__paper", "score")

        status_bucket = request.query_params.get("status")
        if status_bucket:
            real_statuses = _SUBMISSION_STATUS_BUCKETS.get(status_bucket.lower())
            if not real_statuses:
                return error_response(
                    f"Unknown status filter: {status_bucket!r}. "
                    f"Expected one of {sorted(_SUBMISSION_STATUS_BUCKETS)}.",
                    status_code=400,
                )
            qs = qs.filter(status__in=real_statuses)

        student_id = request.query_params.get("student_id")
        if student_id:
            try:
                qs = qs.filter(attempt__student_id=student_id)
            except (ValueError, ValidationError):
                return error_response("student_id must be a valid UUID.", status_code=400)

        batch_id = request.query_params.get("batch_id")
        if batch_id:
            try:
                qs = qs.filter(attempt__assignment__batch_id=batch_id)
            except (ValueError, ValidationError):
                return error_response("batch_id must be a valid UUID.", status_code=400)

        # Real gap found by this phase's own final-audit round: unlike
        # student_id/batch_id above, a malformed date string here doesn't
        # raise at .filter() call time — Django defers a date-lookup's
        # value validation to query evaluation, which happens deep inside
        # paginator.paginate_queryset() below, well outside any try/except
        # here. Confirmed live: ?date_from=not-a-date crashed this
        # endpoint with a raw 500 (a leaked Django debug traceback in this
        # dev environment) instead of a clean 400. Fixed by validating the
        # format upfront with parse_date(), before it ever reaches .filter().
        date_from = request.query_params.get("date_from")
        if date_from:
            if parse_date(date_from) is None:
                return error_response("date_from must be a valid date (YYYY-MM-DD).", status_code=400)
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = request.query_params.get("date_to")
        if date_to:
            if parse_date(date_to) is None:
                return error_response("date_to must be a valid date (YYYY-MM-DD).", status_code=400)
            qs = qs.filter(created_at__date__lte=date_to)

        department = (request.query_params.get("department") or "").strip()
        student_search = (request.query_params.get("student_search") or "").strip().lower()
        if department or student_search:
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            # Same .distinct()-defeated-by-default-ordering bug found and
            # fixed in scoring.py's own cache-invalidation loop —
            # EssaySubmission.Meta.ordering (-created_at) silently breaks
            # .distinct() here too, so this was fetching one roster batch
            # per matching submission instead of per genuinely distinct
            # batch_id. order_by() clears the inherited ordering first.
            batch_ids = qs.order_by().values_list("attempt__assignment__batch_id", flat=True).distinct()
            roster = _roster_by_uid(batch_ids, auth_header)
            matching_ids = set(roster.keys())
            if department:
                matching_ids &= {
                    uid for uid, info in roster.items()
                    if (info.get("department") or "").strip().lower() == department.lower()
                }
            if student_search:
                matching_ids &= {
                    uid for uid, info in roster.items()
                    if student_search in (info.get("student_id") or "").lower()
                    or student_search in (info.get("name") or "").lower()
                }
            qs = qs.filter(attempt__student_id__in=matching_ids)

        paginator = SubmissionsListPagination()
        page = paginator.paginate_queryset(qs, request)
        data = EssaySubmissionListSerializer(page, many=True).data
        return paginator.get_paginated_response(data)


class AdminSubmissionDetailView(APIView):
    """GET /admin/submissions/<id>/ — one submission's full detail: the
    essay itself, its score/feedback breakdown if scored, and the full
    chronological EssaySubmissionEvent trail (this task's own audit-log
    requirement — see that model's own docstring)."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        submission = get_object_or_404(
            EssaySubmission.objects.select_related(
                "attempt__assignment__paper", "attempt__set__question", "score", "llm_trace",
            ).prefetch_related("events"),
            pk=pk, attempt__assignment__institution_id=institution_id,
        )
        return success_response(data=EssaySubmissionDetailSerializer(submission).data)


class AdminSubmissionsPipelineHealthView(APIView):
    """GET /admin/submissions/pipeline-health/ — Celery queue depth (Redis
    LLEN on this service's own default queue), unresolved-DLQ count +
    oldest-unresolved age, undispatched-submission count + oldest age (a
    different failure mode — a submission whose dispatch never even
    reached the broker, so it never had the chance to land in the DLQ;
    see undispatched_submissions_snapshot's own docstring, essays/
    notifications.py), and a live Redis/Celery-worker ping.

    Deliberately NOT institution-scoped: EssayFailedJob and the Celery
    queue itself are shared platform infrastructure with no institution_id
    of their own (one worker pool serves every institution's submissions),
    the same way a status page reports on infrastructure, not per-tenant
    data. Every value exposed here is an aggregate count/age, never
    submission content or any identifying student data, so this doesn't
    cross the institution-isolation boundary (ET8) the rest of this
    service's admin endpoints protect — access is still gated behind
    IsAdminOrSuperAdmin, not public."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        from django.conf import settings
        import redis
        from core.celery import app as celery_app

        health = {
            "redis_ok": False,
            "queue_depth": None,
            "celery_workers_online": 0,
            "unresolved_dlq_count": 0,
            "oldest_unresolved_dlq_age_seconds": None,
            "undispatched_submission_count": 0,
            "oldest_undispatched_submission_age_seconds": None,
        }

        try:
            r = redis.from_url(settings.REDIS_URL)
            r.ping()
            health["redis_ok"] = True
            health["queue_depth"] = r.llen(settings.CELERY_TASK_DEFAULT_QUEUE)
        except redis.exceptions.RedisError as exc:
            logger.warning("AdminSubmissionsPipelineHealthView: Redis unreachable: %s", exc)

        try:
            pong = celery_app.control.ping(timeout=1.0) or []
            health["celery_workers_online"] = len(pong)
        except Exception as exc:
            logger.warning("AdminSubmissionsPipelineHealthView: Celery worker ping failed: %s", exc)

        from .notifications import dlq_unresolved_snapshot, undispatched_submissions_snapshot
        health["unresolved_dlq_count"], health["oldest_unresolved_dlq_age_seconds"] = dlq_unresolved_snapshot()
        health["undispatched_submission_count"], health["oldest_undispatched_submission_age_seconds"] = (
            undispatched_submissions_snapshot()
        )
        return success_response(data=health)


# ── Admin: LLM Controls Module (Phase 7, Task 7.1) ──────────────────────────
# Reference (verified — actually read, not inferred): CLAP's
# django-backend/api/views/admin/llm_controls.py. Adapted since this
# service has exactly one LLM domain (writing), not CLAP's writing+speaking
# — "submission status correctly advances only once all required domains
# have a score" (this task's own testing checklist) trivially reduces to
# "advances once the one domain has a score" here.
#
# Deliberately NOT built: any bulk/mass action ("rescore all failed").
# CLAP's own reference only exposes single-submission retrigger, and this
# task's own checklist explicitly names that as the ET11 cost-ceiling
# scenario to avoid without a separate, explicit guardrail decision —
# every view below acts on exactly one submission per request.

class AdminSubmissionRetriggerView(APIView):
    """POST /admin/submissions/<id>/retrigger/ — deletes the existing
    (failed/wrong) score row, transitions status back to LLM_PROCESSING,
    re-dispatches the Celery evaluation task with a fresh inline-retry
    budget, and audit-logs which admin did it and why. A targeted,
    single-submission action — see this module's own note on why no bulk
    variant exists."""
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        submission = get_object_or_404(
            EssaySubmission, pk=pk, attempt__assignment__institution_id=institution_id,
        )
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return error_response("A reason is required to retrigger evaluation.", status_code=400)

        with transaction.atomic():
            # Real gap found by this phase's own final-audit round, in two
            # layers. First: this view previously had no status guard at
            # all, so retriggering a submission that's already
            # LLM_PROCESSING (a genuine in-flight evaluation, not a stale/
            # failed one) dispatched a SECOND, fully concurrent
            # evaluate_essay run — a real, separately-billed OpenAI API
            # call (the ET11 cost class this task's own checklist
            # explicitly names). Second, found while re-checking that
            # first fix under genuine concurrency: a plain
            # `if submission.status == ...` read-then-write check (what
            # this used to be) does NOT close the race between two
            # admins retriggering the SAME LLM_FAILED submission at the
            # same instant — both can read the pre-check status before
            # either commits, then both unconditionally proceed. Fixed
            # properly with a conditional UPDATE (the same CAS pattern
            # this module already uses in _transition_submission_status()
            # and AdminEssayAssignmentStartView) — the actual status
            # transition IS the guard, so only one of any number of
            # concurrent identical-status racers can ever see updated=1.
            # PENDING is deliberately still allowed through: nothing is
            # actually in flight yet, so no duplicate-call risk exists there.
            updated = EssaySubmission.objects.filter(pk=submission.pk).exclude(
                status=SUBMISSION_STATUS_LLM_PROCESSING,
            ).update(status=SUBMISSION_STATUS_LLM_PROCESSING)
            if not updated:
                return error_response(
                    "This submission's evaluation is already in progress. Wait for it to finish before retriggering.",
                    status_code=409,
                )

            # Any prior score/trace is now stale — evaluate_essay's own
            # idempotency check (essays/tasks.py) would otherwise see the
            # existing EssayScore and skip re-evaluating entirely.
            EssayScore.objects.filter(submission=submission).delete()
            EssayLLMTrace.objects.filter(submission=submission).delete()
            EssayFailedJob.objects.filter(
                task_name="evaluate_essay", args=[str(submission.id)], resolved_at__isnull=True,
            ).update(resolved_at=timezone.now())
            EssaySubmissionEvent.objects.create(
                submission=submission, event_type=SUBMISSION_EVENT_ADMIN_RETRIGGER,
                detail="Evaluation manually retriggered by an admin.",
                admin_user_id=request.user.id, reason=reason,
            )

        # Phase 10's own dashboard cache — this view updates
        # submission.status directly (see this method's own note above on
        # why it can't go through _transition_submission_status()'s own
        # CAS), so it's one of the small number of call sites that must
        # invalidate the dashboard cache itself rather than getting it
        # for free from that shared choke point.
        #
        # Real gap found by this phase's own final-audit round: this call
        # was originally INSIDE the atomic() block above, before the
        # transaction actually committed. A concurrent dashboard read
        # landing in that narrow window would recompute from the
        # not-yet-committed (pre-retrigger) DB state and re-cache it —
        # poisoning the cache with stale data for up to the full 300s TTL
        # backstop, precisely the class of staleness this whole
        # invalidation mechanism exists to prevent. Moved to after the
        # block exits, so invalidation only ever happens once the fresh
        # data is genuinely durable and readable by any concurrent request.
        safe_cache_delete(f"essay_dashboard:{submission.attempt.assignment_id}")

        from .tasks import evaluate_essay
        from core.logging_utils import get_request_id
        # Fresh inline_retry_count=0 — this is a brand-new attempt, not a
        # continuation of whatever retry budget the original run exhausted.
        # correlation_id (Task 17.2) — this admin's own retrigger request's
        # id, so the re-run evaluation's log lines trace back to this
        # specific admin action, not the (long-gone) original submission's.
        #
        # Real gap found auditing every .delay() call site in this file
        # against the same broker-unreachable class of bug already fixed
        # in scoring.py: this view set status to LLM_PROCESSING above
        # BEFORE dispatching, so an unhandled crash here (Redis down at
        # this exact moment) would have left the submission stuck at
        # LLM_PROCESSING forever — sweep_undispatched_submissions only
        # ever looks at PENDING, so it would never have found this one.
        # Reverting to LLM_FAILED on a failed dispatch keeps it visible
        # and immediately re-actionable (the admin can just retry this
        # same action) instead of silently stuck in a state nothing
        # recovers from.
        if not safe_task_dispatch(
            evaluate_essay, str(submission.id), correlation_id=get_request_id(),
            context=f"evaluate_essay retrigger for submission {submission.id}",
        ):
            EssaySubmission.objects.filter(pk=submission.pk).update(status=SUBMISSION_STATUS_LLM_FAILED)
            return error_response(
                "Evaluation could not be dispatched right now (task queue unreachable). "
                "The submission has been left in its failed state — try retriggering again shortly.",
                status_code=503,
            )

        return success_response(message="Evaluation retriggered.")


class AdminSubmissionTraceView(APIView):
    """GET /admin/submissions/<id>/trace/ — the exact prompt used, the
    raw LLM response, the request id, and when it was evaluated, for an
    admin diagnosing "why did this essay get this score". A submission
    that never reached a successful LLM call (failed before that point,
    or was manually overridden instead) genuinely has no trace row — this
    endpoint says so plainly rather than fabricating one."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        submission = get_object_or_404(
            EssaySubmission, pk=pk, attempt__assignment__institution_id=institution_id,
        )
        trace = EssayLLMTrace.objects.filter(submission=submission).first()
        if trace is None:
            return success_response(data=None, message="No LLM trace recorded for this submission.")
        return success_response(data=EssayLLMTraceSerializer(trace).data)


class AdminLLMAnalyticsView(APIView):
    """GET /admin/llm-controls/analytics/ — provider/model in use,
    evaluation count + average score, count of DLQ entries specifically
    caused by LLM-response validation failures (malformed JSON / schema
    mismatch — distinguished from other DLQ causes, e.g. a permanent
    provider rejection, by matching on the error message, since
    EssayFailedJob has no separate "cause" enum of its own), and count of
    retrigger requests.

    Evaluation count/average score are institution-scoped — real
    submission data with a clean join to institution via attempt/
    assignment. The DLQ malformed-count is deliberately NOT institution-
    scoped, the same reasoning as AdminSubmissionsPipelineHealthView's own
    docstring above: EssayFailedJob is shared platform infrastructure
    with no institution_id of its own."""
    permission_classes = [IsAdminOrSuperAdmin]

    # The exact LLMMalformedResponseError message prefixes this service's
    # own llm_client.py/tasks.py ever raise (verified by direct code
    # reading, not guessed) — matching on these specific signatures, not a
    # generic "malformed" substring, avoids false-matching an unrelated
    # DLQ entry whose error text happens to mention that word.
    _MALFORMED_ERROR_SIGNATURES = ["Non-JSON LLM response", "Unexpected response shape", "Semantic-consistency guard"]

    def get(self, request):
        from django.conf import settings
        from django.db.models import Avg, Q

        institution_id = _get_institution_id(request)

        scores = EssayScore.objects.filter(submission__attempt__assignment__institution_id=institution_id)
        agg = scores.aggregate(count=Count("id"), avg=Avg("score"))

        malformed_q = Q()
        for sig in self._MALFORMED_ERROR_SIGNATURES:
            malformed_q |= Q(error__icontains=sig)
        malformed_dlq_count = EssayFailedJob.objects.filter(task_name="evaluate_essay").filter(malformed_q).count()

        retrigger_count = EssaySubmissionEvent.objects.filter(
            event_type=SUBMISSION_EVENT_ADMIN_RETRIGGER,
            submission__attempt__assignment__institution_id=institution_id,
        ).count()

        return success_response(data={
            "provider": "OpenAI",
            "model": getattr(settings, "OPENAI_MODEL", "gpt-4o"),
            "evaluation_count": agg["count"] or 0,
            "average_score": round(agg["avg"], 2) if agg["avg"] is not None else None,
            "malformed_response_dlq_count": malformed_dlq_count,
            "retrigger_count": retrigger_count,
        })


class AdminSubmissionScoreOverrideView(APIView):
    """POST /admin/submissions/<id>/override-score/ — the human-in-the-
    loop failure-recovery path for a submission permanently stuck in the
    DLQ: an admin manually enters a score (0-10) + feedback + a mandatory
    reason, which persists as the submission's score (evaluated_by=
    'admin', so it's visibly distinguishable from an LLM-assigned score
    everywhere it's later shown), marks the associated DLQ entry
    resolved, and audit-logs the override. Scoped to the DLQ-recovery
    case specifically (requires the submission to actually be
    LLM_FAILED) — overriding an already-fine score for other reasons
    (a student appeal, a human regrade) is Phase 8's own, deliberately
    separate, broader override path."""
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        submission = get_object_or_404(
            EssaySubmission, pk=pk, attempt__assignment__institution_id=institution_id,
        )

        if submission.status != SUBMISSION_STATUS_LLM_FAILED:
            return error_response(
                "Only a submission stuck in LLM_FAILED can be manually overridden here.", status_code=400,
            )

        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return error_response("A reason is required to override a score.", status_code=400)

        score_raw = request.data.get("score")
        try:
            score = int(score_raw)
        except (TypeError, ValueError):
            return error_response("score must be an integer between 0 and 10.", status_code=400)
        if not (0 <= score <= 10):
            return error_response("score must be between 0 and 10.", status_code=400)

        feedback = request.data.get("feedback")
        if not isinstance(feedback, dict) or not isinstance(feedback.get("overall"), str) or not feedback["overall"].strip():
            return error_response("feedback must include a non-empty 'overall' string.", status_code=400)

        with transaction.atomic():
            # A DLQ-recovery override, not a re-evaluation — any prior
            # (failed/absent) score is replaced outright, matching the
            # retrigger view's own "delete then create fresh" shape.
            EssayScore.objects.filter(submission=submission).delete()
            # Real gap found by this phase's own final-audit round: the
            # status check above and this create() are not atomic with
            # each other across two concurrent requests — two admins
            # racing to override the SAME submission can both read
            # LLM_FAILED before either commits, and EssayScore.submission
            # is a genuine DB-level unique constraint (OneToOneField), so
            # the loser's create() previously raised an unhandled
            # IntegrityError straight through to a raw 500 — the same
            # "leaked debug traceback" class of bug already found and
            # fixed once in Phase 6 (the date_from/date_to case). A
            # nested atomic() (a real savepoint) isolates just this
            # statement's rollback so the caught branch below can still
            # return a clean response instead of poisoning the whole
            # outer transaction.
            try:
                with transaction.atomic():
                    EssayScore.objects.create(
                        submission=submission, score=score, feedback=feedback,
                        is_no_submission=False, evaluated_by=EVALUATED_BY_ADMIN,
                    )
            except IntegrityError:
                return error_response(
                    "This submission was already overridden by another admin just now. "
                    "Refresh the page to see the current score.",
                    status_code=409,
                )
            EssayFailedJob.objects.filter(
                task_name="evaluate_essay", args=[str(submission.id)], resolved_at__isnull=True,
            ).update(resolved_at=timezone.now())
            EssaySubmission.objects.filter(pk=submission.pk).update(status=SUBMISSION_STATUS_LLM_COMPLETE)
            EssaySubmissionEvent.objects.create(
                submission=submission, event_type=SUBMISSION_EVENT_ADMIN_OVERRIDE,
                detail=f"Manual score override: {score}/10.",
                admin_user_id=request.user.id, reason=reason,
            )

        # Phase 10's own dashboard cache — this view updates
        # submission.status directly, bypassing
        # _transition_submission_status()'s own choke point, so it must
        # invalidate the dashboard cache itself. Real gap found by this
        # phase's own final-audit round, same as the Retrigger view's
        # own identical fix: moved to AFTER the atomic() block exits, not
        # inside it — invalidating before the transaction actually
        # commits let a concurrent read re-cache stale, pre-override data
        # for up to the full 300s TTL backstop.
        safe_cache_delete(f"essay_dashboard:{submission.attempt.assignment_id}")

        # Phase 11: real gap found while auditing every write path to
        # LLM_COMPLETE, the same systematic sweep Phase 10 already applied
        # to the dashboard cache — this view is the one OTHER place (besides
        # evaluate_essay's own three call sites, all funneled through
        # _transition_submission_status()) a submission can reach
        # LLM_COMPLETE for the first time. Without this, a DLQ-recovered
        # submission would never get a report at all — every other path to
        # LLM_COMPLETE gets one automatically, and an admin has no reason to
        # expect this one bypass to behave differently. Dispatched here,
        # after the block exits, not via _transition_submission_status()
        # (which would fire from inside the atomic() block above — the
        # same "dispatch after commit" hazard AdminReportRegenerateView's
        # own docstring explains).
        from .tasks import generate_essay_report
        # Real gap found auditing every .delay() call site against the
        # same broker-unreachable class of bug already fixed in
        # scoring.py: the score override above has already committed —
        # that's the part that actually matters and must not be lost or
        # reported as failed. If report generation itself can't be
        # dispatched right now, the submission simply stays at
        # LLM_COMPLETE with report_html still null (generate_essay_report's
        # own CAS handles every later status transition, so nothing here
        # needs to be reverted) — sweep_undispatched_submissions
        # (essays/tasks.py) now also scans for exactly this state and
        # redispatches it automatically, the same self-heal already proven
        # for the PENDING case.
        report_dispatched = safe_task_dispatch(
            generate_essay_report, str(submission.id),
            context=f"generate_essay_report after override for submission {submission.id}",
        )

        fresh = EssaySubmission.objects.select_related(
            "attempt__assignment__paper", "attempt__set__question", "score", "llm_trace",
        ).prefetch_related("events").get(pk=submission.pk)
        message = "Score overridden." if report_dispatched else (
            "Score overridden. Report generation could not be dispatched right now and will be retried automatically."
        )
        return success_response(data=EssaySubmissionDetailSerializer(fresh).data, message=message)


# ── Admin: Results Module (Phase 8, Task 8.1) ───────────────────────────────
# Reference: assessment-service's own AdminAssignmentResultsView/
# AdminAssignmentResultsExportView (assessments/views.py) — a per-assignment
# outcomes table, anchored on the ROSTER SNAPSHOT (EssayStudentSetAllocation,
# Task 3.1), not on EssaySubmission, so every allocated student has a row
# from the moment the assignment exists — a submission-anchored table would
# make every not-yet-submitted student invisible. Distinct in scope from
# Phase 6's Submissions Module, which is a platform-wide PIPELINE monitor
# across every assignment; Results is deliberately "drill into one
# assignment's per-student outcomes", matching the Essay Writing landing
# page's own pre-existing module description ("Per-student scores and LLM
# feedback for a specific assignment") and this platform's own established
# Results-module shape.
#
# Unlike assessment-service's own subquery-annotated queryset (which pulls
# JSONField values — malpractice_reasons/feedback — through Subquery
# annotations), this service's Results view deliberately does the
# attempt/submission/score ENRICHMENT in plain Python after a cheap,
# DB-paginated allocation query, not via Subquery: this test suite runs
# against SQLite (core/test_settings.py) while the real deployment is
# Postgres, and Subquery-through-JSONField portability across the two is a
# real, avoidable risk for zero benefit at this scale (Task 0.4's own
# capacity numbers size this at tens-to-low-hundreds of students per
# assignment) — two queries per page load (the allocation page, then one
# batched attempt/submission/score fetch for just that page's student_ids)
# is simpler, fully portable, and no slower than a subquery approach would
# be at this row count.

def _essay_result_exam_status(attempt, submission):
    """pending (no attempt) / writing (attempt in progress) / else the
    submission's own 4-bucket pipeline status (Phase 6's own
    _SUBMISSION_STATUS_BUCKETS, reused here rather than a parallel enum) —
    a genuinely different question from EssaySubmission.status alone,
    since a student who simply hasn't started yet has no submission (and
    no attempt) at all."""
    if attempt is None:
        return "pending"
    if attempt.status == ATTEMPT_STATUS_IN_PROGRESS:
        return "writing"
    if submission is None:
        # Attempt finalized but the submission row hasn't appeared yet —
        # scoring.py's own orphan-repair self-heals this on the next
        # finalize_attempts() pass; genuinely momentary, not a stuck state.
        return "processing"
    for bucket, statuses in _SUBMISSION_STATUS_BUCKETS.items():
        if submission.status in statuses:
            return bucket
    return "processing"


def _fetch_essay_roster_lookup(assignment, request):
    """Returns {user_id_str: roster_dict}, or raises RuntimeError (both
    Results views below convert this to a 502) — deliberately NOT
    _roster_by_uid (Phase 6's own helper), which silently swallows a
    roster-fetch failure and degrades to an empty/partial lookup for its
    own best-effort filter-only use case. Here, a student's name/roll
    number is core to what each Results row even means, not an optional
    filter enhancement — matching assessment-service's own identically-
    shaped _fetch_roster_lookup precedent exactly."""
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    roster = fetch_batch_roster(str(assignment.batch_id), auth_header)
    return {str(s["user_id"]): s for s in roster if s.get("user_id")}


def _build_essay_results_queryset(assignment, request, roster_by_user_id):
    """Shared between the table view and the CSV export — the exact same
    filters must apply to both, matching this task's own "export button
    must never silently disagree with the filtered table" requirement
    (mirroring assessment-service's identically-named helper's own
    docstring)."""
    qs = EssayStudentSetAllocation.objects.filter(assignment=assignment).select_related("set__question")

    department = (request.query_params.get("department") or "").strip()
    student_search = (request.query_params.get("student_search") or "").strip().lower()
    if department or student_search:
        matching_ids = set(roster_by_user_id.keys())
        if department:
            matching_ids &= {
                uid for uid, info in roster_by_user_id.items()
                if (info.get("department") or "").strip().lower() == department.lower()
            }
        if student_search:
            matching_ids &= {
                uid for uid, info in roster_by_user_id.items()
                if student_search in (info.get("student_id") or "").lower()
                or student_search in (info.get("name") or "").lower()
            }
        qs = qs.filter(student_id__in=matching_ids)

    # "flagged" needs its own lookup (EssayAttempt.malpractice_flag doesn't
    # live on EssayStudentSetAllocation) — same "fetch matching ids from
    # elsewhere, then student_id__in=" shape as the roster filters above.
    #
    # Real gap found by this phase's own final-audit round: filtering the
    # false/"not flagged" branch by student_id__in=[ids with
    # malpractice_flag=False] silently dropped every student with NO
    # EssayAttempt at all (not yet started) — they have no such row to
    # match, so they'd vanish from a "not flagged" result even though
    # nothing has happened for them yet, which trivially means "not
    # flagged". This is the exact same false-branch pitfall
    # assessment-service's own _build_results_queryset (verified, already
    # read) explicitly documents fixing with a Q(...)|Q(isnull=True) OR —
    # here, always computing the DEFINITELY-flagged id set and excluding
    # it (rather than trying to include the definitely-not-flagged set)
    # achieves the same correctness more simply, since every allocated
    # student not in that exclude set — attempted-and-clean or never
    # started at all — is correctly "not flagged" either way.
    flagged_param = request.query_params.get("flagged")
    if flagged_param is not None:
        flagged_ids = list(EssayAttempt.objects.filter(
            assignment=assignment, malpractice_flag=True,
        ).values_list("student_id", flat=True))
        if str(flagged_param).lower() in ("true", "1"):
            qs = qs.filter(student_id__in=flagged_ids)
        elif str(flagged_param).lower() in ("false", "0"):
            qs = qs.exclude(student_id__in=flagged_ids)

    return qs.order_by("student_id")  # deterministic — stable across pages


def _serialize_essay_results_page(allocations, assignment, roster_by_user_id):
    """Batched enrichment for one page (or the full export) of allocation
    rows: exactly one extra query for every attempt/submission/score in
    this batch, keyed by student_id — never one query per row."""
    student_ids = [a.student_id for a in allocations]
    attempts_by_student = {
        a.student_id: a
        for a in EssayAttempt.objects.filter(
            assignment=assignment, student_id__in=student_ids,
        ).select_related("submission__score")
    }

    rows = []
    for alloc in allocations:
        info = roster_by_user_id.get(str(alloc.student_id), {})
        attempt = attempts_by_student.get(alloc.student_id)
        submission = getattr(attempt, "submission", None) if attempt is not None else None
        score = getattr(submission, "score", None) if submission is not None else None
        question = getattr(alloc.set, "question", None)
        malpractice_reasons = attempt.malpractice_reasons if attempt is not None else []

        rows.append({
            "student_user_id": str(alloc.student_id),
            "student_roll_id": info.get("student_id", ""),
            "student_name": info.get("name") or "Unknown",
            "department": info.get("department") or "",
            "set_label": alloc.set.label,
            "question_text": question.question_text if question is not None else "",
            "attempt_id": str(attempt.id) if attempt is not None else None,
            "submission_id": str(submission.id) if submission is not None else None,
            "exam_status": _essay_result_exam_status(attempt, submission),
            "submitted_at": submission.created_at if submission is not None else None,
            "score": score.score if score is not None else None,
            "feedback": score.feedback if score is not None else None,
            "evaluated_by": score.evaluated_by if score is not None else None,
            "malpractice_flag": bool(attempt.malpractice_flag) if attempt is not None else False,
            "malpractice_reasons": malpractice_reasons,
            "plagiarism_flag": MALPRACTICE_EVENT_TEXT_SIMILARITY in malpractice_reasons,
        })
    return rows


class AdminEssayAssignmentResultsView(APIView):
    """GET /admin/assignments/<id>/results/ — the per-assignment outcomes
    table: one row per allocated student (Phase 3's own roster snapshot),
    with score/feedback/malpractice/plagiarism data joined in once that
    student has actually submitted. A roster-fetch failure fails this
    request outright (502), unlike Phase 6's own best-effort department
    filter — here, the student's own name/roll number is core to what
    each row even means, not an optional filter enhancement, matching
    assessment-service's own identical precedent for its Results view."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(EssayAssignment, pk=pk, institution_id=institution_id)

        try:
            roster_by_user_id = _fetch_essay_roster_lookup(assignment, request)
        except RuntimeError as exc:
            return error_response(f"Could not load student roster: {exc}", status_code=502)

        qs = _build_essay_results_queryset(assignment, request, roster_by_user_id)
        paginator = SubmissionsListPagination()
        page = paginator.paginate_queryset(qs, request)
        rows = _serialize_essay_results_page(page, assignment, roster_by_user_id)
        return paginator.get_paginated_response(rows)


class _Echo:
    """A file-like object that just returns what it's given — the standard
    Django pattern for csv.writer to stream rows through
    StreamingHttpResponse instead of materializing the whole CSV in
    memory (matches assessment-service's own identically-named helper)."""
    def write(self, value):
        return value


_RESULTS_EXPORT_HEADER = [
    "Student Roll No", "Student Name", "Department", "Set", "Question", "Exam Status",
    "Submitted At", "Score", "Feedback", "Flagged", "Plagiarism Flag", "Evaluated By",
]


def _export_essay_result_rows(assignment, request, roster_by_user_id):
    writer = csv.writer(_Echo())
    yield "﻿"  # UTF-8 BOM — matches BulkImportModal.tsx's existing Excel-compatibility convention
    yield writer.writerow(_RESULTS_EXPORT_HEADER)

    qs = _build_essay_results_queryset(assignment, request, roster_by_user_id)
    # Chunked, not one _serialize_essay_results_page() call for the whole
    # assignment — keeps the per-batch enrichment query bounded even for
    # an assignment at the very top of this service's own capacity target,
    # rather than materializing every attempt/submission/score at once.
    batch = []
    for alloc in qs.iterator(chunk_size=200):
        batch.append(alloc)
        if len(batch) == 200:
            for row in _serialize_essay_results_page(batch, assignment, roster_by_user_id):
                yield writer.writerow(_essay_result_csv_row(row))
            batch = []
    if batch:
        for row in _serialize_essay_results_page(batch, assignment, roster_by_user_id):
            yield writer.writerow(_essay_result_csv_row(row))


def _essay_result_csv_row(row):
    return [
        row["student_roll_id"],
        row["student_name"],
        row["department"],
        row["set_label"],
        row["question_text"],
        row["exam_status"],
        row["submitted_at"].isoformat() if row["submitted_at"] is not None else "",
        row["score"] if row["score"] is not None else "",
        (row["feedback"] or {}).get("overall", ""),
        "Yes" if row["malpractice_flag"] else "No",
        "Yes" if row["plagiarism_flag"] else "No",
        row["evaluated_by"] or "",
    ]


class AdminEssayAssignmentResultsExportView(APIView):
    """GET /admin/assignments/<id>/results/export/ — StreamingHttpResponse
    so a large export never holds the full result set in memory
    server-side. Built from the exact same _build_essay_results_queryset
    helper as the table view above, so a filtered table and its export
    button never silently disagree."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(EssayAssignment, pk=pk, institution_id=institution_id)

        try:
            roster_by_user_id = _fetch_essay_roster_lookup(assignment, request)
        except RuntimeError as exc:
            return error_response(f"Could not load student roster: {exc}", status_code=502)

        response = StreamingHttpResponse(
            _export_essay_result_rows(assignment, request, roster_by_user_id),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = f'attachment; filename="essay_results_{assignment.id}.csv"'
        return response


class AdminSubmissionGeneralScoreOverrideView(APIView):
    """POST /admin/submissions/<id>/general-override-score/ — Task 8.1's
    own "General score override", distinct from Phase 7's
    AdminSubmissionScoreOverrideView: that one is a DLQ-recovery path,
    scoped to submissions permanently stuck at LLM_FAILED with no score
    at all. This one is the opposite precondition — CORRECTING a score
    that already exists (a student appeal, a human regrade decision) —
    and can be used on a submission in any status that already has one.

    Verified from CLAP's admin/score_management.py::override_score:
    row-locks both rows, a mandatory reason (<=500 chars), a 0-10-bounded
    score, marks evaluated_by='admin', audit-logs old score -> new score
    -> reason, and returns the freshly-committed DB value rather than
    echoing the request back unverified. Uses select_for_update() —
    genuinely new to this codebase (essay-service's own Phase 7 override
    instead uses a savepoint + IntegrityError catch, since THAT hazard is
    a duplicate CREATE on a first-ever score; this one is a lost-update
    race between two admins independently correcting an ALREADY-EXISTING
    row, the textbook case select_for_update() exists for — CLAP's own
    reference already uses it for exactly this reason, not adopted here
    by reflex).

    Phase 11: deliberately does NOT touch report state. If this
    submission already has a REPORT_READY report, correcting the score
    here leaves that report showing the OLD score/feedback until an
    admin explicitly regenerates it (AdminReportRegenerateView) — not
    auto-chained, because doing so safely would need the exact same
    "dispatch after commit, not before" care as that view's own CAS
    reset (this view's own transaction.atomic() block below would
    otherwise dispatch generate_essay_report before the correction
    itself is durable), for a corner case Task 11.1's own regenerate
    action already covers manually. Unlike the Phase 7 DLQ-recovery
    override (AdminSubmissionScoreOverrideView), which auto-dispatches
    because it's the submission's OWN FIRST arrival at LLM_COMPLETE, this
    view corrects an EXISTING score — the two are genuinely different
    cases, not an inconsistency."""
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        submission = get_object_or_404(
            EssaySubmission, pk=pk, attempt__assignment__institution_id=institution_id,
        )

        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return error_response("A reason is required to override a score.", status_code=400)
        if len(reason) > 500:
            return error_response("Reason must be 500 characters or fewer.", status_code=400)

        score_raw = request.data.get("score")
        try:
            new_score = int(score_raw)
        except (TypeError, ValueError):
            return error_response("score must be an integer between 0 and 10.", status_code=400)
        if not (0 <= new_score <= 10):
            return error_response("score must be between 0 and 10.", status_code=400)

        feedback = request.data.get("feedback")
        if not isinstance(feedback, dict) or not isinstance(feedback.get("overall"), str) or not feedback["overall"].strip():
            return error_response("feedback must include a non-empty 'overall' string.", status_code=400)

        with transaction.atomic():
            # select_for_update() on both rows — see this view's own
            # docstring for why this is the right tool here, unlike Phase
            # 7's sibling override. Locking the submission row too (not
            # just the score row) keeps this consistent with every other
            # write path in this file, which always reasons about
            # "submission" as the unit of contention.
            locked_submission = EssaySubmission.objects.select_for_update().get(pk=submission.pk)
            try:
                locked_score = EssayScore.objects.select_for_update().get(submission=locked_submission)
            except EssayScore.DoesNotExist:
                return error_response(
                    "This submission has no score yet to override — use retrigger or the "
                    "DLQ-recovery override instead.",
                    status_code=400,
                )

            old_score = locked_score.score
            locked_score.score = new_score
            locked_score.feedback = feedback
            locked_score.evaluated_by = EVALUATED_BY_ADMIN
            # Real gap found by this phase's own final-audit round: an
            # admin-entered correction always represents a real, deliberate
            # judgment call — never leave is_no_submission=True standing
            # after one, or a corrected score (e.g. an admin discovering
            # the student's response WAS captured, or granting credit on
            # appeal) would silently keep reading as "never wrote
            # anything" to any future consumer of that flag (its own
            # model docstring names Results/Analytics as exactly that
            # consumer) — the same reasoning Phase 7's own sibling
            # override already applies on its own create() path
            # (is_no_submission=False), just missing here since this is
            # an update, not a create.
            locked_score.is_no_submission = False
            locked_score.save(update_fields=["score", "feedback", "evaluated_by", "is_no_submission"])

            EssaySubmissionEvent.objects.create(
                submission=locked_submission, event_type=SUBMISSION_EVENT_ADMIN_OVERRIDE,
                detail=f"General score override: {old_score}/10 -> {new_score}/10.",
                admin_user_id=request.user.id, reason=reason,
            )

        # Phase 10's own dashboard cache — this view never touches
        # submission.status (its whole precondition is that a score
        # already exists), so it's not a "bypasses the automatic choke
        # point" case the way Retrigger/the DLQ override are. It still
        # needs its own invalidation call: correcting a score changes
        # average_score, a dashboard KPI, with no status transition
        # alongside it for _transition_submission_status() to have ever
        # covered. Moved to after the atomic() block exits (same fix as
        # the two sibling overrides above, found by this phase's own
        # final-audit round) — invalidating before the transaction
        # commits let a concurrent read re-cache stale, pre-correction
        # data for up to the full 300s TTL backstop.
        safe_cache_delete(f"essay_dashboard:{locked_submission.attempt.assignment_id}")

        fresh = EssaySubmission.objects.select_related(
            "attempt__assignment__paper", "attempt__set__question", "score", "llm_trace",
        ).prefetch_related("events").get(pk=submission.pk)
        return success_response(data=EssaySubmissionDetailSerializer(fresh).data, message="Score overridden.")


# ── Admin: Analytics Module (Phase 9, Task 9.1) ─────────────────────────────
# Reference: assessment-service's own AdminAssignmentAnalyticsView
# (assessments/views.py) — metrics swapped for essay-relevant ones (score
# distribution, average word count vs. score, weakest rubric criterion,
# plagiarism-flag rate, LLM-failure rate), not that service's MCQ-specific
# per-question-difficulty/pass-fail-cutoff shape, which doesn't apply here.
#
# **Correction to this tracker's own Task 9.1 text, made before writing any
# code against it — the same discipline ADR 003's own false-attribution
# correction (Phase 5) already established for this project:** Task 9.1
# says to reuse "assessment-service's cache-invalidation-hook pattern...
# per that service's own documented reasoning for why TTL alone was
# insufficient." A direct re-read of assessment-service's actual Analytics
# view (verified, not assumed) found the opposite: its own comment reads
# "short TTL — not submission-triggered invalidation like Task 9.1's
# dashboard; a stale window of up to 60s is an accepted tradeoff here."
# The explicit-invalidation pattern belongs to THAT service's own DASHBOARD
# view (a live-watched-during-an-exam screen), not its Analytics view (a
# post-hoc deep-dive) — two genuinely different modules in that codebase,
# not one. Essay-service's own Dashboard is a separate, later phase
# (Phase 10) with its own live-KPI requirement; this one is the same
# after-the-fact deep-dive assessment-service's Analytics already is, at an
# even smaller scale (Task 0.4's own capacity numbers). Built with the
# SAME plain 60s TTL and SAME reasoning as the verified reference, not the
# inaccurate instruction — not a shortcut, the technically correct choice
# already validated in this platform's own code.

ESSAY_ANALYTICS_CACHE_TTL_SECONDS = 60

_WEAK_CRITERION_THRESHOLD = 0.6  # a criterion scoring under 60% of its own maxScore counts as "weak" for this one submission

_ESSAY_METRIC_DEFINITIONS = {
    "score_distribution": "Number of scored submissions at each score 0-10.",
    "average_score": "Mean score across every scored submission for this assignment.",
    "word_count_vs_score": "Average word count of the submitted essay (attempt.draft_response), grouped by the score it received — only scores with at least one submission are included.",
    "weakest_criterion": "Among every rubric criterion the LLM has ever named in this assignment's own score breakdowns, the one most often scored under 60% of its own maxScore. Criterion names are the LLM's own free text, driven by each question's admin-authored rubric — this is a best-effort signal across a single assignment's own questions, not a fixed taxonomy, and multiple sets with different rubrics can genuinely surface different-sounding criteria.",
    "plagiarism_flag_rate_percentage": "Percentage of submitted attempts (terminal status) flagged for text similarity by the plagiarism check (Task 5.4) — students who haven't submitted yet are excluded from this rate's own denominator, since they were never eligible for the check.",
    "llm_failure_rate_percentage": "Percentage of submitted attempts (the same total_submitted population shown above, and shared with plagiarism_flag_rate_percentage) whose evaluation ended up permanently LLM_FAILED.",
}


def _essay_score_distribution(score_rows):
    counts = {i: 0 for i in range(11)}
    for score, _word_count in score_rows:
        if score in counts:
            counts[score] += 1
    return [{"score": i, "count": counts[i]} for i in range(11)]


def _essay_word_count_vs_score(score_rows):
    totals: dict = {}
    for score, draft_response in score_rows:
        entry = totals.setdefault(score, {"word_count_sum": 0, "count": 0})
        entry["word_count_sum"] += len((draft_response or "").split())
        entry["count"] += 1
    return [
        {"score": score, "average_word_count": round(entry["word_count_sum"] / entry["count"], 1), "count": entry["count"]}
        for score, entry in sorted(totals.items())
    ]


def _essay_weakest_criterion(feedback_rows):
    stats: dict = {}
    for feedback in feedback_rows:
        breakdown = (feedback or {}).get("breakdown")
        if not isinstance(breakdown, dict):
            continue
        for name, entry in breakdown.items():
            if not isinstance(entry, dict):
                continue
            entry_score, max_score = entry.get("score"), entry.get("maxScore")
            if not isinstance(entry_score, (int, float)) or not isinstance(max_score, (int, float)) or max_score <= 0:
                continue
            s = stats.setdefault(name, {"total": 0, "weak": 0})
            s["total"] += 1
            if entry_score < max_score * _WEAK_CRITERION_THRESHOLD:
                s["weak"] += 1
    if not stats:
        return None
    # Real gap found by this phase's own final-audit round: max() alone
    # has no tie-break, and feedback_rows comes from a query with no
    # .order_by() — SQL gives no ordering guarantee absent one, so on a
    # genuine tie between two criteria's own weak counts, which one
    # "wins" was not guaranteed to be stable across different cache-miss
    # recomputations even with completely unchanged underlying data. An
    # admin could refresh after the 60s cache expires and see a
    # different "weakest criterion" purely from this, not from anything
    # that actually happened. Fixed with an explicit, deterministic
    # tie-break: highest weak_count, then highest total_count (more data
    # behind the signal), then alphabetically first — the same value
    # every time, for the same underlying data, regardless of query
    # return order.
    name, s = sorted(stats.items(), key=lambda kv: (-kv[1]["weak"], -kv[1]["total"], kv[0]))[0]
    if s["weak"] == 0:
        return None  # every criterion in this assignment is doing fine — nothing to name as "weakest"
    return {
        "name": name, "weak_count": s["weak"], "total_count": s["total"],
        "weak_rate_percentage": round(s["weak"] / s["total"] * 100, 2),
    }


def _compute_essay_analytics(assignment):
    total_allocated = EssayStudentSetAllocation.objects.filter(assignment=assignment).count()
    total_submitted = EssayAttempt.objects.filter(assignment=assignment, status__in=ATTEMPT_TERMINAL_STATUSES).count()

    score_rows = list(EssayScore.objects.filter(
        submission__attempt__assignment=assignment,
    ).values_list("score", "submission__attempt__draft_response"))
    feedback_rows = EssayScore.objects.filter(
        submission__attempt__assignment=assignment,
    ).values_list("feedback", flat=True)

    plagiarism_reasons = EssayAttempt.objects.filter(
        assignment=assignment, status__in=ATTEMPT_TERMINAL_STATUSES,
    ).values_list("malpractice_reasons", flat=True)
    plagiarism_flagged = sum(1 for reasons in plagiarism_reasons if MALPRACTICE_EVENT_TEXT_SIMILARITY in (reasons or []))

    # Real gap found by this phase's own third final-audit round:
    # llm_failure_rate_percentage used to divide by a SEPARATE
    # EssaySubmission-based count that was never itself exposed anywhere
    # in this response — an admin could see "LLM failure rate: 5%" with
    # no visible denominator at all, unlike plagiarism_flag_rate_
    # percentage right next to it, which shares its own denominator
    # (total_submitted) with the already-visible Submitted stat tile.
    # Unified onto the SAME total_submitted denominator both rate
    # metrics — and the page's own visible stat tile — now share: the
    # two counts were already equal except for a momentary, self-healing
    # orphan-repair window (scoring.py) analytics already tolerates by
    # design (up to 60s of staleness, see this view's own docstring), so
    # nothing is lost by using one consistent, visible population for
    # both rates instead of two subtly-different, only-one-of-which-
    # visible ones.
    llm_failed = EssaySubmission.objects.filter(attempt__assignment=assignment, status=SUBMISSION_STATUS_LLM_FAILED).count()

    return {
        "assignment_id": str(assignment.id),
        # Computed once, here, and cached alongside the rest of this
        # payload — so it truthfully reflects when these numbers were
        # computed even when served from the 60s cache, matching
        # assessment-service's own identical reasoning.
        "generated_at": timezone.now().isoformat(),
        "total_allocated": total_allocated,
        "total_submitted": total_submitted,
        "total_scored": len(score_rows),
        "average_score": round(sum(s for s, _ in score_rows) / len(score_rows), 2) if score_rows else None,
        "score_distribution": _essay_score_distribution(score_rows),
        "word_count_vs_score": _essay_word_count_vs_score(score_rows),
        "weakest_criterion": _essay_weakest_criterion(feedback_rows),
        "plagiarism_flag_rate_percentage": round(plagiarism_flagged / total_submitted * 100, 2) if total_submitted else 0.0,
        "llm_failure_rate_percentage": round(llm_failed / total_submitted * 100, 2) if total_submitted else 0.0,
        "metric_definitions": _ESSAY_METRIC_DEFINITIONS,
    }


class AdminEssayAssignmentAnalyticsView(APIView):
    """GET /admin/assignments/<id>/analytics/ — Redis-cached (60s TTL,
    matching assessment-service's own verified Analytics precedent — see
    this module's own header comment for the correction this makes to
    Task 9.1's literal text). safe_cache_get/set degrade to a cache-miss/
    no-op if Redis is unavailable, matching this service's own established
    core/cache_utils.py convention — a Redis outage must make this view
    slower (direct computation every time), never break it outright."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(EssayAssignment, pk=pk, institution_id=institution_id)

        # Real gap found by this phase's own final-audit round: this
        # page's own frontend "Refresh" button called this same endpoint
        # with no way to bypass the cache, so it could silently re-serve
        # the exact same stale data with zero indication — a genuine
        # inconsistency with the LLM Controls page's own "Refresh" button
        # (Phase 7), which is always fresh since that page has no cache
        # at all. `?refresh=true` gives this button real meaning without
        # weakening the cache for every OTHER (uncached, normal) request
        # — still writes the freshly-computed value back to cache
        # afterward, so the next ordinary load still benefits.
        force_refresh = str(request.query_params.get("refresh", "")).lower() in ("true", "1")
        cache_key = f"essay_analytics:{assignment.id}"
        if not force_refresh:
            cached = safe_cache_get(cache_key)
            if cached is not None:
                return success_response(data=cached)

        data = _compute_essay_analytics(assignment)
        safe_cache_set(cache_key, data, ESSAY_ANALYTICS_CACHE_TTL_SECONDS)
        return success_response(data=data)


# ── Admin: Dashboard Module (Phase 10, Task 10.1) ───────────────────────────
# Reference: assessment-service's own AdminAssignmentDashboardView
# (assessments/views.py) — a live-status operational view, genuinely
# distinct from Phase 9's own Analytics (a post-hoc deep-dive): this one
# answers "is anything broken or backed up RIGHT NOW, while the exam is
# live", not "how did students do" (that's Analytics' own job, kept
# deliberately separate — see assessment-service's own 2026-08-18 KPI-
# overlap audit for the precedent this follows).
#
# Unlike Phase 9's Analytics (corrected to a plain 60s TTL, matching that
# module's own verified real-world behavior), THIS is genuinely the case
# assessment-service's own explicit-invalidation pattern exists for — a
# live-watched-during-an-exam screen needs to be accurate, not merely
# eventually-consistent within a minute. Belt-and-suspenders, matching
# assessment-service's own exact design: a 300s TTL as a defensive
# backstop ONLY (in case an invalidation call is ever missed by a future
# change), not the real freshness guarantee — that's the explicit
# safe_cache_delete() calls, at every place a dashboard KPI can change —
# ELEVEN hook sites in total now, found across four separate final-audit
# rounds, not designed complete up front:
#   1. _transition_submission_status() (essays/tasks.py) — the automatic
#      pipeline's own single choke point, covers evaluate_essay's status
#      transitions (PENDING -> LLM_PROCESSING -> LLM_COMPLETE/LLM_FAILED).
#   2. AdminSubmissionRetriggerView — updates status directly (its own CAS
#      guard, not this choke point), so it invalidates itself.
#   3. AdminSubmissionScoreOverrideView (Phase 7, DLQ-recovery) — same
#      reason as #2.
#   4. AdminSubmissionGeneralScoreOverrideView (Phase 8) — never touches
#      status at all, but DOES change average_score, a dashboard KPI with
#      no status transition alongside it for #1 to have ever covered.
#   5. _create_and_dispatch_submissions() (essays/scoring.py) — real gap
#      found by this phase's own FIRST final-audit round: the single
#      shared primitive EVERY new-submission path funnels through (a
#      normal manual submit, the beat sweep's own auto-submit, an admin
#      close/ cascade, and the orphan-repair self-heal). A new submission
#      changes total_submitted/completion_rate_percentage/in_progress_
#      count — the single most common real-world event a live dashboard
#      exists to show, and the one path none of the original four hooks
#      covered at all.
#   6. AdminEssayAssignmentStartView — real gap found by this phase's own
#      SECOND final-audit round: changes EssayAssignment.status directly
#      (SCHEDULED -> LIVE), which assignment_status/time_remaining_seconds
#      read straight from — none of #1-5 touch EssayAssignment.status at
#      all, they're all about EssaySubmission.
#   7. AdminEssayAssignmentCloseView — same reason as #6 (LIVE -> CLOSED).
#      The cascade this view already runs (finalize_attempts(), which
#      reaches #5) only invalidates when at least one attempt actually
#      gets auto-submitted — the common case of closing an assignment
#      with zero students still IN_PROGRESS silently skipped invalidation
#      entirely, leaving the dashboard claiming "LIVE" with a ticking
#      clock for up to 300s after the exam had genuinely already ended.
#   8. sweep_expired_assignments() (essays/tasks.py) — real gap found by
#      this phase's own THIRD final-audit round: the AUTOMATIC, time-based
#      path an exam most commonly actually ends through (its own time
#      simply running out) — likely the majority case, not the exception,
#      against #6/#7's own admin-initiated equivalents. Same underlying
#      "changes EssayAssignment.status, none of #1-5 cover it" gap class,
#      just via the beat schedule this time, not a manual admin click.
#   9. StudentEssayAttemptStartView — real gap found by this phase's own
#      FOURTH final-audit round: a brand-new attempt is the very FIRST
#      event in the whole pipeline, before any submission exists at all,
#      and changes in_progress_count on its own — none of #1-8 cover
#      attempt CREATION, only later pipeline stages.
#  10. AdminEssayAssignmentResyncRosterView — same round's own finding:
#      new EssayStudentSetAllocation rows change total_allocated, which
#      completion_rate_percentage is computed from.
#  11. sweep_dlq_entries() (essays/tasks.py) — same round's own finding:
#      both its self-heal branch (a DLQ entry found already scored by an
#      earlier retry) and its circuit-breaker bulk-update RESOLVE
#      EssayFailedJob entries, reducing dlq_backlog_count, with none of
#      #1-10 covering either path.

DASHBOARD_CACHE_TTL_SECONDS = 300

_THROUGHPUT_BUCKET_MINUTES = 5
_THROUGHPUT_BUCKET_COUNT = 6  # the last 30 minutes, in 5-minute buckets


def _essay_submission_throughput(submissions_qs, now):
    """Submissions-per-5-minute-bucket over the last 30 minutes, oldest
    first — an "is anyone still submitting right now" operational signal
    for a live dashboard, not a full historical trend (that scope, and
    the richer sparkline treatment, belongs to Analytics if ever needed
    there — this is deliberately just enough to answer one live
    question). No analog exists in assessment-service's own Dashboard to
    reuse — designed fresh for this service's own explicit "submission
    throughput over the live exam window" requirement (Task 10.1)."""
    window_start = now - timedelta(minutes=_THROUGHPUT_BUCKET_MINUTES * _THROUGHPUT_BUCKET_COUNT)
    recent = submissions_qs.filter(created_at__gte=window_start).values_list("created_at", flat=True)

    buckets = [0] * _THROUGHPUT_BUCKET_COUNT
    for ts in recent:
        minutes_ago = (now - ts).total_seconds() / 60
        bucket_from_end = min(int(minutes_ago // _THROUGHPUT_BUCKET_MINUTES), _THROUGHPUT_BUCKET_COUNT - 1)
        buckets[_THROUGHPUT_BUCKET_COUNT - 1 - bucket_from_end] += 1

    return [
        {
            "bucket_start": (now - timedelta(minutes=_THROUGHPUT_BUCKET_MINUTES * (_THROUGHPUT_BUCKET_COUNT - i))).isoformat(),
            "count": buckets[i],
        }
        for i in range(_THROUGHPUT_BUCKET_COUNT)
    ]


def _compute_essay_dashboard(assignment):
    now = timezone.now()
    total_allocated = EssayStudentSetAllocation.objects.filter(assignment=assignment).count()

    attempts = EssayAttempt.objects.filter(assignment=assignment)
    in_progress_count = attempts.filter(status=ATTEMPT_STATUS_IN_PROGRESS).count()
    total_submitted = attempts.filter(status__in=ATTEMPT_TERMINAL_STATUSES).count()

    submissions = EssaySubmission.objects.filter(attempt__assignment=assignment)
    pending_evaluation_count = submissions.filter(status=SUBMISSION_STATUS_LLM_PROCESSING).count()

    score_rows = list(EssayScore.objects.filter(submission__attempt__assignment=assignment).values_list("score", flat=True))
    average_score = round(sum(score_rows) / len(score_rows), 2) if score_rows else None

    # DLQ backlog scoped to THIS assignment's own submissions — a
    # deliberately different question from Phase 6's own
    # AdminSubmissionsPipelineHealthView, which is platform-wide shared-
    # infrastructure monitoring on purpose. This one answers "are THIS
    # assignment's own submissions stuck", not "is the whole pipeline
    # healthy". EssayFailedJob has no assignment FK of its own (it's
    # keyed by submission_id inside its own args JSONField), so this
    # intersects in Python rather than a fragile JSON-containment query
    # — matching this service's own established Postgres/SQLite
    # portability precedent (see AdminEssayAssignmentResultsView's own
    # docstring, Phase 8) — genuinely fine at this scale: the whole
    # unresolved-DLQ table is small platform-wide, let alone per-request.
    #
    # Phase 11 gap found by this phase's own final-audit round: this was
    # hardcoded to task_name="evaluate_essay" only, from back when that
    # was the only task ever DLQ'd against one specific submission.
    # generate_essay_report (Phase 11) is now a second one — without this
    # fix, a permanently-stuck report generation wouldn't move this KPI at
    # all, so "are this assignment's own submissions stuck" would
    # silently say no for a submission that genuinely is. The two task
    # names use different naming conventions in this same table (a
    # pre-existing fact of this codebase, not new here): "evaluate_essay"
    # is a bare literal evaluate_essay's own _record_dlq() calls choose by
    # hand; generate_essay_report goes through DeadLetteringTask's
    # on_failure(), which records Celery's own real (dotted) task name —
    # confirmed live via this exact worker's own Celery logs during this
    # phase's own testing ("essays.tasks.generate_essay_report").
    submission_ids = {str(sid) for sid in submissions.values_list("id", flat=True)}
    dlq_backlog_count = sum(
        1 for args in EssayFailedJob.objects.filter(
            task_name__in=["evaluate_essay", "essays.tasks.generate_essay_report"],
            resolved_at__isnull=True,
        ).values_list("args", flat=True)
        if args and str(args[0]) in submission_ids
    )

    time_remaining_seconds = None
    if assignment.status == ASSIGNMENT_STATUS_LIVE:
        time_remaining_seconds = max(0, int((assignment.global_expire_time - now).total_seconds()))

    return {
        "assignment_id": str(assignment.id),
        "assignment_status": assignment.status,
        "generated_at": now.isoformat(),
        "time_remaining_seconds": time_remaining_seconds,
        "total_allocated": total_allocated,
        "in_progress_count": in_progress_count,
        "total_submitted": total_submitted,
        "completion_rate_percentage": round(total_submitted / total_allocated * 100, 2) if total_allocated else 0.0,
        "total_scored": len(score_rows),
        "average_score": average_score,
        "pending_evaluation_count": pending_evaluation_count,
        "dlq_backlog_count": dlq_backlog_count,
        "submission_throughput": _essay_submission_throughput(submissions, now),
    }


class AdminEssayAssignmentDashboardView(APIView):
    """GET /admin/assignments/<id>/dashboard/ — see this module's own
    header comment for the full caching design (belt-and-suspenders: a
    300s TTL backstop plus explicit invalidation at every KPI-changing
    write path, genuinely reusing assessment-service's own Dashboard
    pattern this time, unlike Phase 9's deliberate correction away from
    it for Analytics)."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(EssayAssignment, pk=pk, institution_id=institution_id)

        cache_key = f"essay_dashboard:{assignment.id}"
        cached = safe_cache_get(cache_key)
        if cached is not None:
            return success_response(data=cached)

        data = _compute_essay_dashboard(assignment)
        safe_cache_set(cache_key, data, DASHBOARD_CACHE_TTL_SECONDS)
        return success_response(data=data)


# ── Admin: Reports Module (Phase 11, Tasks 11.1/11.2) ───────────────────────
# Reference (verified — actually read, not inferred): CLAP's
# report_management.py + email_management.py — "in CLAP these are two
# files, but together they form one coherent 'Reports' concept", per this
# tracker's own framing, which is why the views below are ONE table
# (generation state + delivery state together), not two separate list
# endpoints. See essays/reports.py's own module docstring for the full,
# honest reasoning behind every deviation from CLAP's own approach
# (HTML-not-PDF storage, direct SMTP instead of notification-service,
# deferred bounce/complaint webhook, skipped institution branding).
#
# Bulk-resend cap: derived from this service's own established scale unit
# (fetch_batch_roster's own page_size=200, core/user_service_client.py) —
# not a re-derivation of CLAP's own 500, which sizes a platform this
# service's own capacity plan (Task 0.4 — tens-to-low-hundreds of reports
# per assignment) doesn't match. Applied BEFORE the dry-run/real branch
# below, matching CLAP's own bulk_resend_email ordering exactly, so a
# dry-run preview never promises to send more than the real call actually
# would.
BULK_RESEND_CAP = 200


def _essay_delivery_status(submission, bounce_types_by_submission):
    """sent / pending / bounced / complaint — computed live from
    `email_sent_at` plus any bounce/complaint SubmissionEvent rows, never
    a separately-maintained field that can drift (verified from CLAP's
    own email_management.py: it computes delivery status the same way).

    Priority: complaint > bounced > sent > pending. A submission that was
    successfully delivered and only later bounced/complained must show
    that outcome, not a stale "sent"; one that bounced/complained even
    without an `email_sent_at` on record (a provider can report a hard
    bounce as its own delivery attempt) must still surface the negative
    outcome rather than defaulting to "pending"."""
    event_types = bounce_types_by_submission.get(submission.id, set())
    if SUBMISSION_EVENT_EMAIL_COMPLAINT in event_types:
        return "complaint"
    if SUBMISSION_EVENT_EMAIL_BOUNCED in event_types:
        return "bounced"
    if submission.email_sent_at is not None:
        return "sent"
    return "pending"


def _bounce_event_types_for_submissions(submission_ids):
    """{submission_id: {event_type, ...}} for just the given submissions —
    batched once per page/export, never once per row."""
    lookup: dict = {}
    rows = EssaySubmissionEvent.objects.filter(
        submission_id__in=submission_ids,
        event_type__in=[SUBMISSION_EVENT_EMAIL_BOUNCED, SUBMISSION_EVENT_EMAIL_COMPLAINT],
    ).values_list("submission_id", "event_type")
    for submission_id, event_type in rows:
        lookup.setdefault(submission_id, set()).add(event_type)
    return lookup


def _build_essay_reports_queryset(assignment, request, roster_by_user_id):
    """Shared between the list view, the bulk-download, and the
    bulk-resend below — the exact same filters must apply to all three,
    matching this service's own established "a bulk action must act on
    exactly what the filtered table is showing" convention (see
    `_build_essay_results_queryset`'s own identical reasoning, Phase 8).

    Raises ValueError on an invalid `status` filter — callers convert
    that to a 400, matching AdminSubmissionsListView's own inline
    handling of the same _SUBMISSION_STATUS_BUCKETS lookup.

    Deliberately no `batch` filter, unlike CLAP's own platform-wide
    report list: this view is scoped to one assignment (matching
    Analytics/Dashboard's own established per-assignment picker+detail
    convention, Phases 9/10), and an assignment already has exactly one
    batch_id — a separate batch filter here would be a no-op, not a real
    one."""
    qs = EssaySubmission.objects.filter(attempt__assignment=assignment).select_related("attempt", "score")

    status_bucket = request.query_params.get("status")
    if status_bucket:
        real_statuses = _SUBMISSION_STATUS_BUCKETS.get(status_bucket.lower())
        if not real_statuses:
            raise ValueError(
                f"Unknown status filter: {status_bucket!r}. Expected one of {sorted(_SUBMISSION_STATUS_BUCKETS)}."
            )
        qs = qs.filter(status__in=real_statuses)

    department = (request.query_params.get("department") or "").strip()
    student_search = (request.query_params.get("student_search") or "").strip().lower()
    if department or student_search:
        matching_ids = set(roster_by_user_id.keys())
        if department:
            matching_ids &= {
                uid for uid, info in roster_by_user_id.items()
                if (info.get("department") or "").strip().lower() == department.lower()
            }
        if student_search:
            # Task 11.1's own explicit requirement — "searchable by
            # student email or a partial student-id" — extends the
            # Results module's own roll-id/name search (Phase 8) with
            # email, the one field that module never needed to search.
            matching_ids &= {
                uid for uid, info in roster_by_user_id.items()
                if student_search in (info.get("student_id") or "").lower()
                or student_search in (info.get("name") or "").lower()
                or student_search in (info.get("email") or "").lower()
            }
        qs = qs.filter(attempt__student_id__in=matching_ids)

    return qs.order_by("-created_at")


def _serialize_essay_report_row(submission, roster_by_user_id, bounce_types_by_submission):
    info = roster_by_user_id.get(str(submission.attempt.student_id), {})
    score = getattr(submission, "score", None)
    return {
        "submission_id": str(submission.id),
        "student_user_id": str(submission.attempt.student_id),
        "student_roll_id": info.get("student_id", ""),
        "student_name": info.get("name") or "Unknown",
        "student_email": info.get("email") or "",
        "department": info.get("department") or "",
        "status": submission.status,
        "has_report": bool(submission.report_html),
        "score": score.score if score is not None else None,
        "email_sent_at": submission.email_sent_at,
        "delivery_status": _essay_delivery_status(submission, bounce_types_by_submission),
        "updated_at": submission.updated_at,
    }


class AdminAssignmentReportListView(APIView):
    """GET /admin/assignments/<id>/reports/ — paginated, filterable by
    status/department, searchable by student email/roll-id/name (Task
    11.1), with each row's delivery status (Task 11.2) joined in — see
    this section's own header comment for why generation+delivery are one
    table, not two. A roster-fetch failure fails this request outright
    (502), matching the Results module's own precedent exactly: a
    student's email is core to what a report row even means here (it's a
    required search field and the bulk-download's own CSV column), not an
    optional filter enhancement."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(EssayAssignment, pk=pk, institution_id=institution_id)

        try:
            roster_by_user_id = _fetch_essay_roster_lookup(assignment, request)
        except RuntimeError as exc:
            return error_response(f"Could not load student roster: {exc}", status_code=502)

        try:
            qs = _build_essay_reports_queryset(assignment, request, roster_by_user_id)
        except ValueError as exc:
            return error_response(str(exc), status_code=400)

        paginator = SubmissionsListPagination()
        page = paginator.paginate_queryset(qs, request)
        bounce_types = _bounce_event_types_for_submissions([s.id for s in page])
        rows = [_serialize_essay_report_row(s, roster_by_user_id, bounce_types) for s in page]
        return paginator.get_paginated_response(rows)


class AdminReportRegenerateView(APIView):
    """POST /admin/submissions/<id>/regenerate-report/ — CLAP's own
    documented reliability lessons, applied with this codebase's own
    already-established CAS convention for this exact "re-run a pipeline
    step, guard against a double-click race" shape (a conditional UPDATE,
    not select_for_update — see AdminSubmissionRetriggerView's own
    comment, Phase 7, for why this project already made and audited that
    choice; reusing it here rather than introducing a second locking
    mechanism for an identical problem is the point):
      - resets to the pre-generation state generate_essay_report actually
        checks for (LLM_COMPLETE, never REPORT_GENERATING — the exact bug
        CLAP's own history warns about, see SUBMISSION_STATUS_
        REPORT_GENERATING's own docstring, essays/models.py)
      - resets report_html and email_sent_at to null, so a stale report/
        stale "sent" marker never survives a regenerate
      - the CAS update IS the lock: only one of any number of concurrent
        double-clicks can ever see updated=1
      - dispatches generate_essay_report AFTER the transaction commits,
        never from inside it (this module's own already-audited Phase 10
        "invalidate/dispatch after commit, not before" lesson —
        _transition_submission_status() is deliberately NOT used here for
        exactly this reason; see that function's own docstring)
      - rolls back cleanly (a plain .update(), not the original
        transaction) restoring the prior status/report_html/email_sent_at
        if the Celery dispatch itself raises
    Only ever allowed from REPORT_READY: a submission with no report yet
    has nothing to regenerate (it's already LLM_COMPLETE, on its own way
    to a first generation), and REPORT_GENERATING is already mid-flight.

    Known, deliberately-out-of-scope gap (found and considered, not
    missed, by this phase's own final-audit round): if generate_essay_report
    itself is ever PERMANENTLY DLQ'd (report rendering only fails on a
    genuine bug or a DB hiccup that outlasts its own 3 built-in retries —
    see that task's own docstring), the affected submission rolls back to
    LLM_COMPLETE and stays there — this view's own REPORT_READY-only
    guard won't touch it, so it has no dedicated recovery action here.
    Deliberately not building one: Phase 12 (the DLQ Module) is the
    platform's own generic "retry any stuck EssayFailedJob entry,
    regardless of task_name" mechanism — building a second, narrower,
    report-specific recovery path here would be duplicate machinery for a
    case Phase 12 is explicitly designed to already cover once it exists.
    In the meantime this IS still visible: `dlq_backlog_count`
    (essays/views.py::_compute_essay_dashboard) and the submission's own
    EssaySubmissionEvent trail (DeadLetteringTask.on_failure(),
    essays/tasks.py) both surface it — an admin can see it's stuck, even
    before Phase 12 gives them a one-click fix."""
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        submission = get_object_or_404(
            EssaySubmission, pk=pk, attempt__assignment__institution_id=institution_id,
        )
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return error_response("A reason is required to regenerate a report.", status_code=400)

        old_report_html = submission.report_html
        old_email_sent_at = submission.email_sent_at

        with transaction.atomic():
            updated = EssaySubmission.objects.filter(
                pk=submission.pk, status=SUBMISSION_STATUS_REPORT_READY,
            ).update(status=SUBMISSION_STATUS_LLM_COMPLETE, report_html=None, email_sent_at=None)
            if not updated:
                return error_response(
                    "This submission has no ready report to regenerate (it may already be "
                    "generating, or has not been scored yet).",
                    status_code=409,
                )
            EssaySubmissionEvent.objects.create(
                submission=submission, event_type=SUBMISSION_EVENT_ADMIN_RETRIGGER,
                detail="Report regenerated by an admin.",
                admin_user_id=request.user.id, reason=reason,
            )

        # Moved to after the block exits — see this view's own docstring
        # and _transition_submission_status()'s own docstring for why
        # (Phase 10's own already-audited lesson, applied here fresh).
        safe_cache_delete(f"essay_dashboard:{submission.attempt.assignment_id}")

        from .tasks import generate_essay_report
        try:
            generate_essay_report.delay(str(submission.id))
        except Exception as exc:
            logger.exception("AdminReportRegenerateView: dispatch failed for submission %s.", submission.id)
            EssaySubmission.objects.filter(pk=submission.pk).update(
                status=SUBMISSION_STATUS_REPORT_READY,
                report_html=old_report_html,
                email_sent_at=old_email_sent_at,
            )
            return error_response(f"Could not dispatch report regeneration: {exc}", status_code=502)

        return success_response(message="Report regeneration dispatched.")


class AdminSubmissionReportResendView(APIView):
    """POST /admin/submissions/<id>/resend-report/ — Task 11.2's
    single-submission resend, also the one and only "send" action (see
    send_essay_report_email's own docstring, essays/tasks.py, for why
    there's no separate first-send). The student's email is looked up
    here, in this real request context, not inside the dispatched Celery
    task — core/user_service_client.py authenticates by forwarding the
    calling admin's own JWT, which doesn't exist inside a worker."""
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        submission = get_object_or_404(
            EssaySubmission, pk=pk, attempt__assignment__institution_id=institution_id,
        )
        if not submission.report_html:
            return error_response("This submission has no report yet to send.", status_code=409)

        try:
            roster_by_user_id = _fetch_essay_roster_lookup(submission.attempt.assignment, request)
        except RuntimeError as exc:
            return error_response(f"Could not load student roster: {exc}", status_code=502)

        info = roster_by_user_id.get(str(submission.attempt.student_id))
        email = (info or {}).get("email")
        if not email:
            return error_response("No email address on file for this student.", status_code=422)

        from .tasks import send_essay_report_email
        # Real gap found auditing every .delay() call site against the
        # same broker-unreachable class of bug already fixed in
        # scoring.py. This is a manual, on-demand admin action with no
        # status of its own to get stuck in (send_essay_report_email
        # doesn't gate on anything beforehand) — a failed dispatch here is
        # a clean, honest failure the admin can just retry, not a state
        # that needs an automatic recovery mechanism.
        if not safe_task_dispatch(
            send_essay_report_email, str(submission.id), email,
            context=f"send_essay_report_email for submission {submission.id}",
        ):
            return error_response(
                "Could not dispatch the report email right now (task queue unreachable) — try again shortly.",
                status_code=503,
            )
        return success_response(message=f"Report email dispatched to {email}.")


class AdminAssignmentReportBulkResendView(APIView):
    """POST /admin/assignments/<id>/reports/bulk-resend/ — Task 11.2's
    capped, dry-run-by-default bulk resend (verified from CLAP's own
    bulk_resend_email — this tracker's own Task 11.2 note names this the
    platform-wide default-safe pattern for every bulk action: a cap alone
    stops a catastrophic mistake, dry-run-by-default stops an ordinary
    one). The cap is applied BEFORE the dry-run/real branch, so a preview
    never promises more than the real call would actually do.

    Uses the exact same filters as the report list
    (`_build_essay_reports_queryset`) — an admin resending "everyone
    currently showing bounced" must resend exactly the rows they're
    looking at, not a silently different set. Only ever targets
    submissions that actually have a report (report_html not empty) —
    nothing to send otherwise."""
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(EssayAssignment, pk=pk, institution_id=institution_id)

        try:
            roster_by_user_id = _fetch_essay_roster_lookup(assignment, request)
        except RuntimeError as exc:
            return error_response(f"Could not load student roster: {exc}", status_code=502)

        try:
            qs = _build_essay_reports_queryset(assignment, request, roster_by_user_id)
        except ValueError as exc:
            return error_response(str(exc), status_code=400)

        qs = qs.exclude(report_html__isnull=True).exclude(report_html="")
        total_matching = qs.count()
        submissions = list(qs[:BULK_RESEND_CAP])

        targets = []
        for submission in submissions:
            info = roster_by_user_id.get(str(submission.attempt.student_id))
            email = (info or {}).get("email")
            if email:
                targets.append((submission, email))

        dry_run = str(request.data.get("dry_run", True)).strip().lower() not in ("false", "0")
        if dry_run:
            return success_response(data={
                "dry_run": True,
                "would_dispatch_count": len(targets),
                "total_matching": total_matching,
                "capped": total_matching > BULK_RESEND_CAP,
                "sample": [
                    {"submission_id": str(s.id), "student_email": e}
                    for s, e in targets[:10]
                ],
                "note": "No emails sent. Pass dry_run=false to actually send.",
            })

        from .tasks import send_essay_report_email
        # Real gap found auditing every .delay() call site against the
        # same broker-unreachable class of bug already fixed in
        # scoring.py — this one was the worst of the six found, since it's
        # a loop: an unhandled crash on the first failure would have
        # silently left every remaining target in this batch never even
        # attempted, with the whole request failing 500 despite some
        # emails potentially already having gone out. Same circuit-breaker
        # shape as scoring.py's own dispatch loop: once the broker proves
        # unreachable once, every subsequent target shares that identical
        # failure, so stop attempting further sends immediately rather
        # than re-paying the same retry cost per remaining target — no
        # point burning it hundreds of times over for a single, shared
        # cause. Every skipped target is counted and reported back so the
        # admin knows to retry the bulk-resend, not left to guess.
        dispatched_count = 0
        broker_down = False
        for submission, email in targets:
            if broker_down:
                break
            if safe_task_dispatch(
                send_essay_report_email, str(submission.id), email,
                context=f"send_essay_report_email (bulk) for submission {submission.id}",
            ):
                dispatched_count += 1
            else:
                broker_down = True

        return success_response(data={
            "dry_run": False,
            "dispatched_count": dispatched_count,
            "skipped_count": len(targets) - dispatched_count,
            "total_matching": total_matching,
            "capped": total_matching > BULK_RESEND_CAP,
            "broker_unavailable": broker_down,
        })


class AdminAssignmentReportBulkDownloadView(APIView):
    """GET /admin/assignments/<id>/reports/bulk-download/ — every
    generated report for one assignment as a single ZIP (one HTML file
    per submission, named "<submission_id>.html") plus a CSV manifest
    (submission id, student email, report reference — the exact 3
    columns Task 11.1 asks for), matching CLAP's own buffered
    io.BytesIO()+zipfile.ZipFile pattern — the only bulk-ZIP precedent
    anywhere in this monorepo (verified — nothing else on this platform
    does a ZIP export).

    Built fully in memory, not streamed: proportionate at this service's
    own scale (Task 0.4 — tens-to-low-hundreds of reports per assignment).
    Results' own CSV export (Phase 8) streams instead because that export
    has no such report-count ceiling to lean on — a genuinely different
    trade-off for a genuinely different data shape, not an inconsistency.

    Same filters as the report list — a filtered "only completed" bulk
    download matches what the table shows, never silently downloads
    everything."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(EssayAssignment, pk=pk, institution_id=institution_id)

        try:
            roster_by_user_id = _fetch_essay_roster_lookup(assignment, request)
        except RuntimeError as exc:
            return error_response(f"Could not load student roster: {exc}", status_code=502)

        try:
            qs = _build_essay_reports_queryset(assignment, request, roster_by_user_id)
        except ValueError as exc:
            return error_response(str(exc), status_code=400)

        qs = qs.exclude(report_html__isnull=True).exclude(report_html="")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            manifest = io.StringIO()
            writer = csv.writer(manifest)
            writer.writerow(["Submission ID", "Student Email", "Report Reference"])
            for submission in qs:
                info = roster_by_user_id.get(str(submission.attempt.student_id), {})
                filename = f"{submission.id}.html"
                writer.writerow([str(submission.id), info.get("email") or "", filename])
                zf.writestr(filename, submission.report_html)
            zf.writestr("manifest.csv", manifest.getvalue())

        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="essay_reports_{assignment.id}.zip"'
        return response


# ── Admin: DLQ Module (Phase 12, Task 12.1) ─────────────────────────────────
# Reference (verified — actually read, not inferred): CLAP's own
# django-backend/api/views/admin/dlq.py — "a dedicated module, richer than
# the small widget embedded in Phase 6's Submissions module" (this
# tracker's own framing), which only ever surfaced a bare unresolved
# count (AdminSubmissionsPipelineHealthView above). This module exposes
# individual entries — including the full original task payload — for an
# admin to actually diagnose and act on.
#
# EssayFailedJob has no institution_id of its own (shared platform
# infrastructure, not per-institution data — see
# AdminSubmissionsPipelineHealthView's own docstring above, which already
# established this for its own bare count), so none of the views below
# filter by institution either — matching that same, already-decided
# precedent, and IsAdminOrSuperAdmin's own docstring, which explicitly
# lists DLQ among the modules "admin and super_admin share... the entire
# admin surface" for in this service (core/permissions.py).
#
# Deliberately generic, not evaluate_essay-specific: see
# tasks.py::retry_dlq_entry's own docstring for the one accepted,
# documented trade-off (a retried evaluate_essay entry's submission
# status briefly still reads LLM_FAILED until the retry itself
# completes, since this generic path doesn't pre-set LLM_PROCESSING the
# way Phase 7's own dedicated AdminSubmissionRetriggerView does).

def _serialize_dlq_entry_row(entry):
    return {
        "id": str(entry.id),
        "task_name": entry.task_name,
        "attempts": entry.attempts,
        "dlq_retry_count": entry.dlq_retry_count,
        "error": entry.error,
        "resolved": entry.resolved_at is not None,
        "resolved_at": entry.resolved_at,
        "created_at": entry.created_at,
    }


def _serialize_dlq_entry_detail(entry):
    return {
        **_serialize_dlq_entry_row(entry),
        "task_id": entry.task_id,
        # The full original task payload (Task 12.1's own explicit
        # requirement) — everything needed to actually diagnose why this
        # failed, not just that it did.
        "args": entry.args,
        "kwargs": entry.kwargs,
        "traceback": entry.traceback,
    }


class AdminDLQListView(APIView):
    """GET /admin/dlq/ — paginated (30/page, reusing SubmissionsListPagination
    — this task's own explicit number, already the platform's established
    page size for a dense operational list), server-side `resolved` filter:
    `true` (only resolved), `false` (only unresolved), omitted or `all`
    (no filter) — never "load everything and filter in the browser"."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        qs = EssayFailedJob.objects.all()

        resolved_param = (request.query_params.get("resolved") or "").strip().lower()
        if resolved_param == "true":
            qs = qs.filter(resolved_at__isnull=False)
        elif resolved_param == "false":
            qs = qs.filter(resolved_at__isnull=True)
        elif resolved_param and resolved_param != "all":
            return error_response(
                f"Unknown resolved filter: {resolved_param!r}. Expected one of true, false, all.",
                status_code=400,
            )

        paginator = SubmissionsListPagination()
        page = paginator.paginate_queryset(qs, request)
        rows = [_serialize_dlq_entry_row(entry) for entry in page]
        return paginator.get_paginated_response(rows)


class AdminDLQDetailView(APIView):
    """GET /admin/dlq/<id>/ — the full original task payload (args,
    kwargs, traceback) alongside everything the list row already shows —
    "essential for actually diagnosing why something failed, not just
    that it did" (Task 12.1's own words)."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, pk):
        entry = get_object_or_404(EssayFailedJob, pk=pk)
        return success_response(data=_serialize_dlq_entry_detail(entry))


def _log_dlq_action_on_submission(entry, event_type, detail, admin_user_id, reason):
    """Best-effort: only writes an event when this entry's own task is
    genuinely tied to one specific submission (its own args[0]) — see
    DLQ_SUBMISSION_SCOPED_TASK_NAMES's own docstring, essays/tasks.py.
    Never allowed to fail the admin action it's merely recording
    alongside (matches _log_submission_event's own established
    convention, essays/tasks.py).

    Real bug found by this phase's own testing (not just theorized): a
    bare try/except around .create() here is NOT enough. Model.save()
    wraps itself in its own transaction.atomic(savepoint=False) —
    confirmed live, a deliberately-malformed submission id raised inside
    that inner block still poisoned the OUTER transaction, so the
    caller's own very next query (marking this entry resolved) failed
    with a TransactionManagementError despite this function's own
    except-and-log already having "handled" the original error. The same
    lesson AdminSubmissionGeneralScoreOverrideView's own docstring already
    documents once (Phase 7, "a nested atomic() isolates just this
    statement's rollback") — applied fresh here: a real, explicit
    savepoint, not a bare try/except, is what actually isolates a failed
    write from the rest of the request."""
    from .tasks import DLQ_SUBMISSION_SCOPED_TASK_NAMES
    if entry.task_name not in DLQ_SUBMISSION_SCOPED_TASK_NAMES or not entry.args:
        return
    try:
        with transaction.atomic():
            EssaySubmissionEvent.objects.create(
                submission_id=entry.args[0], event_type=event_type, detail=detail,
                admin_user_id=admin_user_id, reason=reason,
            )
    except Exception:
        logger.exception(
            "DLQ module: failed to log %s for submission %s (entry %s) — the DLQ action itself is unaffected.",
            event_type, entry.args[0], entry.id,
        )


class AdminDLQRetryView(APIView):
    """POST /admin/dlq/<id>/retry/ — idempotent: retrying an
    already-resolved entry is a safe no-op (Task 12.1's own explicit
    requirement), not an error, since an admin browsing a list that's
    mid-refresh could easily double-click a row that just got resolved by
    someone else. Otherwise re-dispatches the exact original task (see
    tasks.py::retry_dlq_entry).

    Real race found by this phase's own final-audit round: the first
    version read `entry.resolved_at` from the already-fetched object,
    then dispatched, then separately wrote `resolved_at` — a genuine
    read-then-write gap, not a real lock. Two concurrent callers (two
    admins double-clicking, or an admin racing the automatic sweeper —
    sweep_dlq_entries, essays/tasks.py, which also dispatches
    evaluate_essay for unresolved entries past their grace period) could
    both see resolved_at=None and both dispatch — the exact "duplicate
    concurrent evaluation, real billed LLM cost" class of race (ET11)
    AdminSubmissionRetriggerView's own CAS guard (Phase 7) already exists
    to close for ITS OWN call path. Fixed the same way: a conditional
    UPDATE CLAIMS the entry (resolved_at set) BEFORE dispatch, not after
    — only one of any number of concurrent callers can ever see
    updated=1 — and rolls back (resolved_at cleared) if the dispatch
    itself then fails, so a failed retry doesn't silently disappear from
    the unresolved list."""
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        entry = get_object_or_404(EssayFailedJob, pk=pk)
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return error_response("A reason is required to retry a DLQ entry.", status_code=400)

        claimed = EssayFailedJob.objects.filter(pk=entry.pk, resolved_at__isnull=True).update(resolved_at=timezone.now())
        if not claimed:
            return success_response(message="This entry was already resolved — nothing to retry.")

        from .tasks import retry_dlq_entry
        try:
            retry_dlq_entry(entry)
        except ValueError as exc:
            EssayFailedJob.objects.filter(pk=entry.pk).update(resolved_at=None)
            return error_response(str(exc), status_code=422)
        except Exception as exc:
            logger.exception("AdminDLQRetryView: dispatch failed for entry %s.", entry.id)
            EssayFailedJob.objects.filter(pk=entry.pk).update(resolved_at=None)
            return error_response(f"Could not dispatch retry: {exc}", status_code=502)

        _log_dlq_action_on_submission(
            entry, SUBMISSION_EVENT_ADMIN_RETRIGGER,
            f"Retried from the DLQ module ({entry.task_name}).",
            request.user.id, reason,
        )
        return success_response(message="Retry dispatched.")


class AdminDLQResolveView(APIView):
    """POST /admin/dlq/<id>/resolve/ — mark an entry done WITHOUT
    retrying, for one an admin has handled some other way (e.g. Phase 7's
    manual score override for a permanently-stuck evaluation). Idempotent
    for the same reason as retry above — a real conditional UPDATE claims
    the entry, not a read-then-write check (see AdminDLQRetryView's own
    docstring for the race this closes; less consequential here since
    resolving never dispatches anything, but the same no-op-vs-error
    correctness matters either way, and consistency is its own value).
    Reuses SUBMISSION_EVENT_ADMIN_OVERRIDE (not a new event type) —
    semantically this is an admin overriding the automatic pipeline's own
    "still needs attention" state, not a retrigger, matching
    AdminReportRegenerateView's own established reasoning (Phase 11) for
    reusing an existing event type over adding a new one for a
    narrowly-different admin action."""
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        entry = get_object_or_404(EssayFailedJob, pk=pk)
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return error_response("A reason is required to resolve a DLQ entry.", status_code=400)

        claimed = EssayFailedJob.objects.filter(pk=entry.pk, resolved_at__isnull=True).update(resolved_at=timezone.now())
        if not claimed:
            return success_response(message="This entry was already resolved.")

        _log_dlq_action_on_submission(
            entry, SUBMISSION_EVENT_ADMIN_OVERRIDE,
            f"DLQ entry resolved without retrying ({entry.task_name}).",
            request.user.id, reason,
        )
        return success_response(message="Entry resolved.")


class AdminDLQBulkRetryView(APIView):
    """POST /admin/dlq/bulk-retry/ — capped (`DLQ_BULK_RETRY_CAP`,
    essays/tasks.py — re-derived from this service's own scale, not
    CLAP's own "100" copied as-is, per Task 12.1's own explicit
    instruction) and dry-run-by-default (Phase 11's own Task 11.2 note
    names this exact action — "bulk DLQ retry in Phase 12" — as one of
    the two worked examples for applying that same platform-wide
    default-safe pattern everywhere). Operates on every currently
    unresolved entry, oldest first (the ones that have waited longest),
    up to the cap."""
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request):
        from .tasks import DLQ_BULK_RETRY_CAP
        qs = EssayFailedJob.objects.filter(resolved_at__isnull=True).order_by("created_at")
        total_matching = qs.count()
        entries = list(qs[:DLQ_BULK_RETRY_CAP])

        dry_run = str(request.data.get("dry_run", True)).strip().lower() not in ("false", "0")
        if dry_run:
            return success_response(data={
                "dry_run": True,
                "would_dispatch_count": len(entries),
                "total_matching": total_matching,
                "capped": total_matching > DLQ_BULK_RETRY_CAP,
                "sample": [
                    {"id": str(e.id), "task_name": e.task_name, "error": e.error[:200]}
                    for e in entries[:10]
                ],
                "note": "No entries retried. Pass dry_run=false to actually retry.",
            })

        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return error_response("A reason is required to bulk-retry DLQ entries.", status_code=400)

        from .tasks import retry_dlq_entry
        dispatched = 0
        for entry in entries:
            # Same conditional-UPDATE claim as AdminDLQRetryView's own
            # single-entry action, and for the same reason — this loop
            # re-checks `entries` fetched moments earlier in this same
            # request, but the automatic sweeper (or a concurrent single
            # retry) could still have claimed any one of them in between.
            claimed = EssayFailedJob.objects.filter(pk=entry.pk, resolved_at__isnull=True).update(resolved_at=timezone.now())
            if not claimed:
                continue  # already resolved by something else since we listed it — skip, not an error
            try:
                retry_dlq_entry(entry)
            except ValueError:
                EssayFailedJob.objects.filter(pk=entry.pk).update(resolved_at=None)
                continue  # unrecognized task_name — skip, don't fail the whole batch
            except Exception:
                logger.exception("AdminDLQBulkRetryView: dispatch failed for entry %s.", entry.id)
                EssayFailedJob.objects.filter(pk=entry.pk).update(resolved_at=None)
                continue  # one bad entry must not fail the whole batch
            _log_dlq_action_on_submission(
                entry, SUBMISSION_EVENT_ADMIN_RETRIGGER,
                f"Bulk-retried from the DLQ module ({entry.task_name}).",
                request.user.id, reason,
            )
            dispatched += 1

        return success_response(data={
            "dry_run": False,
            "dispatched_count": dispatched,
            "total_matching": total_matching,
            "capped": total_matching > DLQ_BULK_RETRY_CAP,
        })


# ── Admin: Notifications Module (Phase 13, Task 13.1) ───────────────────────
# Reference (verified — actually read, not inferred; and a real correction
# already made once by this tracker's own text, re-confirmed here): CLAP's
# django-backend/api/views/admin/notifications.py — an OPERATIONAL
# alerting system for admins monitoring the pipeline's own health, not a
# "your report is ready" student-notification wrapper (that concept
# already lives under Phase 11's own delivery tracking). See
# essays/notifications.py's own module docstring for the full,
# doubly-verified correction to this task's own "reuse notification-
# service" claim — it's both factually wrong about notification-service's
# real capabilities, AND cites a Non-Negotiable Constraint (§5) that says
# something entirely unrelated.
#
# Not institution-scoped, matching AdminSubmissionsPipelineHealthView's
# own already-established precedent (Phase 6) and IsAdminOrSuperAdmin's
# own docstring (core/permissions.py), which already explicitly lists
# every module in this admin surface — including this one — as shared
# between admin/super_admin, not gated by institution.

class AdminPipelineHealthSummaryView(APIView):
    """GET /admin/notifications/summary/?window_hours=24 — Task 13.1's
    own pipeline-health summary + tiered alerts, computed fresh on every
    request. Deliberately NOT cached: this is a low-traffic admin
    monitoring view, not a high-QPS student-facing one (unlike Phase
    9/10's own dashboard/analytics caching decisions), and a stale alert
    is a worse failure mode here than one extra query."""
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        from django.conf import settings
        from .notifications import compute_pipeline_health_summary, generate_pipeline_alerts

        window_param = request.query_params.get("window_hours")
        try:
            window_hours = int(window_param) if window_param else settings.PIPELINE_SUMMARY_DEFAULT_WINDOW_HOURS
        except ValueError:
            return error_response("window_hours must be an integer.", status_code=400)
        if window_hours <= 0:
            return error_response("window_hours must be a positive integer.", status_code=400)
        if window_hours > settings.PIPELINE_SUMMARY_MAX_WINDOW_HOURS:
            return error_response(
                f"window_hours must not exceed {settings.PIPELINE_SUMMARY_MAX_WINDOW_HOURS}.",
                status_code=400,
            )

        summary = compute_pipeline_health_summary(window_hours)
        alerts = generate_pipeline_alerts(summary)
        return success_response(data={**summary, "alerts": alerts})


class AdminSendDailySummaryView(APIView):
    """POST /admin/notifications/send-summary/ — Task 13.2's own "manual
    send daily summary now" action for testing/on-demand use. Dispatches
    the exact same Celery task the automatic daily schedule uses
    (send_pipeline_health_summary_email, essays/tasks.py) — not a
    separate code path, so a manual send and the real automatic one can
    never silently drift apart in content, thresholds, or recipients."""
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request):
        from django.conf import settings
        if not settings.ALERT_EMAIL_RECIPIENTS:
            return error_response(
                "No alert email recipients configured (ALERT_EMAIL_RECIPIENTS is empty).",
                status_code=409,
            )
        from .tasks import send_pipeline_health_summary_email
        # Real gap found auditing every .delay() call site against the
        # same broker-unreachable class of bug already fixed in
        # scoring.py. Low-severity (an on-demand admin testing action, not
        # part of the real pipeline) but the same fix for consistency.
        if not safe_task_dispatch(
            send_pipeline_health_summary_email, context="send_pipeline_health_summary_email (manual)",
        ):
            return error_response(
                "Could not dispatch the summary email right now (task queue unreachable) — try again shortly.",
                status_code=503,
            )
        return success_response(
            message=f"Daily summary dispatched to {len(settings.ALERT_EMAIL_RECIPIENTS)} recipient(s)."
        )


# ── Student: Past Results (Phase 14, Task 14.1) ─────────────────────────────
# Mirrors assessment-service's own StudentResultsView (verified, already
# read) — same IDOR guarantee, closing ET3: filtered strictly by the JWT's
# own user_id, never a client-supplied identifier. Same choice to exclude
# malpractice/plagiarism detection detail from the student-facing payload
# (handing a student their own detection outcome would let them calibrate
# around it) — that stays admin-only, Phase 8's own
# AdminEssayAssignmentResultsView. Unlike that precedent, essay-service has
# no per-assignment "show results" admin toggle at all (no such field
# exists on EssayAssignment — confirmed, not assumed, by reading the whole
# model) and no retake path (ADR 002 Decision 3, unique_together on
# EssayAttempt), so every terminal attempt's own row is always shown once
# it exists; readiness is expressed through exam_status (reusing
# _essay_result_exam_status, Phase 8's own helper, defined later in this
# file — a plain forward reference, resolved at request time like every
# other cross-section helper call in this module) rather than a separate
# visibility flag.

class StudentEssayResultsView(APIView):
    """GET /api/essay/student/results/ — the requesting student's own
    completed essay attempts, with score + feedback once evaluation has
    finished. A still-processing or permanently-failed attempt still shows
    its own row (matching assessment-service's own "never hide that you
    completed it" precedent) with score/feedback left null — the frontend
    is responsible for presenting that state kindly (never the raw
    "failed" bucket word, which reads as "you failed" rather than "the
    automated grading hit an error")."""
    permission_classes = [IsStudentUser]

    def get(self, request):
        attempts = (
            EssayAttempt.objects.filter(
                student_id=request.user.id, status__in=ATTEMPT_TERMINAL_STATUSES,
            )
            .select_related("assignment__paper", "set__question", "submission__score")
        )

        data = []
        for attempt in attempts:
            submission = getattr(attempt, "submission", None)
            score = getattr(submission, "score", None) if submission is not None else None
            question = getattr(attempt.set, "question", None)
            data.append({
                "assignment_id": str(attempt.assignment_id),
                "attempt_id": str(attempt.id),
                "paper_title": attempt.assignment.paper.title,
                "set_label": attempt.set.label,
                "question_text": question.question_text if question is not None else "",
                "attempt_status": attempt.status,
                "exam_status": _essay_result_exam_status(attempt, submission),
                "started_at": attempt.started_at,
                "submitted_at": submission.created_at if submission is not None else None,
                "score": score.score if score is not None else None,
                "max_score": question.max_score if question is not None else None,
                "is_no_submission": bool(score.is_no_submission) if score is not None else False,
                "feedback": score.feedback if score is not None else None,
            })
        # Most-recently-COMPLETED first, matching assessment-service's own
        # StudentResultsView precedent (order_by("-ended_at")) — found
        # during Phase 14's own final audit that this had drifted to
        # ordering by started_at instead, a genuine behavioral difference
        # for any attempt whose completion order differs from its start
        # order (e.g. a long-running attempt started first but auto-
        # submitted last at its own later deadline). Falls back to
        # started_at only for the rare, momentary processing-window case
        # where finalize_attempts() hasn't yet created the submission row —
        # a per-student list is small (no retakes; at most one attempt per
        # assignment), so a Python-side sort after the fetch is simpler
        # than a DB-level annotation for no real cost at this scale.
        data.sort(key=lambda row: row["submitted_at"] or row["started_at"], reverse=True)
        return success_response(data=data)
