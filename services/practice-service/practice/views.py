import logging
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.generics import get_object_or_404

from core.permissions import IsAdminUser, IsStudentUser
from core.responses import success_response, error_response
from core.pagination import StandardResultsPagination
from core.storage import (
    build_file_key, generate_presigned_upload_url, get_cdn_url,
    verify_uploaded_image, delete_file, scan_image_for_malware,
    TransientStorageError,
)
from core.upload_constraints import ALLOWED_IMAGE_EXTENSIONS, MAX_BYTES_PER_SECTION
from .validators import get_publish_blockers

from .models import (
    PracticeModule, PracticeSection, PracticeQuestion, PracticeQuestionOption,
    PracticeQuestionAttempt, PracticeQuestionProgress,
    PROGRESS_RANK,
    PROGRESS_VISITED, PROGRESS_ATTEMPTED, PROGRESS_COMPLETED,
)
from .serializers import (
    PracticeModuleSerializer,
    PracticeSectionSerializer,
    PracticeQuestionSerializer,
    StudentPracticeQuestionSerializer,
    PracticeQuestionOptionAdminSerializer,
    PracticeQuestionOptionStudentSerializer,
)

logger = logging.getLogger(__name__)

_SECTION_CACHE_TTL = 600  # 10 minutes


def _section_cache_key(institution_id, section_id):
    return f"practice:institution:{institution_id}:section:{section_id}:questions"


def _invalidate_section_cache(institution_id, section_id):
    cache.delete(_section_cache_key(institution_id, section_id))


class _PublishBlocked(Exception):
    """Raised inside a transaction to force a rollback when a mutation
    would leave a published question failing its publish requirements —
    caught by the calling view to return a 400 with the specific reasons."""
    def __init__(self, blockers):
        self.blockers = blockers
        super().__init__("Publish requirements not met")


def _raise_if_publish_blocked(question):
    """
    Call from inside a `transaction.atomic()` block, after mutating one of
    a question's options (create/update/delete). Raising here — rather than
    just returning an error — is what actually triggers the rollback;
    returning a Response from inside `atomic()` would still commit the
    already-applied DB write. The caller catches `_PublishBlocked` outside
    the `with` block to turn it into a 400 response.
    """
    if not question.is_published:
        return
    blockers = get_publish_blockers(question)
    if blockers:
        raise _PublishBlocked(blockers)


def _publish_blocked_response(exc, editing_published=False):
    """
    Build the 400 response for a `_PublishBlocked` exception. The specific
    reasons are folded into the top-level `message` (not just the nested
    `errors.publish` list) — the frontend's error helper reads `message`
    first, so without this the admin would only ever see a generic
    "requirements not met" toast instead of which fields to fix.
    """
    prefix = (
        "Cannot save — this question is published and this change would leave it invalid: "
        if editing_published else
        "Cannot publish: "
    )
    return error_response(
        prefix + " ".join(exc.blockers),
        errors={"publish": exc.blockers},
        status_code=400,
    )


def _get_institution_id(request):
    return getattr(request.user, "institution_id", None)


def _get_student_id(request):
    """Return the JWT user_id, used as student identifier in progress/attempt records."""
    return request.user.id


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
            "service": "practice-service",
            "db": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
        })


# ── Admin: Root hub ────────────────────────────────────────────────────────────

class AdminPracticeRootView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        institution_id = _get_institution_id(request)
        modules = PracticeModule.objects.filter(
            parent__isnull=True, institution_id=institution_id
        ).order_by("order", "created_at")
        sections = PracticeSection.objects.filter(
            module__isnull=True, institution_id=institution_id
        ).annotate(question_count=Count("questions")).order_by("order", "created_at")
        return success_response(data={
            "modules":  PracticeModuleSerializer(modules, many=True).data,
            "sections": PracticeSectionSerializer(sections, many=True).data,
        })


# ── Admin: Modules ─────────────────────────────────────────────────────────────

class AdminPracticeModuleListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        institution_id = _get_institution_id(request)
        data = {**request.data, "parent": None}
        s = PracticeModuleSerializer(data=data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save(institution_id=institution_id)
        return success_response(data=s.data, status_code=201, message="Module created")


class AdminPracticeModuleDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk, institution_id):
        return get_object_or_404(PracticeModule, pk=pk, institution_id=institution_id)

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        module   = self._get(pk, institution_id)
        children = module.children.filter(
            institution_id=institution_id
        ).order_by("order", "created_at")
        sections = module.sections.annotate(
            question_count=Count("questions")
        ).order_by("order", "created_at")
        return success_response(data={
            "module":   PracticeModuleSerializer(module).data,
            "children": PracticeModuleSerializer(children, many=True).data,
            "sections": PracticeSectionSerializer(sections, many=True).data,
        })

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        module = self._get(pk, institution_id)
        s = PracticeModuleSerializer(module, data=request.data, partial=True)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save()
        return success_response(data=s.data, message="Module updated")

    def delete(self, request, pk):
        institution_id = _get_institution_id(request)
        module = self._get(pk, institution_id)
        if module.children.exists() or module.sections.exists():
            return error_response(
                "Cannot delete a module that has sub-modules or sections. Remove them first.",
                status_code=400,
            )
        module.delete()
        return success_response(message="Module deleted")


