import csv
import io
import logging
from datetime import timedelta
from django.core.cache import cache
from django.db import transaction, IntegrityError
from django.db.models import Count, Max, Avg, Case, When, Value, F, FloatField, CharField, ExpressionWrapper, Q, OuterRef, Subquery
from django.http import StreamingHttpResponse, HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.generics import get_object_or_404

from core.permissions import IsAdminUser, IsStudentUser, IsAdminOrSuperAdmin
from core.responses import success_response, error_response
from core.pagination import StandardResultsPagination
from core.storage import (
    build_file_key, generate_presigned_upload_url, get_cdn_url,
    verify_uploaded_image, delete_file, scan_image_for_malware,
    TransientStorageError,
)
from core.upload_constraints import ALLOWED_IMAGE_EXTENSIONS, MAX_BYTES_PER_PAPER
from core.user_service_client import fetch_batch_roster
from core.auth_service_client import resolve_user_names
from core.cache_utils import safe_cache_get, safe_cache_set

from .models import (
    QuestionPaper, QuestionSet, Question, QuestionOption, MCQ_TYPE_SINGLE,
    BatchAssignment, ASSIGNMENT_STATUS_SCHEDULED, ASSIGNMENT_STATUS_LIVE,
    ASSIGNMENT_STATUS_CLOSED,
    AssessmentSession, StudentSetAllocation, AssessmentResponse,
    ActivityLog, ACTIVITY_EVENT_TYPE_CHOICES, ResultSummary,
    SESSION_STATUS_IN_PROGRESS, SESSION_STATUS_SUBMITTED, SESSION_STATUS_AUTO_SUBMITTED,
)
from .serializers import (
    QuestionPaperSerializer, QuestionSetSerializer,
    QuestionSerializer, QuestionOptionSerializer, BatchAssignmentSerializer,
    StudentQuestionSerializer,
)
from .validators import get_content_type_blocker, get_assignment_readiness_blockers
from .allocation import snapshot_roster_and_allocate
from .scoring import finalize_sessions
from .enforcement import session_is_writable, strip_client_timestamps
from .throttling import ActivityLogRateThrottle, AnswerSubmitRateThrottle

logger = logging.getLogger(__name__)

_OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ALLOWED_IMAGE_MIME = (
    "image/jpeg", "image/png", "image/webp", "image/gif", "image/avif",
)


def _get_institution_id(request):
    return getattr(request.user, "institution_id", None)


PAPER_OWNERSHIP_DENIED_MSG = "This assessment was created by another admin and can't be accessed by you."


def _require_paper_owner(paper, request):
    """Faculty-privacy restriction: a question paper's contents (sets,
    questions, options, instructions, images) and the ability to assign it
    to a batch are visible/actionable only to the admin who authored it —
    every other admin at the same institution sees the paper listed
    (AdminPaperListCreateView.get is intentionally NOT gated by this) but
    cannot open, edit, delete, or assign it. Results/Analytics/Dashboard
    stay institution-wide and are never gated by this check.

    Super admins always bypass this — without an override, a paper would
    become permanently inaccessible to everyone the instant its creator's
    account is deactivated or deleted (already-supported admin-management
    actions elsewhere in this platform), which would be a real operational
    risk, not a hypothetical one.

    Returns an error_response (403) if access is denied, else None.
    """
    if request.user.role == "super_admin":
        return None
    if str(paper.created_by) != str(request.user.id):
        return error_response(PAPER_OWNERSHIP_DENIED_MSG, status_code=403)
    return None


# ── Health ─────────────────────────────────────────────────────────────────────

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
            "service": "assessment-service",
            "db": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
        })


# ── Shared image-write pipeline ─────────────────────────────────────────────────
# Verify (real size + magic bytes) → scan (ClamAV) → quota check, in that
# order (no point scanning/counting an object that already failed a cheaper
# check). Mirrors practice-service's inline pattern in
# AdminPracticeQuestionDetailView.patch, factored into one helper since this
# service applies it to both question images and option images.

def _verify_and_scan_image(file_key):
    """Returns (real_size, error_response). error_response is None on
    success; real_size is None on failure. Never raises — RuntimeError
    (storage/scanning not configured) is converted to a 503 error_response
    so callers don't need their own try/except for that case."""
    try:
        real_size, error = verify_uploaded_image(file_key)
    except RuntimeError as exc:
        logger.error("Storage not configured for image verification: %s", exc)
        return None, error_response("File storage is not configured.", status_code=503)
    except TransientStorageError as exc:
        # Verification itself failed (storage unreachable) — the object was
        # never examined, so it's left in place; the admin can retry the
        # same save once storage recovers.
        return None, error_response(str(exc), status_code=503)
    if error:
        try:
            delete_file(file_key)
        except Exception:
            logger.warning("Failed to clean up rejected image key=%s", file_key)
        return None, error_response(error, status_code=400)

    try:
        scan_error = scan_image_for_malware(file_key)
    except RuntimeError as exc:
        logger.error("Malware scanning not configured: %s", exc)
        return None, error_response("Malware scanning is not configured.", status_code=503)
    except TransientStorageError as exc:
        # Scanner unreachable — the image was never actually cleared or
        # rejected, so it must NOT be deleted (that would destroy a good
        # upload and force a needless re-upload on retry).
        return None, error_response(str(exc), status_code=503)
    if scan_error:
        try:
            delete_file(file_key)
        except Exception:
            logger.warning("Failed to clean up infected image key=%s", file_key)
        return None, error_response(scan_error, status_code=400)

    return real_size, None


def _paper_image_quota_ok(paper_id, exclude_bytes, additional_bytes):
    """Total confirmed image bytes across every question + option image in
    this paper, after replacing `exclude_bytes` worth with `additional_bytes`
    of new uploads. Mirrors practice-service's per-section quota, scoped to
    paper here since that's this service's authoring unit."""
    from django.db.models import Sum
    q_total = Question.objects.filter(set__paper_id=paper_id).aggregate(
        s=Sum("question_image_size_bytes")
    )["s"] or 0
    # Option images aren't separately quota-tracked by size today (no
    # size field on QuestionOption — only question images set one) — options
    # are small (single-answer illustrations), tracked implicitly via
    # MAX_IMAGE_SIZE per-file only. Extending this if usage shows it matters.
    new_total = q_total - exclude_bytes + additional_bytes
    return new_total <= MAX_BYTES_PER_PAPER


def _validate_image_presign_request(filename: str, content_type: str):
    """Returns an error message, or None. Extension/MIME are both
    attacker-controlled at this stage — fast client-facing rejection only;
    the real check happens in verify_uploaded_image once the object lands
    in storage."""
    import os
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return f"Extension '{ext}' not allowed. Allowed: {ALLOWED_IMAGE_EXTENSIONS}"
    if not any(content_type.startswith(p) for p in _ALLOWED_IMAGE_MIME):
        return "Unsupported image format. Allowed: JPEG, PNG, WebP, GIF, AVIF."
    return None


def _generate_image_presign(filename: str, content_type: str):
    """Returns (payload, error_response) — payload is None on failure.
    Shared by all three presign views (question/option/set-scoped)."""
    error = _validate_image_presign_request(filename, content_type)
    if error:
        return None, error_response(error, status_code=400)

    file_key = build_file_key("image", filename)
    try:
        upload_url = generate_presigned_upload_url(file_key, content_type)
    except RuntimeError as exc:
        logger.error("Storage not configured: %s", exc)
        return None, error_response("File storage is not configured.", status_code=503)
    return {
        "upload_url": upload_url, "file_key": file_key, "cdn_url": get_cdn_url(file_key),
    }, None


# ── Admin: Question Papers ──────────────────────────────────────────────────────