class AdminPracticeModuleChildrenView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        parent = get_object_or_404(PracticeModule, pk=pk, institution_id=institution_id)
        data   = {**request.data, "parent": str(parent.id)}
        s = PracticeModuleSerializer(data=data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save(institution_id=institution_id)
        return success_response(data=s.data, status_code=201, message="Child module created")


class AdminPracticeModuleSectionsView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        module = get_object_or_404(PracticeModule, pk=pk, institution_id=institution_id)
        data   = {**request.data, "module": str(module.id)}
        s = PracticeSectionSerializer(data=data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save(institution_id=institution_id)
        return success_response(data=s.data, status_code=201, message="Section created")


# ── Admin: Sections ────────────────────────────────────────────────────────────

class AdminPracticeSectionListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        institution_id = _get_institution_id(request)
        data = {**request.data, "module": None}
        s = PracticeSectionSerializer(data=data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save(institution_id=institution_id)
        return success_response(data=s.data, status_code=201, message="Section created")


class AdminPracticeSectionDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk, institution_id):
        return get_object_or_404(
            PracticeSection.objects.select_related("module"),
            pk=pk, institution_id=institution_id,
        )

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        section   = self._get(pk, institution_id)
        questions = section.questions.order_by("order", "created_at")
        return success_response(data={
            "section":   PracticeSectionSerializer(section).data,
            "module":    PracticeModuleSerializer(section.module).data if section.module else None,
            "questions": PracticeQuestionSerializer(questions, many=True).data,
        })

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        section = self._get(pk, institution_id)
        s = PracticeSectionSerializer(section, data=request.data, partial=True)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save()
        _invalidate_section_cache(institution_id, pk)
        return success_response(data=s.data, message="Section updated")

    def delete(self, request, pk):
        institution_id = _get_institution_id(request)
        section = self._get(pk, institution_id)
        if section.questions.exists():
            return error_response(
                "Cannot delete a section that has questions. Remove them first.",
                status_code=400,
            )
        section.delete()
        _invalidate_section_cache(institution_id, pk)
        return success_response(message="Section deleted")


# ── Admin: Questions ───────────────────────────────────────────────────────────

class AdminPracticeQuestionListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, section_id):
        institution_id = _get_institution_id(request)
        section = get_object_or_404(PracticeSection, pk=section_id, institution_id=institution_id)
        data = {
            "section":       str(section.id),
            "question_type": request.data.get("question_type", "mcq"),
            "title":         request.data.get("title", ""),
        }
        s = PracticeQuestionSerializer(data=data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)
        s.save()
        _invalidate_section_cache(institution_id, str(section.id))
        return success_response(data=s.data, status_code=201, message="Question created")


class AdminPracticeQuestionDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk, institution_id):
        return get_object_or_404(
            PracticeQuestion.objects.select_related("section"),
            pk=pk,
            section__institution_id=institution_id,
        )

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        question = self._get(pk, institution_id)
        section  = question.section
        options  = []
        if question.question_type == "mcq":
            opts    = question.options.order_by("order", "created_at")
            options = PracticeQuestionOptionAdminSerializer(opts, many=True).data
        return success_response(data={
            "question": PracticeQuestionSerializer(question).data,
            "section":  PracticeSectionSerializer(section).data,
            "module":   PracticeModuleSerializer(section.module).data if section.module else None,
            "options":  options,
        })

    def patch(self, request, pk):
        institution_id = _get_institution_id(request)
        question = self._get(pk, institution_id)
        was_published_before = question.is_published

        # Ground-truth check any new image key against what's actually in
        # storage (real size + magic bytes) before it's ever attached to a
        # question — never trust the client-supplied key or content_type.
        # This service has no separate confirm-upload step (unlike
        # resource-service), so the question PATCH is the commit point.
        # Then: malware scan, then the per-section storage quota — in that
        # order, since there's no point scanning or counting an object that
        # already failed a cheaper check.
        image_fields = {
            "question_image_key": "question_image_size_bytes",
            "explanation_image_key": "explanation_image_size_bytes",
        }
        new_sizes = {}
        for field, size_field in image_fields.items():
            new_key = request.data.get(field)
            if not new_key or new_key == getattr(question, field):
                continue

            try:
                real_size, error = verify_uploaded_image(new_key)
            except RuntimeError as exc:
                logger.error("Storage not configured for image verification: %s", exc)
                return error_response("File storage is not configured.", status_code=503)
            except TransientStorageError as exc:
                # Verification itself failed (storage unreachable) — the
                # object was never examined, so it's left in place and the
                # admin can just retry the same save once storage recovers.
                return error_response(str(exc), status_code=503)
            if error:
                try:
                    delete_file(new_key)
                except Exception:
                    logger.warning("Failed to clean up rejected image key=%s", new_key)
                return error_response(error, status_code=400)

            try:
                scan_error = scan_image_for_malware(new_key)
            except RuntimeError as exc:
                logger.error("Malware scanning not configured: %s", exc)
                return error_response("Malware scanning is not configured.", status_code=503)
            except TransientStorageError as exc:
                # Scanner unreachable — the image was never actually cleared
                # or rejected, so it must NOT be deleted (that would destroy
                # a good upload and force a needless re-upload on retry).
                return error_response(str(exc), status_code=503)
            if scan_error:
                try:
                    delete_file(new_key)
                except Exception:
                    logger.warning("Failed to clean up infected image key=%s", new_key)
                return error_response(scan_error, status_code=400)

            new_sizes[field] = (size_field, real_size)

        if new_sizes:
            from django.db.models import Sum
            existing_total = PracticeQuestion.objects.filter(
                section_id=question.section_id
            ).aggregate(
                q=Sum("question_image_size_bytes"), e=Sum("explanation_image_size_bytes"),
            )
            existing_total_bytes = (existing_total["q"] or 0) + (existing_total["e"] or 0)
            # Subtract this question's own current image sizes — they're
            # being replaced, not added on top of themselves.
            existing_total_bytes -= (question.question_image_size_bytes or 0)
            existing_total_bytes -= (question.explanation_image_size_bytes or 0)
            new_total_bytes = existing_total_bytes + sum(size for _, size in new_sizes.values())

            if new_total_bytes > MAX_BYTES_PER_SECTION:
                for field, _ in new_sizes.items():
                    try:
                        delete_file(request.data[field])
                    except Exception:
                        logger.warning("Failed to clean up over-quota image key=%s", request.data[field])
                return error_response(
                    "This section has reached its image storage limit. "
                    "Remove some images before adding more.",
                    status_code=400,
                )

        old_image_keys = {field: getattr(question, field) for field in image_fields}

        # question_image_size_bytes / explanation_image_size_bytes are
        # read_only on the serializer — never client-writable, or a client
        # could report a fake (small) size to dodge the quota check above.
        # Set them directly from verify_uploaded_image's real HEAD result.
        s = PracticeQuestionSerializer(question, data=request.data, partial=True)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)

        # A published question must always satisfy the publish requirements
        # (question content, options + a correct answer / fib answer,
        # explanation) — not just at the moment it's first published. If
        # this PATCH would leave it published but invalid (whether by
        # setting is_published=True directly, or by editing content on an
        # already-published question down to an invalid state), the whole
        # PATCH is rejected atomically — nothing about it is saved.
        try:
            with transaction.atomic():
                question = s.save()
                size_changed = False
                for field, (size_field, real_size) in new_sizes.items():
                    setattr(question, size_field, real_size)
                    size_changed = True
                for field in image_fields:
                    if field in request.data and not request.data.get(field):
                        setattr(question, image_fields[field], None)
                        size_changed = True
                if size_changed:
                    question.save(update_fields=list(image_fields.values()))

                if question.is_published:
                    blockers = get_publish_blockers(question)
                    if blockers:
                        raise _PublishBlocked(blockers)
        except _PublishBlocked as exc:
            # Any newly-uploaded (verified, scanned) image in this same
            # request is now orphaned since the DB write rolled back —
            # clean it up rather than leaking storage.
            for field in new_sizes:
                try:
                    delete_file(request.data[field])
                except Exception:
                    logger.warning("Failed to clean up orphaned image key=%s", request.data[field])
            return _publish_blocked_response(exc, editing_published=was_published_before)

        _invalidate_section_cache(institution_id, str(question.section_id))

        # Best-effort cleanup of a replaced/removed image object — no
        # celery worker in this service, so this runs synchronously.
        for field, old_key in old_image_keys.items():
            new_key = getattr(question, field)
            if old_key and old_key != new_key:
                try:
                    delete_file(old_key)
                except Exception:
                    logger.warning("Failed to delete replaced image key=%s", old_key)

        return success_response(data=s.data, message="Question updated")

    def delete(self, request, pk):
        institution_id = _get_institution_id(request)
        question = self._get(pk, institution_id)
        section_id = str(question.section_id)
        question.delete()
        _invalidate_section_cache(institution_id, section_id)
        return success_response(message="Question deleted")