class AdminPaperListCreateView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        institution_id = _get_institution_id(request)
        papers = QuestionPaper.objects.filter(
            institution_id=institution_id
        ).annotate(set_count=Count("sets"))

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(papers, request)
        data = QuestionPaperSerializer(page, many=True).data

        # "Created by <name>" per card — one batch call for the whole page,
        # not one per paper. created_by has no FK (cross-service isolation —
        # see QuestionPaper.created_by's own comment), so the name/email
        # live in auth-service and must be resolved live. Best-effort:
        # resolve_user_names degrades to {} on any failure rather than
        # raising, so the papers list itself never breaks over this — a
        # paper whose creator didn't resolve just shows created_by_name=""
        # (the frontend falls back to the creator's id in that case).
        creator_ids = sorted({row["created_by"] for row in data if row.get("created_by")})
        # Explicit early-exit rather than relying on resolve_user_names' own
        # internal no-op-on-empty behavior — an empty page (or one whole
        # institution with zero papers) shouldn't even attempt the call.
        creators = resolve_user_names(creator_ids, request.META.get("HTTP_AUTHORIZATION", "")) if creator_ids else {}
        for row in data:
            info = creators.get(row["created_by"], {})
            row["created_by_name"] = info.get("name", "")
            row["created_by_email"] = info.get("email", "")

        return paginator.get_paginated_response(data)

    def post(self, request):
        institution_id = _get_institution_id(request)
        s = QuestionPaperSerializer(data=request.data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save(institution_id=institution_id, created_by=request.user.id)
        return success_response(data=s.data, status_code=201, message="Paper created")


class AdminPaperDetailView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def _get(self, pk, institution_id):
        return get_object_or_404(QuestionPaper, pk=pk, institution_id=institution_id)

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        paper = self._get(pk, institution_id)
        denied = _require_paper_owner(paper, request)
        if denied:
            return denied
        sets = paper.sets.annotate(question_count=Count("questions"))
        return success_response(data={
            "paper": QuestionPaperSerializer(paper).data,
            "sets": QuestionSetSerializer(sets, many=True).data,
        })

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        paper = self._get(pk, institution_id)
        denied = _require_paper_owner(paper, request)
        if denied:
            return denied
        if paper.is_locked():
            return error_response("This paper is assigned and locked.", status_code=403)
        s = QuestionPaperSerializer(paper, data=request.data, partial=True)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save()
        return success_response(data=s.data, message="Paper updated")

    def delete(self, request, pk):
        institution_id = _get_institution_id(request)
        paper = self._get(pk, institution_id)
        denied = _require_paper_owner(paper, request)
        if denied:
            return denied
        if paper.is_locked():
            return error_response("This paper is assigned and locked.", status_code=403)
        paper.delete()
        return success_response(message="Paper deleted")


class AdminPaperInstructionsView(APIView):
    """Rules/instructions text shown to students before they can start the
    exam (student/assignments/ list -> the Start-Exam gate). Deliberately
    NOT gated by paper.is_locked() — unlike every other paper edit, this is
    read-only guidance text that can't corrupt exam integrity or scores, so
    an admin must still be able to write/fix it after the paper is already
    assigned (the common case, since assignment now happens right after
    authoring — see get_assignment_readiness_blockers)."""
    permission_classes = [IsAdminOrSuperAdmin]

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        paper = get_object_or_404(QuestionPaper, pk=pk, institution_id=institution_id)
        denied = _require_paper_owner(paper, request)
        if denied:
            return denied
        instructions = request.data.get("instructions", "")
        if not isinstance(instructions, str):
            return error_response("instructions must be a string.", status_code=400)
        paper.instructions = instructions
        paper.save(update_fields=["instructions", "updated_at"])
        return success_response(data=QuestionPaperSerializer(paper).data, message="Instructions saved")


# ── Admin: Question Sets ─────────────────────────────────────────────────────────

class AdminPaperSetsView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        paper = get_object_or_404(QuestionPaper, pk=pk, institution_id=institution_id)
        denied = _require_paper_owner(paper, request)
        if denied:
            return denied
        if paper.is_locked():
            return error_response("This paper is assigned and locked.", status_code=403)

        data = {**request.data, "paper": str(paper.id)}
        if not data.get("order"):
            max_order = paper.sets.aggregate(m=Max("order"))["m"] or 0
            data["order"] = max_order + 1

        s = QuestionSetSerializer(data=data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save()
        return success_response(data=s.data, status_code=201, message="Set created")


class AdminSetDetailView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def _get(self, pk, institution_id):
        return get_object_or_404(
            QuestionSet.objects.select_related("paper"),
            pk=pk, paper__institution_id=institution_id,
        )

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        qset = self._get(pk, institution_id)
        denied = _require_paper_owner(qset.paper, request)
        if denied:
            return denied
        questions = qset.questions.all()
        return success_response(data={
            "set": QuestionSetSerializer(qset).data,
            "paper": QuestionPaperSerializer(qset.paper).data,
            "questions": QuestionSerializer(questions, many=True).data,
        })

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        qset = self._get(pk, institution_id)
        denied = _require_paper_owner(qset.paper, request)
        if denied:
            return denied
        if qset.paper.is_locked():
            return error_response("This paper is assigned and locked.", status_code=403)
        s = QuestionSetSerializer(qset, data=request.data, partial=True)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save()
        return success_response(data=s.data, message="Set updated")

    def delete(self, request, pk):
        institution_id = _get_institution_id(request)
        qset = self._get(pk, institution_id)
        denied = _require_paper_owner(qset.paper, request)
        if denied:
            return denied
        if qset.paper.is_locked():
            return error_response("This paper is assigned and locked.", status_code=403)
        qset.delete()
        return success_response(message="Set deleted")


# ── Admin: Questions ───────────────────────────────────────────────────────────

class AdminSetQuestionsView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        qset = get_object_or_404(
            QuestionSet.objects.select_related("paper"),
            pk=pk, paper__institution_id=institution_id,
        )
        denied = _require_paper_owner(qset.paper, request)
        if denied:
            return denied
        if qset.paper.is_locked():
            return error_response("This paper is assigned and locked.", status_code=403)

        content_type = request.data.get("question_content_type", "text")
        image_key = request.data.get("question_image_key", "")
        blocker = get_content_type_blocker(
            content_type,
            request.data.get("question_text", ""),
            image_key,
        )
        if blocker:
            return error_response(blocker, status_code=400)

        # An image can now be uploaded (via AdminSetImagePresignView) before
        # the question exists — e.g. content_type='image'/'both' need an
        # image key present on this very first save. That image was never
        # scanned/quota-checked at presign time (presigning only issues an
        # upload URL), so it must go through the same verify+quota gate
        # AdminQuestionDetailView.patch already applies on every later image
        # change — otherwise a first-save image would skip both checks.
        real_size = None
        if image_key:
            real_size, err = _verify_and_scan_image(image_key)
            if err:
                return err
            if not _paper_image_quota_ok(qset.paper_id, exclude_bytes=0, additional_bytes=real_size):
                try:
                    delete_file(image_key)
                except Exception:
                    logger.warning("Failed to clean up over-quota image key=%s", image_key)
                return error_response(
                    "This paper has reached its image storage limit. Remove some images before adding more.",
                    status_code=400,
                )

        data = {**request.data, "set": str(qset.id)}
        s = QuestionSerializer(data=data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        question = s.save()
        if real_size is not None:
            question.question_image_size_bytes = real_size
            question.save(update_fields=["question_image_size_bytes"])
        return success_response(data=QuestionSerializer(question).data, status_code=201, message="Question created")


class AdminQuestionDetailView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def _get(self, pk, institution_id):
        return get_object_or_404(
            Question.objects.select_related("set__paper"),
            pk=pk, set__paper__institution_id=institution_id,
        )

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        question = self._get(pk, institution_id)
        denied = _require_paper_owner(question.set.paper, request)
        if denied:
            return denied
        options = question.options.all()
        return success_response(data={
            "question": QuestionSerializer(question).data,
            "set": QuestionSetSerializer(question.set).data,
            "options": QuestionOptionSerializer(options, many=True).data,
        })

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        question = self._get(pk, institution_id)
        denied = _require_paper_owner(question.set.paper, request)
        if denied:
            return denied
        if question.set.paper.is_locked():
            return error_response("This paper is assigned and locked.", status_code=403)

        content_type = request.data.get("question_content_type", question.question_content_type)
        text = request.data.get("question_text", question.question_text)
        image_key_in_payload = "question_image_key" in request.data
        new_image_key = request.data.get("question_image_key", question.question_image_key)
        blocker = get_content_type_blocker(content_type, text, new_image_key)
        if blocker:
            return error_response(blocker, status_code=400)

        real_size = None
        if image_key_in_payload and new_image_key and new_image_key != question.question_image_key:
            real_size, err = _verify_and_scan_image(new_image_key)
            if err:
                return err
            if not _paper_image_quota_ok(
                question.set.paper_id,
                exclude_bytes=question.question_image_size_bytes or 0,
                additional_bytes=real_size,
            ):
                try:
                    delete_file(new_image_key)
                except Exception:
                    logger.warning("Failed to clean up over-quota image key=%s", new_image_key)
                return error_response(
                    "This paper has reached its image storage limit. Remove some images before adding more.",
                    status_code=400,
                )

        # Switching mcq_type "multiple" -> "single" while 2+ options are
        # already marked correct would otherwise silently leave the
        # question in an inconsistent state (single-choice with multiple
        # correct answers) — the option-level endpoints already guard the
        # other direction (rejecting a 2nd correct option on a
        # single-choice question), so this closes the same gap
        # symmetrically rather than leaving it asymmetric. Found during a
        # live bug report: the frontend's "Answer Type" toggle used to be
        # local-only (never PATCHed here at all) until this same fix.
        new_mcq_type = request.data.get("mcq_type", question.mcq_type)
        if new_mcq_type == MCQ_TYPE_SINGLE and question.mcq_type != MCQ_TYPE_SINGLE:
            if question.options.filter(is_correct=True).count() > 1:
                return error_response(
                    "This question has more than one correct option marked — "
                    "unset all but one before switching to Single Correct.",
                    status_code=400,
                )

        old_image_key = question.question_image_key
        s = QuestionSerializer(question, data=request.data, partial=True)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        question = s.save()
        if real_size is not None:
            question.question_image_size_bytes = real_size
            question.save(update_fields=["question_image_size_bytes"])
        elif image_key_in_payload and not new_image_key:
            question.question_image_size_bytes = None
            question.save(update_fields=["question_image_size_bytes"])

        if old_image_key and old_image_key != question.question_image_key:
            try:
                delete_file(old_image_key)
            except Exception:
                logger.warning("Failed to delete replaced image key=%s", old_image_key)

        return success_response(data=QuestionSerializer(question).data, message="Question updated")

    def delete(self, request, pk):
        institution_id = _get_institution_id(request)
        question = self._get(pk, institution_id)
        denied = _require_paper_owner(question.set.paper, request)
        if denied:
            return denied
        if question.set.paper.is_locked():
            return error_response("This paper is assigned and locked.", status_code=403)
        image_key = question.question_image_key
        question.delete()
        if image_key:
            try:
                delete_file(image_key)
            except Exception:
                logger.warning("Failed to delete removed question's image key=%s", image_key)
        return success_response(message="Question deleted")


# ── Admin: Question Options ───────────────────────────────────────────────────

class AdminQuestionOptionsView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        question = get_object_or_404(
            Question.objects.select_related("set__paper"),
            pk=pk, set__paper__institution_id=institution_id,
        )
        denied = _require_paper_owner(question.set.paper, request)
        if denied:
            return denied
        options = question.options.all()
        return success_response(data=QuestionOptionSerializer(options, many=True).data)

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        question = get_object_or_404(
            Question.objects.select_related("set__paper"),
            pk=pk, set__paper__institution_id=institution_id,
        )
        denied = _require_paper_owner(question.set.paper, request)
        if denied:
            return denied
        if question.set.paper.is_locked():
            return error_response("This paper is assigned and locked.", status_code=403)

        data = dict(request.data)
        data["question"] = str(question.id)
        if not data.get("label"):
            count = question.options.count()
            data["label"] = (
                _OPTION_LABELS[count] if count < len(_OPTION_LABELS) else str(count + 1)
            )
        if not data.get("order"):
            max_order = question.options.aggregate(m=Max("order"))["m"] or 0
            data["order"] = max_order + 1

        wants_correct = str(data.get("is_correct", False)).lower() in ("true", "1")
        if wants_correct and question.mcq_type == MCQ_TYPE_SINGLE:
            if question.options.filter(is_correct=True).exists():
                return error_response(
                    "A single-choice question can only have one correct answer. "
                    "Unset the existing correct option first.",
                    status_code=400,
                )

        s = QuestionOptionSerializer(data=data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save()
        return success_response(data=s.data, status_code=201, message="Option created")


class AdminQuestionOptionDetailView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def _get(self, pk, option_pk, institution_id):
        return get_object_or_404(
            QuestionOption.objects.select_related("question__set__paper"),
            pk=option_pk, question_id=pk,
            question__set__paper__institution_id=institution_id,
        )

    def patch(self, request, pk, option_pk):
        institution_id = _get_institution_id(request)
        option = self._get(pk, option_pk, institution_id)
        question = option.question
        denied = _require_paper_owner(question.set.paper, request)
        if denied:
            return denied
        if question.set.paper.is_locked():
            return error_response("This paper is assigned and locked.", status_code=403)

        wants_correct = "is_correct" in request.data and str(request.data.get("is_correct")).lower() in ("true", "1")
        if wants_correct and question.mcq_type == MCQ_TYPE_SINGLE:
            if question.options.exclude(pk=option_pk).filter(is_correct=True).exists():
                return error_response(
                    "A single-choice question can only have one correct answer. "
                    "Unset the existing correct option first.",
                    status_code=400,
                )

        s = QuestionOptionSerializer(option, data=request.data, partial=True)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save()
        return success_response(data=s.data, message="Option updated")

    def delete(self, request, pk, option_pk):
        institution_id = _get_institution_id(request)
        option = self._get(pk, option_pk, institution_id)
        denied = _require_paper_owner(option.question.set.paper, request)
        if denied:
            return denied
        if option.question.set.paper.is_locked():
            return error_response("This paper is assigned and locked.", status_code=403)
        image_key = option.image_key
        option.delete()
        if image_key:
            try:
                delete_file(image_key)
            except Exception:
                logger.warning("Failed to delete removed option's image key=%s", image_key)
        return success_response(message="Option deleted")


# ── Admin: Image presign ───────────────────────────────────────────────────────

class AdminQuestionImagePresignView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        question = get_object_or_404(
            Question.objects.select_related("set__paper"),
            pk=pk, set__paper__institution_id=institution_id,
        )
        denied = _require_paper_owner(question.set.paper, request)
        if denied:
            return denied
        filename = request.data.get("filename", "image.jpg") or "image.jpg"
        content_type = request.data.get("content_type", "image/jpeg") or "image/jpeg"
        payload, error = _generate_image_presign(filename, content_type)
        if error:
            return error
        return success_response(data=payload)


class AdminOptionImagePresignView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk, option_pk):
        institution_id = _get_institution_id(request)
        option = get_object_or_404(
            QuestionOption.objects.select_related("question__set__paper"),
            pk=option_pk, question_id=pk,
            question__set__paper__institution_id=institution_id,
        )
        denied = _require_paper_owner(option.question.set.paper, request)
        if denied:
            return denied
        filename = request.data.get("filename", "image.jpg") or "image.jpg"
        content_type = request.data.get("content_type", "image/jpeg") or "image/jpeg"
        payload, error = _generate_image_presign(filename, content_type)
        if error:
            return error
        return success_response(data=payload)


class AdminSetImagePresignView(APIView):
    """Presign for a question image before the question itself exists —
    scoped to the QuestionSet it will be created in, since that's the only
    stable id available at that point. Without this, content_type='image'
    or 'both' could never be used on a question's first save: the
    question-level presign endpoint above needs a question id, but
    content_type='both' can't be saved without an image already attached
    (get_content_type_blocker), and content_type='image' shouldn't force
    typing throwaway text just to unlock the upload UI. Live bug report,
    2026-08-14 — see AdminSetQuestionsView.post for the matching
    verify/quota gate applied when this presigned image is attached."""
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        qset = get_object_or_404(
            QuestionSet.objects.select_related("paper"),
            pk=pk, paper__institution_id=institution_id,
        )
        denied = _require_paper_owner(qset.paper, request)
        if denied:
            return denied
        filename = request.data.get("filename", "image.jpg") or "image.jpg"
        content_type = request.data.get("content_type", "image/jpeg") or "image/jpeg"
        payload, error = _generate_image_presign(filename, content_type)
        if error:
            return error
        return success_response(data=payload)


# ── Admin: Batch Assignments ────────────────────────────────────────────────────

class _RosterSnapshotFailed(Exception):
    """Internal-only: lets a roster-snapshot failure unwind out of
    transaction.atomic() (rolling everything back) while still being
    distinguishable from an unexpected error in the outer except clause."""


class AdminAssignmentListCreateView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        institution_id = _get_institution_id(request)
        # select_related("paper") makes BatchAssignmentSerializer's new
        # paper_title field free — one JOIN, not one extra query per row.
        qs = BatchAssignment.objects.filter(institution_id=institution_id).select_related("paper")
        paper_id = request.query_params.get("paper_id")
        if paper_id:
            qs = qs.filter(paper_id=paper_id)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(BatchAssignmentSerializer(page, many=True).data)

    def post(self, request):
        institution_id = _get_institution_id(request)
        paper = get_object_or_404(
            QuestionPaper, pk=request.data.get("paper"), institution_id=institution_id
        )
        # Assigning is part of the paper-authoring flow (initiated from the
        # paper's own page), not the results/analytics/dashboard side of
        # this app — so it's gated by the same creator-only restriction as
        # opening/editing the paper, per the same user decision that
        # introduced _require_paper_owner.
        denied = _require_paper_owner(paper, request)
        if denied:
            return denied
        # Publish/unpublish removed from the admin workflow (user decision,
        # 2026-08-14) — "assign" is now the sole gate a paper must pass
        # before it can go live, so every readiness check that used to live
        # behind publish/ (content completeness, correct-answer counts) runs
        # here instead, plus new cross-set uniformity checks that publish
        # never enforced as a hard block.
        blockers = get_assignment_readiness_blockers(paper)
        if blockers:
            return error_response(
                "Cannot assign: " + " ".join(blockers),
                errors={"assign": blockers},
                status_code=400,
            )

        # Same paper -> many different batches is normal usage (e.g. one
        # mock test rolled out batch by batch). Same paper -> the SAME batch
        # twice has no legitimate use case — it just double-allocates the
        # same students into two independently-tracked exam attempts. Only
        # blocked while an assignment is still SCHEDULED/LIVE — a CLOSED one
        # doesn't count, so re-assigning the same paper to the same batch
        # later (e.g. a retake, next term) is still allowed.
        batch_id = request.data.get("batch_id")
        if batch_id and BatchAssignment.objects.filter(
            paper=paper, batch_id=batch_id, institution_id=institution_id,
            status__in=[ASSIGNMENT_STATUS_SCHEDULED, ASSIGNMENT_STATUS_LIVE],
        ).exists():
            return error_response(
                "This paper is already assigned to this batch and hasn't been closed yet.",
                status_code=400,
            )

        s = BatchAssignmentSerializer(data=request.data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        try:
            with transaction.atomic():
                assignment = s.save(institution_id=institution_id, created_by=request.user.id)
                try:
                    snapshot_roster_and_allocate(assignment, auth_header)
                except RuntimeError as exc:
                    # Roll back the whole transaction — the assignment itself
                    # must not exist if its roster snapshot failed, per Task
                    # 3.1's "no partial/corrupt allocation state" requirement.
                    raise _RosterSnapshotFailed(str(exc)) from exc
        except _RosterSnapshotFailed as exc:
            logger.warning("Assignment creation rolled back — roster snapshot failed: %s", exc)
            return error_response(f"Could not create assignment: {exc}", status_code=502)

        return success_response(
            data=BatchAssignmentSerializer(assignment).data, status_code=201, message="Assignment created",
        )


class AdminAssignmentDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(BatchAssignment, pk=pk, institution_id=institution_id)
        return success_response(data=BatchAssignmentSerializer(assignment).data)


class AdminAssignmentStartView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(
            BatchAssignment.objects.select_related("paper"), pk=pk, institution_id=institution_id,
        )
        # Publish/unpublish removed from the admin workflow (2026-08-14) —
        # readiness (content completeness, correct-answer counts, cross-set
        # uniformity) is now fully checked at assignment-creation time
        # (get_assignment_readiness_blockers), and the paper is locked the
        # moment that assignment exists, so nothing can have regressed by
        # the time Start Exam is clicked. No separate is_published gate here.

        # Conditional UPDATE ... WHERE status=SCHEDULED — race-safe against
        # concurrent Start clicks: only the request that actually flips the
        # row wins, the other sees updated=0 and reports the resulting state.
        updated = BatchAssignment.objects.filter(
            pk=assignment.pk, status=ASSIGNMENT_STATUS_SCHEDULED,
        ).update(
            status=ASSIGNMENT_STATUS_LIVE,
            global_start_time=assignment.global_start_time or timezone.now(),
        )
        assignment.refresh_from_db()

        if not updated:
            if assignment.status == ASSIGNMENT_STATUS_LIVE:
                return success_response(
                    data=BatchAssignmentSerializer(assignment).data, message="Exam is already live",
                )
            return error_response(
                f"Cannot start an assignment with status {assignment.status}.", status_code=409,
            )

        return success_response(data=BatchAssignmentSerializer(assignment).data, message="Exam started")


class AdminAssignmentCloseView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(BatchAssignment, pk=pk, institution_id=institution_id)

        BatchAssignment.objects.filter(pk=assignment.pk).exclude(
            status=ASSIGNMENT_STATUS_CLOSED,
        ).update(status=ASSIGNMENT_STATUS_CLOSED)
        assignment.refresh_from_db()

        # Cascade: every IN_PROGRESS session under this now-CLOSED
        # assignment is finalized immediately, not left dangling until its
        # own ends_at — this is the actual "stop everyone now" behavior an
        # emergency close needs. Reuses the exact same primitive the beat
        # sweep uses (Task 4.1) — not a separate implementation.
        auto_submitted = finalize_sessions(assignment.sessions.all(), SESSION_STATUS_AUTO_SUBMITTED)

        return success_response(
            data={**BatchAssignmentSerializer(assignment).data, "sessions_auto_submitted": auto_submitted},
            message="Assignment closed",
        )


class AdminAssignmentResyncRosterView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(BatchAssignment, pk=pk, institution_id=institution_id)
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        try:
            new_count = snapshot_roster_and_allocate(assignment, auth_header)
        except RuntimeError as exc:
            return error_response(f"Could not resync roster: {exc}", status_code=502)
        return success_response(
            data={"new_allocations": new_count}, message="Roster resynced",
        )


class AdminAssignmentExtendSessionView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk, session_id):
        institution_id = _get_institution_id(request)
        # Validate assignment ownership first — a request against an
        # assignment this admin doesn't own 404s here, before we even look
        # for the session, rather than leaking existence via a different
        # error shape.
        get_object_or_404(BatchAssignment, pk=pk, institution_id=institution_id)

        session = get_object_or_404(AssessmentSession, pk=session_id, assignment_id=pk)

        try:
            extend_minutes = int(request.data.get("extend_minutes", 0))
        except (TypeError, ValueError):
            return error_response("extend_minutes must be an integer.", status_code=400)
        if extend_minutes <= 0:
            return error_response("extend_minutes must be a positive integer.", status_code=400)
        # Task 12.2's abuse-hardening audit: an unbounded extend_minutes
        # crashed this endpoint with an unhandled OverflowError
        # ("date value out of range") once `session.ends_at + timedelta(
        # minutes=extend_minutes)` exceeded datetime's representable range
        # — a malformed/oversized payload producing a 500, not the clean
        # 400 every other bad-input path here already returns. 1440
        # minutes (24 hours) is already far beyond any legitimate one-off
        # extension this action is meant for (a student's technical
        # difficulty during a single exam sitting).
        if extend_minutes > 1440:
            return error_response("extend_minutes cannot exceed 1440 (24 hours).", status_code=400)

        if session.status != SESSION_STATUS_IN_PROGRESS:
            return error_response(
                f"Cannot extend a session with status {session.status} — it has already finished.",
                status_code=409,
            )

        # This is the ONLY exception to "ends_at is computed once and never
        # recomputed" (ADR 001) — a targeted, audited override. Editing
        # global_expire_time on the assignment has no effect on an
        # already-frozen session.ends_at; this direct patch is the only way
        # to actually give one affected student more time.
        new_ends_at = session.ends_at + timedelta(minutes=extend_minutes)
        AssessmentSession.objects.filter(pk=session.pk).update(ends_at=new_ends_at)
        session.refresh_from_db()

        return success_response(
            data={"session_id": str(session.id), "ends_at": session.ends_at},
            message=f"Session extended by {extend_minutes} minute(s).",
        )


class AdminAssignmentStatusView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(BatchAssignment, pk=pk, institution_id=institution_id)
        return success_response(data={
            "status": assignment.status,
            "student_count_total": assignment.allocations.count(),
            "student_count_completed": assignment.sessions.filter(
                status__in=[SESSION_STATUS_SUBMITTED, SESSION_STATUS_AUTO_SUBMITTED],
            ).count(),
        })


# ── Student: Server-Time Sync ───────────────────────────────────────────────

class StudentServerTimeView(APIView):
    """GET /api/assessments/student/server-time/ (Task 4.2, ADR 001).

    The client's countdown is cosmetic only — it renders from this endpoint
    so client clock drift, tampering, or a paused tab never affects what the
    server will actually accept on a write (Phase 5's submit/autosave
    endpoints are the real enforcement, via enforcement.session_is_writable()).
    """
    permission_classes = [IsStudentUser]

    def get(self, request):
        data = {"server_time": timezone.now()}

        # A student could in principle have more than one IN_PROGRESS
        # session if multiple assignments are live at once — the most
        # recently started one is what the currently-open exam tab cares
        # about. Filtered by the requesting student's own JWT identity only
        # (IDOR-safe, AT3) — never a client-supplied student identifier.
        session = (
            AssessmentSession.objects.filter(
                student_id=request.user.id, status=SESSION_STATUS_IN_PROGRESS,
            )
            .order_by("-started_at")
            .first()
        )
        if session is not None:
            data["session_id"] = str(session.id)
            data["ends_at"] = session.ends_at

        return success_response(data=data)


# ── Student: Assignments & Session Start/Resume (Task 5.1) ─────────────────────

class StudentAssignmentListView(APIView):
    """GET /api/assessments/student/assignments/ — everything this student
    has been allocated to, gated purely by StudentSetAllocation existing
    (IDOR-safe: filtered by the requesting student's own JWT identity, never
    a client-supplied one) — no separate per-assignment call needed to know
    whether it's waiting, live, or closed."""
    permission_classes = [IsStudentUser]

    def get(self, request):
        allocations = (
            StudentSetAllocation.objects.filter(student_id=request.user.id)
            .select_related("assignment__paper")
        )
        assignment_ids = [a.assignment_id for a in allocations]

        # Own-session status per assignment, if a session was ever started
        # — lets the frontend show "Resume" vs "Start" vs "Completed"
        # without a second round trip per assignment.
        session_status_by_assignment = dict(
            AssessmentSession.objects.filter(
                student_id=request.user.id, assignment_id__in=assignment_ids,
            ).values_list("assignment_id", "status")
        )

        results = []
        for alloc in allocations:
            assignment = alloc.assignment
            results.append({
                "assignment_id": str(assignment.id),
                "paper_title": assignment.paper.title,
                "paper_instructions": assignment.paper.instructions,
                "status": assignment.status,
                "exam_duration_minutes": assignment.exam_duration_minutes,
                "global_start_time": assignment.global_start_time,
                "global_expire_time": assignment.global_expire_time,
                "session_status": session_status_by_assignment.get(assignment.id),
            })

        return success_response(data=results)


class StudentAssignmentStartSessionView(APIView):
    """POST /api/assessments/student/assignments/<id>/start-session/ —
    idempotent create-or-resume. A page refresh mid-exam calls this again
    and gets the SAME session back, same ends_at, never a reset."""
    permission_classes = [IsStudentUser]

    def post(self, request, pk):
        assignment = get_object_or_404(BatchAssignment.objects.select_related("paper"), pk=pk)

        # IDOR + allocation guard, in one query: 404 for both "no such
        # assignment" and "not allocated to it" — never distinguish the two
        # in the response, so a student can't probe for assignment
        # existence outside their own allocation (AT3).
        allocation = StudentSetAllocation.objects.filter(
            assignment=assignment, student_id=request.user.id,
        ).select_related("set").first()
        if allocation is None:
            return error_response("Assessment not found.", status_code=404)

        # Resume path — return the existing session untouched if one
        # already exists, before even checking LIVE/expiry again. A
        # student who started while LIVE and is now refreshing after the
        # admin closed the assignment must still be able to see their own
        # session (e.g. to observe it was auto-submitted), not get locked
        # out of their own resume call.
        existing = AssessmentSession.objects.filter(
            assignment=assignment, student_id=request.user.id,
        ).first()
        if existing is not None:
            return success_response(
                data={"session_id": str(existing.id), "ends_at": existing.ends_at, "status": existing.status},
                message="Session resumed",
            )

        if assignment.status != ASSIGNMENT_STATUS_LIVE:
            return error_response("This assessment is not yet live.", status_code=403)
        if timezone.now() >= assignment.global_expire_time:
            # Status may not have been swept to CLOSED yet (sweep lag, ADR
            # 001) — reject anyway rather than create an already-expired
            # session. This student becomes EXPIRED_UNSTARTED territory
            # (Phase 7/8 results), not an IN_PROGRESS session with 0 time left.
            return error_response("This assessment has expired.", status_code=403)

        ends_at = min(
            timezone.now() + timedelta(minutes=assignment.exam_duration_minutes),
            assignment.global_expire_time,
        )
        try:
            session = AssessmentSession.objects.create(
                assignment=assignment, student_id=request.user.id,
                set=allocation.set, ends_at=ends_at,
            )
        except IntegrityError:
            # Lost a create race against a concurrent request for the same
            # student+assignment (unique_together) — the winner's row is
            # what we resume from.
            session = AssessmentSession.objects.get(assignment=assignment, student_id=request.user.id)
            return success_response(
                data={"session_id": str(session.id), "ends_at": session.ends_at, "status": session.status},
                message="Session resumed",
            )

        return success_response(
            data={"session_id": str(session.id), "ends_at": session.ends_at, "status": session.status},
            status_code=201, message="Session started",
        )


# ── Student: Answer Submission & Submit (Task 5.2) ──────────────────────────

class StudentAnswerView(APIView):
    """PUT /api/assessments/student/sessions/<id>/questions/<qid>/answer/ —
    idempotent upsert. is_correct/marks_awarded are intentionally NOT
    computed here — scoring happens once, at finalize time
    (scoring.finalize_sessions()), from the frozen response set.

    Rate-limited per student (Task 11.2) — see AnswerSubmitRateThrottle's
    docstring for the exact threshold and its rationale."""
    permission_classes = [IsStudentUser]
    throttle_classes = [AnswerSubmitRateThrottle]

    def put(self, request, pk, qid):
        # IDOR-safe: a session only resolves for its own owning student.
        session = get_object_or_404(
            AssessmentSession.objects.select_related("assignment"),
            pk=pk, student_id=request.user.id,
        )
        # The question must belong to THIS session's own allocated set —
        # not just any question in the paper (closes the "answer a
        # question from a set I wasn't allocated" security case).
        question = get_object_or_404(Question, pk=qid, set_id=session.set_id)

        ok, reason = session_is_writable(session, session.assignment)
        if not ok:
            return error_response(reason, status_code=403)

        data = strip_client_timestamps(request.data)
        selected_option_ids = data.get("selected_option_ids", [])
        if not isinstance(selected_option_ids, list):
            return error_response("selected_option_ids must be a list.", status_code=400)

        valid_option_ids = {str(oid) for oid in question.options.values_list("id", flat=True)}
        selected_set = {str(oid) for oid in selected_option_ids}
        if not selected_set.issubset(valid_option_ids):
            return error_response(
                "One or more selected options do not belong to this question.", status_code=400,
            )

        try:
            response_obj, _ = AssessmentResponse.objects.update_or_create(
                session=session, question=question,
                defaults={"selected_option_ids": sorted(selected_set)},
            )
        except IntegrityError:
            # Lost an upsert race against a concurrent identical PUT for
            # the same (session, question) — e.g. a genuine network retry
            # racing the original. The winner's row already holds
            # equivalent data; just report the current state.
            response_obj = AssessmentResponse.objects.get(session=session, question=question)

        return success_response(
            data={
                "question_id": str(question.id),
                "selected_option_ids": response_obj.selected_option_ids,
                "answered_at": response_obj.answered_at,
            },
            message="Answer saved",
        )


class StudentSubmitView(APIView):
    """POST /api/assessments/student/sessions/<id>/submit/ — final manual
    submit. Reuses finalize_sessions() (Task 4.1/5.2) — the exact same
    race-safe primitive the beat sweep and admin close/ cascade use, so a
    submit racing either of those can never double-score or corrupt state."""
    permission_classes = [IsStudentUser]

    def post(self, request, pk):
        session = get_object_or_404(
            AssessmentSession.objects.select_related("assignment"),
            pk=pk, student_id=request.user.id,
        )

        ok, reason = session_is_writable(session, session.assignment)
        if not ok:
            return error_response(reason, status_code=403)

        finalize_sessions(AssessmentSession.objects.filter(pk=session.pk), SESSION_STATUS_SUBMITTED)

        session.refresh_from_db()
        result = getattr(session, "result", None)
        show_result = session.assignment.show_result_to_student
        return success_response(
            data={
                "session_id": str(session.id),
                "status": session.status,
                "results_visible": show_result,
                "score": result.score if result and show_result else None,
                "total_marks": result.total_marks if result and show_result else None,
            },
            message="Submitted",
        )


class StudentSessionQuestionsView(APIView):
    """GET /api/assessments/student/sessions/<id>/questions/ — the actual
    question list for this session's allocated set, for the exam-taking UI
    (Task 5.4). Uses StudentQuestionSerializer, which never includes
    is_correct — leaking that would hand the student the answer key.
    Each question also carries the student's own previously-saved
    selected_option_ids (if any), so resuming a session shows prior answers."""
    permission_classes = [IsStudentUser]

    def get(self, request, pk):
        session = get_object_or_404(
            AssessmentSession.objects.select_related("set"), pk=pk, student_id=request.user.id,
        )
        questions = list(
            session.set.questions.prefetch_related("options").order_by("question_number")
        )
        saved_answers = {
            str(qid): opts for qid, opts in
            AssessmentResponse.objects.filter(session=session).values_list("question_id", "selected_option_ids")
        }

        data = StudentQuestionSerializer(questions, many=True).data
        for q in data:
            q["selected_option_ids"] = saved_answers.get(q["id"], [])

        return success_response(data={
            "session_id": str(session.id),
            "session_status": session.status,
            "ends_at": session.ends_at,
            "questions": data,
        })


# ── Student: Activity Logs (Task 6.2) ───────────────────────────────────────

_ACTIVITY_EVENT_TYPES = {c[0] for c in ACTIVITY_EVENT_TYPE_CHOICES}
_MAX_EVENTS_PER_BATCH = 100


def _parse_occurred_at(raw):
    """Client-reported event time, falling back to server now() if
    missing/unparseable — see ActivityLog.occurred_at's model comment for
    why trusting the client here is acceptable (unlike session timing)."""
    if raw:
        dt = parse_datetime(str(raw))
        if dt is not None:
            return dt if timezone.is_aware(dt) else timezone.make_aware(dt, timezone.utc)
    return timezone.now()


class StudentActivityLogBulkCreateView(APIView):
    """POST /api/assessments/student/sessions/<id>/activity-logs/ —
    bulk-insert a batch of client-captured anti-cheat events (Task 6.1's
    client-side batching lands here). Rate-limited per session, not per
    user, so one compromised/buggy client can't degrade ingestion for
    every other student in the same exam."""
    permission_classes = [IsStudentUser]
    throttle_classes = [ActivityLogRateThrottle]

    def post(self, request, pk):
        session = get_object_or_404(
            AssessmentSession.objects.select_related("assignment"), pk=pk, student_id=request.user.id,
        )

        # Task 12.1's audit found this endpoint was the one mutating
        # student endpoint with no timer/status revalidation at all — every
        # sibling (answer autosave, submit) calls session_is_writable()
        # before accepting a write, this one didn't. Closing it for
        # consistency: once a session is no longer IN_PROGRESS (or its
        # assignment is closed), there is no legitimate reason for a
        # client to keep posting events to it.
        ok, reason = session_is_writable(session, session.assignment)
        if not ok:
            return error_response(reason, status_code=403)

        events = request.data.get("events")
        if not isinstance(events, list) or not events:
            return error_response("events must be a non-empty list.", status_code=400)
        if len(events) > _MAX_EVENTS_PER_BATCH:
            return error_response(
                f"Too many events in one batch (max {_MAX_EVENTS_PER_BATCH}).", status_code=400,
            )

        to_create = []
        for e in events:
            if not isinstance(e, dict):
                continue
            event_type = e.get("event_type")
            if event_type not in _ACTIVITY_EVENT_TYPES:
                # Skip malformed/unknown entries rather than failing the
                # whole batch over one bad event — logging is best-effort
                # audit data, not exam-integrity-critical like an answer.
                continue
            metadata = e.get("metadata")
            to_create.append(ActivityLog(
                session=session,
                event_type=event_type,
                occurred_at=_parse_occurred_at(e.get("occurred_at")),
                metadata=metadata if isinstance(metadata, dict) else {},
            ))

        if to_create:
            ActivityLog.objects.bulk_create(to_create)

        return success_response(data={"logged": len(to_create)}, status_code=201)


# ── Student: Past Results (Task 10.1) ────────────────────────────────────────

class StudentResultsView(APIView):
    """GET /api/assessments/student/results/ — the requesting student's own
    past ResultSummary rows only, filtered strictly by their JWT user_id
    claim (never a client-supplied identifier — same IDOR guarantee as
    every other student endpoint this session, closes AT3).

    Deliberately excludes malpractice_flag/malpractice_reasons: Decision
    #5's thresholds double as scoring.py's bot-defense signal, and handing
    a student the exact detection outcome computed on their own session
    would let them calibrate around it on a future attempt. That detail
    stays admin-only (visible via the Admin Results module, Task 7.x) —
    matching this task's own "no admin-only analytics field" requirement.
    Also excludes AssessmentResponse-level detail entirely (no per-question
    correctness), so a still-open sibling set's correct answers are never
    reachable through this endpoint regardless of assignment status."""
    permission_classes = [IsStudentUser]

    def get(self, request):
        results = (
            ResultSummary.objects.filter(student_id=request.user.id)
            .select_related("assignment__paper")
            .order_by("-ended_at")
        )
        data = []
        for r in results:
            percentage = round(r.score / r.total_marks * 100, 2) if r.total_marks else 0.0
            show_result = r.assignment.show_result_to_student
            data.append({
                "assignment_id": str(r.assignment_id),
                "paper_title": r.assignment.paper.title,
                "results_visible": show_result,
                "score": r.score if show_result else None,
                "total_marks": r.total_marks if show_result else None,
                "percentage": percentage if show_result else None,
                "status": r.status,
                "started_at": r.started_at,
                "ended_at": r.ended_at,
                "duration_seconds": r.duration_seconds,
                "pass_cutoff_percentage": r.assignment.pass_cutoff_percentage,
                "passed": (percentage >= r.assignment.pass_cutoff_percentage) if show_result else None,
            })
        return success_response(data=data)


# ── Admin: Results (Phase 7) ─────────────────────────────────────────────────

# Public sort= query-param values stay the same as before (frontend/exports
# already use these) even though the underlying annotated field names
# changed — see _SORT_FIELD_MAP below.
_RESULTS_ALLOWED_SORTS = {
    "percentage", "-percentage", "duration_seconds", "-duration_seconds",
    "ended_at", "-ended_at", "started_at", "-started_at",
}
_SORT_FIELD_MAP = {
    "percentage": "percentage", "-percentage": "-percentage",
    "duration_seconds": "duration_seconds", "-duration_seconds": "-duration_seconds",
    "ended_at": "result_ended_at", "-ended_at": "-result_ended_at",
    "started_at": "result_started_at", "-started_at": "-result_started_at",
}
_PERCENTAGE_ANNOTATION = Case(
    When(total_marks=0, then=Value(0.0)),
    default=ExpressionWrapper(F("score") * 100.0 / F("total_marks"), output_field=FloatField()),
    output_field=FloatField(),
)
EXAM_STATUS_PENDING   = "pending"
EXAM_STATUS_WRITING   = "writing"
EXAM_STATUS_SUBMITTED = "submitted"


def _build_results_queryset(assignment, request, roster_by_user_id):
    """
    Shared between Task 7.1's table view and Task 7.3's export — the exact
    same filters must apply to both, or a filtered table view and its
    "export these results" button would silently disagree.

    Base is StudentSetAllocation (the roster snapshot taken at assignment
    creation — Task 3.1), not ResultSummary — a table built from
    ResultSummary alone only ever showed students who'd already submitted;
    everyone else the paper was assigned to was simply invisible. This way
    every allocated student has a row from the moment the assignment is
    created, LEFT JOINed (via correlated subqueries, since AssessmentSession
    and ResultSummary are both unique per (assignment, student_id) — never
    more than one row to join) against their session (for exam_status:
    pending/writing/submitted) and result (for score data, once it exists).

    Department filtering can't be a DB column here (department lives in
    user-service's roster, not locally) — instead, the already
    roster-fetched student_ids matching that department become a
    `student_id__in=[...]` DB filter, so pagination/sorting still happen
    entirely at the DB level even with a department filter applied (no
    full-table scan, per this task's load requirement).
    """
    session_sq = AssessmentSession.objects.filter(assignment=assignment, student_id=OuterRef("student_id"))
    result_sq = ResultSummary.objects.filter(assignment=assignment, student_id=OuterRef("student_id"))

    qs = StudentSetAllocation.objects.filter(assignment=assignment).select_related("set").annotate(
        session_status=Subquery(session_sq.values("status")[:1]),
        result_id=Subquery(result_sq.values("id")[:1]),
        score=Subquery(result_sq.values("score")[:1]),
        total_marks=Subquery(result_sq.values("total_marks")[:1]),
        result_started_at=Subquery(result_sq.values("started_at")[:1]),
        result_ended_at=Subquery(result_sq.values("ended_at")[:1]),
        duration_seconds=Subquery(result_sq.values("duration_seconds")[:1]),
        malpractice_flag=Subquery(result_sq.values("malpractice_flag")[:1]),
    ).annotate(
        percentage=Case(
            When(total_marks__gt=0, then=ExpressionWrapper(F("score") * 100.0 / F("total_marks"), output_field=FloatField())),
            When(total_marks=0, then=Value(0.0)),
            default=None,
            output_field=FloatField(),
        ),
        exam_status=Case(
            When(session_status__in=[SESSION_STATUS_SUBMITTED, SESSION_STATUS_AUTO_SUBMITTED], then=Value(EXAM_STATUS_SUBMITTED)),
            When(session_status=SESSION_STATUS_IN_PROGRESS, then=Value(EXAM_STATUS_WRITING)),
            default=Value(EXAM_STATUS_PENDING),
            output_field=CharField(),
        ),
    )

    department = request.query_params.get("department")
    if department:
        matching_ids = [uid for uid, info in roster_by_user_id.items() if info.get("department") == department]
        qs = qs.filter(student_id__in=matching_ids)

    # Roll-number search — case-insensitive substring match against the
    # roster (already fetched once above; same no-extra-call pattern as the
    # department filter), not a DB LIKE, so no wildcard-injection concerns
    # from user-typed "%"/"_". Composes with department via a second,
    # separately-ANDed student_id__in — Django ANDs successive .filter()
    # calls, so "CSE department AND roll contains '004'" narrows correctly
    # rather than one filter silently overwriting the other.
    roll_search = request.query_params.get("student_roll_id", "").strip().lower()
    if roll_search:
        matching_ids = [
            uid for uid, info in roster_by_user_id.items()
            if roll_search in (info.get("student_id") or "").lower()
        ]
        qs = qs.filter(student_id__in=matching_ids)

    # "flagged" is the current param (tri-state: true/false/absent);
    # "flagged_only=true" is kept as a legacy alias for "flagged=true" since
    # the frontend/exports already shipped with it (Task 7.1).
    flagged_param = request.query_params.get("flagged")
    if flagged_param is None and str(request.query_params.get("flagged_only", "")).lower() in ("true", "1"):
        flagged_param = "true"
    if flagged_param is not None:
        if str(flagged_param).lower() in ("true", "1"):
            qs = qs.filter(malpractice_flag=True)
        elif str(flagged_param).lower() in ("false", "0"):
            # Explicit OR-with-isnull, not exclude(malpractice_flag=True) —
            # SQL's three-valued logic means "NOT (NULL = True)" is itself
            # NULL/no-match, so a plain exclude() would silently drop
            # pending/writing students (malpractice_flag NULL — no
            # ResultSummary yet) instead of counting them as "not flagged".
            qs = qs.filter(Q(malpractice_flag=False) | Q(malpractice_flag__isnull=True))

    exam_status_param = request.query_params.get("exam_status")
    if exam_status_param in (EXAM_STATUS_PENDING, EXAM_STATUS_WRITING, EXAM_STATUS_SUBMITTED):
        qs = qs.filter(exam_status=exam_status_param)

    passed_param = request.query_params.get("passed")
    if passed_param is not None:
        cutoff = assignment.pass_cutoff_percentage
        if str(passed_param).lower() in ("true", "1"):
            qs = qs.filter(percentage__gte=cutoff)
        elif str(passed_param).lower() in ("false", "0"):
            # percentage__lt on a NULL percentage (pending/writing) matches
            # nothing in SQL — pending/writing students are correctly
            # excluded from "Failed" too, not just "Passed".
            qs = qs.filter(percentage__lt=cutoff)

    # Lower bound exclusive, upper bound inclusive — so "below 60" and
    # "above 60" partition the class with no gap and no double-count at
    # exactly 60%, and "between 40 and 60" behaves identically to
    # min=40&max=60 rather than needing its own special case.
    min_pct = request.query_params.get("min_percentage")
    if min_pct not in (None, ""):
        qs = qs.filter(percentage__gt=float(min_pct))
    max_pct = request.query_params.get("max_percentage")
    if max_pct not in (None, ""):
        qs = qs.filter(percentage__lte=float(max_pct))

    sort_param = request.query_params.get("sort", "-ended_at")
    sort = _SORT_FIELD_MAP.get(sort_param, "-result_ended_at")
    # Pending/writing students have NULL for every sortable field (no
    # ResultSummary yet) — nulls_last=True pins them to the bottom
    # regardless of direction, instead of relying on the DB's own
    # (backend-specific, easy to get backwards) default null-ordering.
    field_name = sort.lstrip("-")
    order_expr = F(field_name).desc(nulls_last=True) if sort.startswith("-") else F(field_name).asc(nulls_last=True)
    return qs.order_by(order_expr, "-pk")  # -pk: stable tiebreak for rows sharing a NULL sort value


def _fetch_roster_lookup(assignment, request):
    """Returns {user_id_str: roster_dict}, or raises RuntimeError (caller
    converts to a 502 — a roster-fetch failure fails this specific read,
    never the exam-taking path, which never calls user-service live)."""
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    roster = fetch_batch_roster(str(assignment.batch_id), auth_header)
    return {s["user_id"]: s for s in roster if s.get("user_id")}


def _serialize_result_row(alloc, roster_by_user_id):
    info = roster_by_user_id.get(str(alloc.student_id), {})
    return {
        "result_id": str(alloc.result_id) if alloc.result_id else None,
        "student_user_id": str(alloc.student_id),
        "student_roll_id": info.get("student_id", ""),
        "student_name": info.get("fullname") or "Unknown",
        "department": info.get("department") or "",
        "set_label": alloc.set.label,
        "exam_status": alloc.exam_status,
        "started_at": alloc.result_started_at,
        "ended_at": alloc.result_ended_at,
        "duration_seconds": alloc.duration_seconds,
        "score": alloc.score,
        "total_marks": alloc.total_marks,
        "percentage": round(alloc.percentage, 2) if alloc.percentage is not None else None,
        "malpractice_flag": bool(alloc.malpractice_flag),
    }


class AdminAssignmentResultsView(APIView):
    """GET /api/assessments/admin/assignments/<id>/results/ (Task 7.1) —
    paginated, filterable, sortable. Never computed live from raw
    AssessmentResponse data — reads ResultSummary, which Task 4.1/5.2
    write once at finalize time."""
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(BatchAssignment, pk=pk, institution_id=institution_id)

        try:
            roster_by_user_id = _fetch_roster_lookup(assignment, request)
        except RuntimeError as exc:
            return error_response(f"Could not load student roster: {exc}", status_code=502)

        qs = _build_results_queryset(assignment, request, roster_by_user_id)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        rows = [_serialize_result_row(r, roster_by_user_id) for r in page]
        return paginator.get_paginated_response(rows)


class AdminResultResponsesView(APIView):
    """GET /api/assessments/admin/results/<result_id>/responses/ (Task 7.2)
    — resolves ResultSummary.session (Task 4.1's FK), not the reverse:
    ResultSummary itself has no direct question-level detail, only the
    aggregate score."""
    permission_classes = [IsAdminUser]

    def get(self, request, result_id):
        institution_id = _get_institution_id(request)
        result = get_object_or_404(
            ResultSummary.objects.select_related("session__set"),
            pk=result_id, institution_id=institution_id,
        )
        session = result.session

        questions = list(
            session.set.questions.prefetch_related("options").order_by("question_number")
        )
        responses_by_question = {
            r.question_id: r for r in AssessmentResponse.objects.filter(session=session)
        }

        data = []
        for q in questions:
            resp = responses_by_question.get(q.id)
            data.append({
                "question_id": str(q.id),
                "question_number": q.question_number,
                "question_text": q.question_text,
                "question_image_url": get_cdn_url(q.question_image_key) if q.question_image_key else None,
                "marks": q.marks,
                # Admin review view — is_correct on each option is
                # deliberately exposed here (unlike the student-facing
                # StudentQuestionSerializer), since this IS the answer key.
                "options": QuestionOptionSerializer(q.options.all(), many=True).data,
                "selected_option_ids": resp.selected_option_ids if resp else [],
                "is_correct": resp.is_correct if resp else False,
                "marks_awarded": resp.marks_awarded if resp else 0,
                "answered": resp is not None,
            })

        return success_response(data={"result_id": str(result.id), "questions": data})


class AdminResultLogsView(APIView):
    """GET /api/assessments/admin/results/<result_id>/logs/ (Task 7.2) —
    resolves the same ResultSummary.session FK as the responses view.

    Paginated (Task 11.1's index/pagination audit): unlike the per-session
    responses view, the number of activity-log rows for one session is NOT
    bounded by anything the admin authored (a paper's question count is;
    tab-switch/copy/paste events over a multi-hour exam are not) — a single
    session sitting at the 20/min throttle ceiling for a whole exam window
    could accumulate thousands of rows, so this was a genuinely unbounded
    query before this pass."""
    permission_classes = [IsAdminUser]

    def get(self, request, result_id):
        institution_id = _get_institution_id(request)
        result = get_object_or_404(ResultSummary, pk=result_id, institution_id=institution_id)
        logs = ActivityLog.objects.filter(session=result.session).order_by("occurred_at")

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(logs, request)

        return success_response(data={
            "result_id": str(result.id),
            "malpractice_flag": result.malpractice_flag,
            "malpractice_reasons": result.malpractice_reasons,
            "count": paginator.page.paginator.count,
            "total_pages": paginator.page.paginator.num_pages,
            "current_page": paginator.page.number,
            "logs": [
                {"event_type": l.event_type, "occurred_at": l.occurred_at, "metadata": l.metadata}
                for l in page
            ],
        })


class _Echo:
    """A file-like object that just returns what it's given — the standard
    Django pattern for csv.writer to stream rows through StreamingHttpResponse
    instead of materializing the whole CSV in memory."""
    def write(self, value):
        return value


_EXPORT_HEADER = [
    "Student Roll No", "Student Name", "Department", "Set", "Status", "Started At", "Ended At",
    "Duration (seconds)", "Score", "Total Marks", "Percentage", "Flagged",
]


def _export_rows(assignment, request, roster_by_user_id):
    writer = csv.writer(_Echo())
    yield "﻿"  # UTF-8 BOM — matches BulkImportModal.tsx's existing Excel-compatibility convention
    yield writer.writerow(_EXPORT_HEADER)

    qs = _build_results_queryset(assignment, request, roster_by_user_id)
    for r in qs.iterator(chunk_size=500):
        info = roster_by_user_id.get(str(r.student_id), {})
        yield writer.writerow([
            info.get("student_id", ""),
            info.get("fullname") or "Unknown",
            info.get("department") or "",
            r.set.label,
            r.exam_status,
            r.result_started_at.isoformat() if r.result_started_at else "",
            r.result_ended_at.isoformat() if r.result_ended_at else "",
            r.duration_seconds if r.duration_seconds is not None else "",
            r.score if r.score is not None else "",
            r.total_marks if r.total_marks is not None else "",
            f"{round(r.percentage, 2)}" if r.percentage is not None else "",
            "Yes" if r.malpractice_flag else "No",
        ])


class AdminAssignmentResultsExportView(APIView):
    """GET /api/assessments/admin/assignments/<id>/results/export/ (Task
    7.3) — StreamingHttpResponse so a large export never holds the full
    result set in memory server-side. Same filters as Task 7.1's table
    (both built from the identical _build_results_queryset helper), so a
    filtered table view and its export button never silently disagree."""
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(BatchAssignment, pk=pk, institution_id=institution_id)

        try:
            roster_by_user_id = _fetch_roster_lookup(assignment, request)
        except RuntimeError as exc:
            return error_response(f"Could not load student roster: {exc}", status_code=502)

        response = StreamingHttpResponse(
            _export_rows(assignment, request, roster_by_user_id), content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = f'attachment; filename="results_{assignment.id}.csv"'
        return response


# ── Admin: Analytics (Task 8.1) ──────────────────────────────────────────────

ANALYTICS_CACHE_TTL_SECONDS = 60  # short TTL (Task 8.1) — not submission-triggered
                                   # invalidation like Task 9.1's dashboard; a stale
                                   # window of up to 60s is an accepted tradeoff here.

_METRIC_DEFINITIONS = {
    "score_distribution": "Number of completed sessions falling into each 10-percentage-point bucket of score/total_marks (e.g. \"70-80%\" = sessions scoring at least 70% and under 80%; the final bucket includes exactly 100%).",
    "pass_rate_percentage": "Percentage of completed sessions scoring >= the assignment's pass_cutoff_percentage, computed on score/total_marks (not raw score) so students on different sets remain comparable.",
    "percentage_correct": "Per question: (students who answered it correctly / students who attempted it) * 100. Not normalized against other questions — stays scoped to that one question's own attempts. Lower = harder.",
    "average_percentage": "Per department: mean of score/total_marks across that department's completed sessions.",
    "malpractice_rate_percentage": "Percentage of completed sessions with malpractice_flag=True (Task 6.2's threshold rule: tab-switch/fullscreen-exit/cadence).",
}


def _score_distribution(qs):
    buckets = [0] * 10
    for pct in qs.values_list("percentage", flat=True):
        idx = min(int(pct // 10), 9)  # a perfect 100% lands in the last bucket, not a stray 11th one
        buckets[idx] += 1
    return [{"bucket": f"{i * 10}-{(i + 1) * 10}%", "count": buckets[i]} for i in range(10)]


def _pass_fail(qs, cutoff_percentage):
    total = qs.count()
    passed = qs.filter(percentage__gte=cutoff_percentage).count()
    return {
        "pass_count": passed,
        "fail_count": total - passed,
        "pass_rate_percentage": round(passed / total * 100, 2) if total else 0.0,
        "cutoff_percentage": cutoff_percentage,
    }


def _question_difficulty(assignment):
    stats = (
        AssessmentResponse.objects.filter(session__assignment=assignment)
        .values("question_id")
        .annotate(total=Count("id"), correct=Count("id", filter=Q(is_correct=True)))
    )
    stats_by_qid = {s["question_id"]: s for s in stats}

    questions = Question.objects.filter(set__paper=assignment.paper).order_by("set__order", "question_number")
    result = []
    for q in questions:
        s = stats_by_qid.get(q.id, {"total": 0, "correct": 0})
        result.append({
            "question_id": str(q.id),
            "question_number": q.question_number,
            "set_label": q.set.label,
            "total_answered": s["total"],
            "correct_count": s["correct"],
            "percentage_correct": round(s["correct"] / s["total"] * 100, 2) if s["total"] else None,
        })
    return result


def _department_comparison(qs, roster_by_user_id):
    dept_percentages: dict = {}
    for student_id, pct in qs.values_list("student_id", "percentage"):
        info = roster_by_user_id.get(str(student_id), {})
        dept = info.get("department") or "Unknown"
        dept_percentages.setdefault(dept, []).append(pct)
    return [
        {"department": dept, "student_count": len(pcts), "average_percentage": round(sum(pcts) / len(pcts), 2)}
        for dept, pcts in sorted(dept_percentages.items())
    ]


def _malpractice_rate(qs):
    total = qs.count()
    flagged = qs.filter(malpractice_flag=True).count()
    return {
        "flagged_count": flagged,
        "total_count": total,
        "rate_percentage": round(flagged / total * 100, 2) if total else 0.0,
    }


def _compute_analytics(assignment, request):
    """Raises RuntimeError (from the roster fetch) — callers convert to a
    502, matching Task 7.1's pattern for the same failure mode."""
    qs = ResultSummary.objects.filter(
        assignment=assignment, institution_id=assignment.institution_id,
    ).annotate(percentage=_PERCENTAGE_ANNOTATION)

    roster_by_user_id = _fetch_roster_lookup(assignment, request)

    return {
        "assignment_id": str(assignment.id),
        "total_completed": qs.count(),
        "score_distribution": _score_distribution(qs),
        "pass_fail": _pass_fail(qs, assignment.pass_cutoff_percentage),
        "question_difficulty": _question_difficulty(assignment),
        "department_comparison": _department_comparison(qs, roster_by_user_id),
        "malpractice_rate": _malpractice_rate(qs),
        "metric_definitions": _METRIC_DEFINITIONS,
    }


class AdminAssignmentAnalyticsView(APIView):
    """GET /api/assessments/admin/assignments/<id>/analytics/ (Task 8.1) —
    Redis-cached (60s TTL) since every figure here is an aggregate over
    potentially thousands of ResultSummary rows; repeated admin page views
    during a live exam must not recompute on every request (closes AT11)."""
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(BatchAssignment, pk=pk, institution_id=institution_id)

        # Task 13.1: safe_cache_get/set degrade to a cache-miss/no-op
        # instead of raising if Redis is unavailable — a Redis outage must
        # make this view slower (direct computation every time), not break
        # it outright.
        cache_key = f"assessment_analytics:{assignment.id}"
        cached = safe_cache_get(cache_key)
        if cached is not None:
            return success_response(data=cached)

        try:
            data = _compute_analytics(assignment, request)
        except RuntimeError as exc:
            return error_response(f"Could not load student roster: {exc}", status_code=502)

        safe_cache_set(cache_key, data, ANALYTICS_CACHE_TTL_SECONDS)
        return success_response(data=data)


class AdminAssignmentAnalyticsExportView(APIView):
    """GET /api/assessments/admin/assignments/<id>/analytics/export/ (Task
    8.1) — a structured, multi-section CSV (not one flat table, unlike Task
    7.3's per-student export — this data is inherently several small
    aggregates, not one row-per-record dataset). Bounded in size regardless
    of student count, so a plain (non-streaming) response is appropriate
    here, unlike Task 7.3's per-row results export."""
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(BatchAssignment, pk=pk, institution_id=institution_id)

        try:
            data = _compute_analytics(assignment, request)
        except RuntimeError as exc:
            return error_response(f"Could not load student roster: {exc}", status_code=502)

        output = io.StringIO()
        output.write("﻿")
        writer = csv.writer(output)

        writer.writerow(["Score Distribution"])
        writer.writerow(["Bucket", "Count"])
        for row in data["score_distribution"]:
            writer.writerow([row["bucket"], row["count"]])
        writer.writerow([])

        writer.writerow(["Pass / Fail Summary"])
        pf = data["pass_fail"]
        writer.writerow(["Cutoff %", pf["cutoff_percentage"]])
        writer.writerow(["Pass Count", pf["pass_count"]])
        writer.writerow(["Fail Count", pf["fail_count"]])
        writer.writerow(["Pass Rate %", pf["pass_rate_percentage"]])
        writer.writerow([])

        writer.writerow(["Per-Question Difficulty"])
        writer.writerow(["Set", "Question #", "Total Answered", "Correct", "% Correct"])
        for q in data["question_difficulty"]:
            writer.writerow([q["set_label"], q["question_number"], q["total_answered"], q["correct_count"], q["percentage_correct"]])
        writer.writerow([])

        writer.writerow(["Department Comparison"])
        writer.writerow(["Department", "Student Count", "Average %"])
        for d in data["department_comparison"]:
            writer.writerow([d["department"], d["student_count"], d["average_percentage"]])
        writer.writerow([])

        writer.writerow(["Malpractice Rate"])
        mp = data["malpractice_rate"]
        writer.writerow(["Flagged", mp["flagged_count"]])
        writer.writerow(["Total", mp["total_count"]])
        writer.writerow(["Rate %", mp["rate_percentage"]])

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="analytics_{assignment.id}.csv"'
        return response


# ── Admin: Dashboard (Task 9.1) ─────────────────────────────────────────────
#
# Unlike Task 8.1's analytics cache (pure 60s TTL, a stale window is an
# accepted tradeoff for that view), the dashboard is meant to be watched
# live during an in-progress exam (Task 9.2's UI polls it), so its cache is
# explicitly invalidated the moment new results exist — see
# scoring.finalize_sessions()'s `cache.delete(f"assessment_dashboard:...")`
# call, which fires for every assignment that gained a ResultSummary row in
# that finalize pass (the sweep, an admin close/, or a manual submit all go
# through that one function). DASHBOARD_CACHE_TTL_SECONDS below is only a
# defensive backstop in case an invalidation is ever missed (e.g. a future
# code path that writes ResultSummary directly) — the real freshness
# guarantee is the explicit delete, not this TTL.
DASHBOARD_CACHE_TTL_SECONDS = 300

_DASHBOARD_METRIC_DEFINITIONS = {
    "completion_rate_percentage": "student_count_completed / student_count_total * 100, where completed = a ResultSummary row exists (SUBMITTED or AUTO_SUBMITTED).",
    "average_score_percentage": "Mean of score/total_marks (not raw score) across all completed sessions — percentage-normalized so students on different sets remain comparable, same convention as Task 8.1's analytics.",
    "malpractice_incidents": "Count of completed sessions with malpractice_flag=True (Task 6.2's threshold rule).",
    "submission_breakdown": "Of completed sessions: on_time = finalized via manual submit (SUBMITTED), auto_submitted = finalized by the beat sweep or an admin close/ hitting the deadline (AUTO_SUBMITTED).",
}


def _compute_dashboard(assignment):
    total = assignment.allocations.count()
    completed_qs = ResultSummary.objects.filter(
        assignment=assignment, institution_id=assignment.institution_id,
    )
    completed = completed_qs.count()
    in_progress = assignment.sessions.filter(status=SESSION_STATUS_IN_PROGRESS).count()

    avg_percentage = completed_qs.annotate(percentage=_PERCENTAGE_ANNOTATION).aggregate(
        avg=Avg("percentage"),
    )["avg"]

    on_time = completed_qs.filter(status=SESSION_STATUS_SUBMITTED).count()
    auto_submitted = completed_qs.filter(status=SESSION_STATUS_AUTO_SUBMITTED).count()

    return {
        "assignment_id": str(assignment.id),
        "status": assignment.status,
        "student_count_total": total,
        "student_count_completed": completed,
        "student_count_in_progress": in_progress,
        "completion_rate_percentage": round(completed / total * 100, 2) if total else 0.0,
        "average_score_percentage": round(avg_percentage, 2) if avg_percentage is not None else 0.0,
        "malpractice_incidents": completed_qs.filter(malpractice_flag=True).count(),
        "submission_breakdown": {
            "on_time": on_time,
            "auto_submitted": auto_submitted,
            "on_time_percentage": round(on_time / completed * 100, 2) if completed else 0.0,
        },
        "metric_definitions": _DASHBOARD_METRIC_DEFINITIONS,
    }


class AdminAssignmentDashboardView(APIView):
    """GET /api/assessments/admin/assignments/<id>/dashboard/ (Task 9.1) —
    top-line KPI rollup meant to be watched live during an in-progress exam.
    Redis-cached with explicit invalidation on every new submission (see the
    module comment above), not the pure-TTL pattern Task 8.1's analytics
    cache uses — a dashboard being watched live can't tolerate a up-to-60s
    stale window the way a post-hoc analytics deep-dive can."""
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(BatchAssignment, pk=pk, institution_id=institution_id)

        cache_key = f"assessment_dashboard:{assignment.id}"
        cached = safe_cache_get(cache_key)
        if cached is not None:
            return success_response(data=cached)

        data = _compute_dashboard(assignment)
        safe_cache_set(cache_key, data, DASHBOARD_CACHE_TTL_SECONDS)
        return success_response(data=data)


class AdminAssignmentDashboardExportView(APIView):
    """GET /api/assessments/admin/assignments/<id>/dashboard/export/ (Task
    9.1).

    Export format decision (documented per the task's explicit
    "evaluate server-side vs client-side, document the choice"
    requirement): this endpoint exports the underlying KPI data as CSV —
    small, bounded, always available headlessly (curl, CI, a scheduled
    report) with zero new dependencies on either side. A rendered
    image/PDF snapshot of the dashboard-as-displayed is produced
    client-side instead, via the browser's native window.print() with
    print-specific CSS on Task 9.2's dashboard page — this needed no new
    server-side PDF-rendering package (e.g. WeasyPrint) and no new
    frontend package (e.g. jsPDF/html2canvas), consistent with the
    project's standing "no new npm/pip packages" constraint, and it
    captures the same CSS-div/SVG charts the admin is actually looking
    at rather than a separately-maintained server-side re-render of them.
    """
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        assignment = get_object_or_404(BatchAssignment, pk=pk, institution_id=institution_id)

        data = _compute_dashboard(assignment)

        output = io.StringIO()
        output.write("﻿")
        writer = csv.writer(output)

        writer.writerow(["Assessment Dashboard"])
        writer.writerow(["Assignment ID", data["assignment_id"]])
        writer.writerow(["Status", data["status"]])
        writer.writerow([])

        writer.writerow(["Metric", "Value"])
        writer.writerow(["Students Total", data["student_count_total"]])
        writer.writerow(["Students Completed", data["student_count_completed"]])
        writer.writerow(["Students In Progress", data["student_count_in_progress"]])
        writer.writerow(["Completion Rate %", data["completion_rate_percentage"]])
        writer.writerow(["Average Score %", data["average_score_percentage"]])
        writer.writerow(["Malpractice Incidents", data["malpractice_incidents"]])
        writer.writerow([])

        writer.writerow(["Submission Breakdown"])
        sb = data["submission_breakdown"]
        writer.writerow(["On Time (manual submit)", sb["on_time"]])
        writer.writerow(["Auto-Submitted (deadline)", sb["auto_submitted"]])
        writer.writerow(["On Time %", sb["on_time_percentage"]])

        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="dashboard_{assignment.id}.csv"'
        return response