# ── Admin: MCQ Options ─────────────────────────────────────────────────────────

_OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class AdminPracticeQuestionOptionListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        question = get_object_or_404(
            PracticeQuestion, pk=pk, section__institution_id=institution_id
        )
        options  = question.options.order_by("order", "created_at")
        return success_response(data=PracticeQuestionOptionAdminSerializer(options, many=True).data)

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        question = get_object_or_404(
            PracticeQuestion, pk=pk, section__institution_id=institution_id
        )
        data = dict(request.data)
        data["question"] = str(question.id)
        if not data.get("label"):
            count = question.options.count()
            data["label"] = (
                _OPTION_LABELS[count] if count < len(_OPTION_LABELS)
                else str(count + 1)
            )
        if not data.get("order"):
            max_order = question.options.aggregate(m=Max("order"))["m"] or 0
            data["order"] = max_order + 1

        s = PracticeQuestionOptionAdminSerializer(data=data)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)

        try:
            with transaction.atomic():
                if s.validated_data.get("is_correct") and question.mcq_type == "single":
                    question.options.filter(is_correct=True).update(is_correct=False)
                s.save()
                _raise_if_publish_blocked(question)
        except _PublishBlocked as exc:
            return _publish_blocked_response(exc, editing_published=True)

        _invalidate_section_cache(institution_id, str(question.section_id))
        return success_response(data=s.data, status_code=201, message="Option created")


class AdminPracticeQuestionOptionDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk, option_pk, institution_id):
        return get_object_or_404(
            PracticeQuestionOption,
            pk=option_pk,
            question__id=pk,
            question__section__institution_id=institution_id,
        )

    def patch(self, request, pk, option_pk):
        institution_id = _get_institution_id(request)
        option   = self._get(pk, option_pk, institution_id)
        question = option.question

        s = PracticeQuestionOptionAdminSerializer(option, data=request.data, partial=True)
        if not s.is_valid():
            return error_response("Validation failed", errors=s.errors, status_code=400)

        try:
            with transaction.atomic():
                if s.validated_data.get("is_correct") and question.mcq_type == "single":
                    question.options.exclude(pk=option_pk).filter(is_correct=True).update(is_correct=False)
                s.save()
                _raise_if_publish_blocked(question)
        except _PublishBlocked as exc:
            return _publish_blocked_response(exc, editing_published=True)

        _invalidate_section_cache(institution_id, str(question.section_id))
        return success_response(data=s.data, message="Option updated")

    def delete(self, request, pk, option_pk):
        institution_id = _get_institution_id(request)
        option = self._get(pk, option_pk, institution_id)
        question = option.question
        section_id = str(question.section_id)

        try:
            with transaction.atomic():
                option.delete()
                _raise_if_publish_blocked(question)
        except _PublishBlocked as exc:
            return _publish_blocked_response(exc, editing_published=True)

        _invalidate_section_cache(institution_id, section_id)
        return success_response(message="Option deleted")


# ── Admin: Image presign ───────────────────────────────────────────────────────

_ALLOWED_IMAGE_MIME = (
    "image/jpeg", "image/png", "image/webp",
    "image/gif", "image/avif",
)


def _validate_image_presign_request(filename: str, content_type: str):
    """Returns an error message, or None if the request passes. Extension
    and MIME are both attacker-controlled at this stage — this is a fast
    client-facing rejection; the real check happens in verify_uploaded_image
    once the object actually lands in storage."""
    import os
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return f"Extension '{ext}' not allowed. Allowed: {ALLOWED_IMAGE_EXTENSIONS}"
    if not any(content_type.startswith(p) for p in _ALLOWED_IMAGE_MIME):
        return "Unsupported image format. Allowed: JPEG, PNG, WebP, GIF, AVIF."
    return None


class AdminPracticeQuestionBodyImagePresignView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        get_object_or_404(PracticeQuestion, pk=pk, section__institution_id=institution_id)
        filename     = request.data.get("filename", "image.jpg") or "image.jpg"
        content_type = request.data.get("content_type", "image/jpeg") or "image/jpeg"

        error = _validate_image_presign_request(filename, content_type)
        if error:
            return error_response(error, status_code=400)

        file_key = build_file_key("image", filename)
        try:
            upload_url = generate_presigned_upload_url(file_key, content_type)
        except RuntimeError as exc:
            logger.error("R2 not configured: %s", exc)
            return error_response("File storage is not configured.", status_code=503)
        cdn_url = get_cdn_url(file_key)
        return success_response(data={"upload_url": upload_url, "file_key": file_key, "cdn_url": cdn_url})


class AdminPracticeQuestionExplanationImagePresignView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        get_object_or_404(PracticeQuestion, pk=pk, section__institution_id=institution_id)
        filename     = request.data.get("filename", "image.jpg") or "image.jpg"
        content_type = request.data.get("content_type", "image/jpeg") or "image/jpeg"

        error = _validate_image_presign_request(filename, content_type)
        if error:
            return error_response(error, status_code=400)

        file_key = build_file_key("image", filename)
        try:
            upload_url = generate_presigned_upload_url(file_key, content_type)
        except RuntimeError as exc:
            logger.error("R2 not configured: %s", exc)
            return error_response("File storage is not configured.", status_code=503)
        cdn_url = get_cdn_url(file_key)
        return success_response(data={"upload_url": upload_url, "file_key": file_key, "cdn_url": cdn_url})


# ── Student: Root hub ──────────────────────────────────────────────────────────

class StudentPracticeRootView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request):
        institution_id = _get_institution_id(request)
        modules = PracticeModule.objects.filter(
            parent__isnull=True, is_published=True, institution_id=institution_id
        ).order_by("order", "created_at")
        sections = PracticeSection.objects.filter(
            module__isnull=True, is_published=True, institution_id=institution_id
        ).annotate(
            question_count=Count("questions", filter=Q(questions__is_published=True))
        ).order_by("order", "created_at")
        return success_response(data={
            "modules":  PracticeModuleSerializer(modules, many=True).data,
            "sections": PracticeSectionSerializer(sections, many=True).data,
        })


class StudentPracticeModuleView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        module = get_object_or_404(PracticeModule, pk=pk, is_published=True, institution_id=institution_id)
        children = module.children.filter(
            is_published=True, institution_id=institution_id
        ).order_by("order", "created_at")
        sections = module.sections.filter(is_published=True).annotate(
            question_count=Count("questions", filter=Q(questions__is_published=True))
        ).order_by("order", "created_at")
        return success_response(data={
            "module":   PracticeModuleSerializer(module).data,
            "children": PracticeModuleSerializer(children, many=True).data,
            "sections": PracticeSectionSerializer(sections, many=True).data,
        })


class StudentPracticeSectionView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        student_id     = _get_student_id(request)
        section = get_object_or_404(PracticeSection, pk=pk, is_published=True, institution_id=institution_id)

        # Try cache first
        cache_key = _section_cache_key(institution_id, str(pk))
        cached    = cache.get(cache_key)
        if cached is not None:
            questions_data = cached
        else:
            questions_qs = section.questions.filter(is_published=True).order_by("order", "created_at")
            questions_data = []
            for q in questions_qs:
                d = StudentPracticeQuestionSerializer(q).data
                questions_data.append(d)
            cache.set(cache_key, questions_data, _SECTION_CACHE_TTL)

        # Augment with per-student progress (never cached — per-user data)
        question_ids = [q["id"] for q in questions_data]
        progress_map = {
            str(p.question_id): p.status
            for p in PracticeQuestionProgress.objects.filter(
                student_id=student_id,
                question_id__in=question_ids,
            )
        }
        augmented = []
        for q in questions_data:
            entry = dict(q)
            entry["progress_status"] = progress_map.get(str(q["id"]), "not_visited")
            augmented.append(entry)

        return success_response(data={
            "section":   PracticeSectionSerializer(section).data,
            "module":    PracticeModuleSerializer(section.module).data if section.module else None,
            "questions": augmented,
        })


class StudentPracticeQuestionView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request, pk):
        institution_id = _get_institution_id(request)
        student_id     = _get_student_id(request)
        question = get_object_or_404(
            PracticeQuestion.objects.select_related("section__module"),
            pk=pk,
            is_published=True,
            section__is_published=True,
            section__institution_id=institution_id,
        )
        section = question.section

        sibling_ids = list(
            section.questions
            .filter(is_published=True)
            .order_by("order", "created_at")
            .values_list("id", flat=True)
        )
        try:
            idx = sibling_ids.index(question.id)
        except ValueError:
            idx = -1

        prev_question_id = str(sibling_ids[idx - 1]) if idx > 0 else None
        next_question_id = str(sibling_ids[idx + 1]) if 0 <= idx < len(sibling_ids) - 1 else None

        progress = PracticeQuestionProgress.objects.filter(
            student_id=student_id, question=question
        ).first()
        progress_status = progress.status if progress else "not_visited"

        question_data = StudentPracticeQuestionSerializer(question).data
        question_data["progress_status"] = progress_status

        options = []
        if question.question_type == "mcq":
            opts    = question.options.order_by("order", "created_at")
            options = PracticeQuestionOptionStudentSerializer(opts, many=True).data

        attempt_info = None
        if progress_status in (PROGRESS_ATTEMPTED, PROGRESS_COMPLETED):
            attempts = PracticeQuestionAttempt.objects.filter(
                student_id=student_id, question=question
            ).order_by("attempt_number")

            attempt_count   = attempts.count()
            last_attempt    = attempts.last()
            last_is_correct = last_attempt.is_correct if last_attempt else False

            correct_option_ids = [
                str(o.id)
                for o in question.options.filter(is_correct=True)
            ] if question.question_type == "mcq" else []

            attempt_info = {
                "attempt_count":    attempt_count,
                "last_is_correct":  last_is_correct,
                "correct_option_ids": correct_option_ids,
            }

        return success_response(data={
            "question":          question_data,
            "section":           PracticeSectionSerializer(section).data,
            "module":            PracticeModuleSerializer(section.module).data if section.module else None,
            "options":           list(options),
            "prev_question_id":  prev_question_id,
            "next_question_id":  next_question_id,
            "attempt_info":      attempt_info,
        })


# ── Student: Progress ──────────────────────────────────────────────────────────

class StudentPracticeQuestionProgressView(APIView):
    permission_classes = [IsStudentUser]

    VALID_STATUSES = (PROGRESS_VISITED, PROGRESS_ATTEMPTED, PROGRESS_COMPLETED)

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        student_id     = _get_student_id(request)
        question = get_object_or_404(
            PracticeQuestion,
            pk=pk,
            is_published=True,
            section__is_published=True,
            section__institution_id=institution_id,
        )

        new_status = request.data.get("status")
        if new_status not in self.VALID_STATUSES:
            return error_response(
                "Invalid status. Must be 'visited', 'attempted', or 'completed'.",
                status_code=400,
            )

        now = timezone.now()
        progress, created = PracticeQuestionProgress.objects.get_or_create(
            student_id=student_id,
            question=question,
            defaults={
                "institution_id":     institution_id,
                "status":             new_status,
                "first_visited_at":   now,
                "first_attempted_at": now if new_status in (PROGRESS_ATTEMPTED, PROGRESS_COMPLETED) else None,
                "first_completed_at": now if new_status == PROGRESS_COMPLETED else None,
            },
        )

        if not created:
            if PROGRESS_RANK.get(new_status, 0) > PROGRESS_RANK.get(progress.status, 0):
                update_fields = ["status", "updated_at"]
                progress.status = new_status
                if not progress.first_visited_at:
                    progress.first_visited_at = now
                    update_fields.append("first_visited_at")
                if new_status in (PROGRESS_ATTEMPTED, PROGRESS_COMPLETED) and not progress.first_attempted_at:
                    progress.first_attempted_at = now
                    update_fields.append("first_attempted_at")
                if new_status == PROGRESS_COMPLETED and not progress.first_completed_at:
                    progress.first_completed_at = now
                    update_fields.append("first_completed_at")
                progress.save(update_fields=update_fields)

        return success_response(data={
            "question_id":        str(question.id),
            "status":             progress.status,
            "first_visited_at":   progress.first_visited_at,
            "first_attempted_at": progress.first_attempted_at,
            "first_completed_at": progress.first_completed_at,
        })


# ── Student: Reveal answer ─────────────────────────────────────────────────────

class StudentPracticeQuestionRevealAnswerView(APIView):
    permission_classes = [IsStudentUser]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        student_id     = _get_student_id(request)
        question = get_object_or_404(
            PracticeQuestion,
            pk=pk,
            is_published=True,
            section__is_published=True,
            section__institution_id=institution_id,
        )

        if question.question_type == "mcq":
            correct_option_ids = [
                str(o.id) for o in question.options.filter(is_correct=True)
            ]
            return success_response(data={"correct_option_ids": correct_option_ids})

        # FIB: reveal + advance progress to completed
        now = timezone.now()
        progress, created = PracticeQuestionProgress.objects.get_or_create(
            student_id=student_id,
            question=question,
            defaults={
                "institution_id":     institution_id,
                "status":             PROGRESS_COMPLETED,
                "first_visited_at":   now,
                "first_attempted_at": now,
                "first_completed_at": now,
            },
        )
        if not created and PROGRESS_RANK.get(PROGRESS_COMPLETED, 0) > PROGRESS_RANK.get(progress.status, 0):
            update_fields = ["status", "updated_at"]
            progress.status = PROGRESS_COMPLETED
            if not progress.first_visited_at:
                progress.first_visited_at = now
                update_fields.append("first_visited_at")
            if not progress.first_attempted_at:
                progress.first_attempted_at = now
                update_fields.append("first_attempted_at")
            if not progress.first_completed_at:
                progress.first_completed_at = now
                update_fields.append("first_completed_at")
            progress.save(update_fields=update_fields)

        return success_response(data={"fib_answer": question.fib_answer})


# ── Student: Submit MCQ ────────────────────────────────────────────────────────

class StudentPracticeQuestionSubmitView(APIView):
    permission_classes = [IsStudentUser]

    def post(self, request, pk):
        institution_id = _get_institution_id(request)
        student_id     = _get_student_id(request)
        question = get_object_or_404(
            PracticeQuestion,
            pk=pk,
            is_published=True,
            section__is_published=True,
            section__institution_id=institution_id,
        )

        if question.question_type != "mcq":
            return error_response("Submit is only valid for MCQ questions.", status_code=400)

        selected_ids = request.data.get("selected_option_ids", [])
        if not isinstance(selected_ids, list) or not selected_ids:
            return error_response("selected_option_ids must be a non-empty list.", status_code=400)

        valid_options = {
            str(o.id): o
            for o in question.options.filter(id__in=selected_ids)
        }
        if len(valid_options) != len(set(str(i) for i in selected_ids)):
            return error_response("One or more selected option IDs are invalid.", status_code=400)

        correct_ids  = {str(o.id) for o in question.options.filter(is_correct=True)}
        selected_set = {str(i) for i in selected_ids}
        is_correct   = selected_set == correct_ids

        max_attempt = PracticeQuestionAttempt.objects.filter(
            student_id=student_id, question=question
        ).aggregate(m=Max("attempt_number"))["m"] or 0
        attempt_number = max_attempt + 1

        PracticeQuestionAttempt.objects.create(
            student_id=student_id,
            institution_id=institution_id,
            question=question,
            selected_option_ids=list(selected_set),
            is_correct=is_correct,
            attempt_number=attempt_number,
        )

        now        = timezone.now()
        new_status = PROGRESS_COMPLETED if is_correct else PROGRESS_ATTEMPTED

        progress, created = PracticeQuestionProgress.objects.get_or_create(
            student_id=student_id,
            question=question,
            defaults={
                "institution_id":     institution_id,
                "status":             new_status,
                "first_visited_at":   now,
                "first_attempted_at": now,
                "first_completed_at": now if is_correct else None,
            },
        )

        if not created:
            if PROGRESS_RANK.get(new_status, 0) > PROGRESS_RANK.get(progress.status, 0):
                update_fields = ["status", "updated_at"]
                progress.status = new_status
                if not progress.first_visited_at:
                    progress.first_visited_at = now
                    update_fields.append("first_visited_at")
                if not progress.first_attempted_at:
                    progress.first_attempted_at = now
                    update_fields.append("first_attempted_at")
                if is_correct and not progress.first_completed_at:
                    progress.first_completed_at = now
                    update_fields.append("first_completed_at")
                progress.save(update_fields=update_fields)

        return success_response(data={
            "is_correct":         is_correct,
            "attempt_number":     attempt_number,
            "correct_option_ids": list(correct_ids),
        })
