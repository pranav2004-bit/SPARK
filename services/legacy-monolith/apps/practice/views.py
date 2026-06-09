from django.db.models import Max
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from core.permissions import IsAdminUser, IsStudentUser
from core.responses import success_response, error_response
from core.storage import build_file_key, generate_presigned_upload_url, get_cdn_url

from apps.students.models import Student

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
    PracticeQuestionOptionAdminSerializer,
    PracticeQuestionOptionStudentSerializer,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_student(request):
    """Return the Student for the authenticated request user."""
    return get_object_or_404(Student, user=request.user)


def _questions_with_progress(questions_qs, student):
    """
    Given an ordered queryset of PracticeQuestion, return a list of
    serialized dicts each augmented with 'progress_status'.
    Single DB query for all progress records.
    """
    questions = list(questions_qs)
    question_ids = [q.id for q in questions]

    progress_map = {
        p.question_id: p.status
        for p in PracticeQuestionProgress.objects.filter(
            student=student,
            question_id__in=question_ids,
        )
    }

    result = []
    for q in questions:
        data = PracticeQuestionSerializer(q).data
        # Strip fib_answer from student-facing list
        data.pop("fib_answer", None)
        data["progress_status"] = progress_map.get(q.id, "not_visited")
        result.append(data)
    return result


# ── Root (hub-level) ──────────────────────────────────────────────────────────

class AdminPracticeRootView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        modules  = PracticeModule.objects.filter(parent__isnull=True).order_by("order", "created_at")
        sections = PracticeSection.objects.filter(module__isnull=True).order_by("order", "created_at")
        return success_response({
            "modules":  PracticeModuleSerializer(modules, many=True).data,
            "sections": PracticeSectionSerializer(sections, many=True).data,
        })


# ── Modules ───────────────────────────────────────────────────────────────────

class AdminPracticeModuleListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        data = {**request.data, "parent": None}
        s = PracticeModuleSerializer(data=data)
        s.is_valid(raise_exception=True)
        s.save()
        return success_response(s.data, status_code=status.HTTP_201_CREATED)


class AdminPracticeModuleDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        return get_object_or_404(PracticeModule, pk=pk)

    def get(self, request, pk):
        module   = self._get(pk)
        children = module.children.order_by("order", "created_at")
        sections = module.sections.order_by("order", "created_at")
        return success_response({
            "module":   PracticeModuleSerializer(module).data,
            "children": PracticeModuleSerializer(children, many=True).data,
            "sections": PracticeSectionSerializer(sections, many=True).data,
        })

    def patch(self, request, pk):
        module = self._get(pk)
        s = PracticeModuleSerializer(module, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return success_response(s.data)

    def delete(self, request, pk):
        self._get(pk).delete()
        return success_response(None, status_code=status.HTTP_204_NO_CONTENT)


class AdminPracticeModuleChildrenView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        parent = get_object_or_404(PracticeModule, pk=pk)
        data   = {**request.data, "parent": str(parent.id)}
        s = PracticeModuleSerializer(data=data)
        s.is_valid(raise_exception=True)
        s.save()
        return success_response(s.data, status_code=status.HTTP_201_CREATED)


class AdminPracticeModuleSectionsView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        module = get_object_or_404(PracticeModule, pk=pk)
        data   = {**request.data, "module": str(module.id)}
        s = PracticeSectionSerializer(data=data)
        s.is_valid(raise_exception=True)
        s.save()
        return success_response(s.data, status_code=status.HTTP_201_CREATED)


# ── Sections ──────────────────────────────────────────────────────────────────

class AdminPracticeSectionListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        data = {**request.data, "module": None}
        s = PracticeSectionSerializer(data=data)
        s.is_valid(raise_exception=True)
        s.save()
        return success_response(s.data, status_code=status.HTTP_201_CREATED)


class AdminPracticeSectionDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        return get_object_or_404(PracticeSection, pk=pk)

    def get(self, request, pk):
        section   = self._get(pk)
        questions = section.questions.order_by("order", "created_at")
        return success_response({
            "section":   PracticeSectionSerializer(section).data,
            "module":    PracticeModuleSerializer(section.module).data if section.module else None,
            "questions": PracticeQuestionSerializer(questions, many=True).data,
        })

    def patch(self, request, pk):
        section = self._get(pk)
        s = PracticeSectionSerializer(section, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return success_response(s.data)

    def delete(self, request, pk):
        self._get(pk).delete()
        return success_response(None, status_code=status.HTTP_204_NO_CONTENT)


# ── Questions ─────────────────────────────────────────────────────────────────

class AdminPracticeQuestionListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, section_id):
        section = get_object_or_404(PracticeSection, pk=section_id)
        data = {
            "section":       str(section.id),
            "question_type": request.data.get("question_type", "mcq"),
            "title":         request.data.get("title", ""),
        }
        s = PracticeQuestionSerializer(data=data)
        s.is_valid(raise_exception=True)
        s.save()
        return success_response(s.data, status_code=status.HTTP_201_CREATED)


class AdminPracticeQuestionDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        return get_object_or_404(PracticeQuestion, pk=pk)

    def get(self, request, pk):
        question = self._get(pk)
        section  = question.section
        options  = []
        if question.question_type == "mcq":
            opts    = question.options.order_by("order", "created_at")
            options = PracticeQuestionOptionAdminSerializer(opts, many=True).data
        return success_response({
            "question": PracticeQuestionSerializer(question).data,
            "section":  PracticeSectionSerializer(section).data,
            "module":   PracticeModuleSerializer(section.module).data if section.module else None,
            "options":  options,
        })

    def patch(self, request, pk):
        question = self._get(pk)
        s = PracticeQuestionSerializer(question, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return success_response(s.data)

    def delete(self, request, pk):
        self._get(pk).delete()
        return success_response(None, status_code=status.HTTP_204_NO_CONTENT)


# ── MCQ Options (Admin) ───────────────────────────────────────────────────────

_OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class AdminPracticeQuestionOptionListCreateView(APIView):
    """
    GET  /admin/practice/questions/<pk>/options/  → list all options ordered
    POST /admin/practice/questions/<pk>/options/  → create a new option

    On POST, label is auto-assigned (A, B, C …) if not provided.
    When creating a correct option for a single-correct MCQ, all other
    options are automatically unmarked as correct.
    """
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        question = get_object_or_404(PracticeQuestion, pk=pk)
        options  = question.options.order_by("order", "created_at")
        return success_response(PracticeQuestionOptionAdminSerializer(options, many=True).data)

    def post(self, request, pk):
        question = get_object_or_404(PracticeQuestion, pk=pk)

        # Auto-assign label
        data = dict(request.data)
        data["question"] = str(question.id)
        if not data.get("label"):
            count = question.options.count()
            data["label"] = (
                _OPTION_LABELS[count] if count < len(_OPTION_LABELS)
                else str(count + 1)
            )
        # Auto-assign order
        if not data.get("order"):
            max_order = question.options.aggregate(m=Max("order"))["m"] or 0
            data["order"] = max_order + 1

        s = PracticeQuestionOptionAdminSerializer(data=data)
        s.is_valid(raise_exception=True)

        # Enforce single-correct: clear others before saving new correct option
        if s.validated_data.get("is_correct") and question.mcq_type == "single":
            question.options.filter(is_correct=True).update(is_correct=False)

        s.save()
        return success_response(s.data, status_code=status.HTTP_201_CREATED)


class AdminPracticeQuestionOptionDetailView(APIView):
    """
    PATCH  /admin/practice/questions/<pk>/options/<option_pk>/
    DELETE /admin/practice/questions/<pk>/options/<option_pk>/

    When marking an option as correct in a single-correct MCQ,
    all other options are automatically unmarked.
    """
    permission_classes = [IsAdminUser]

    def _get(self, pk, option_pk):
        return get_object_or_404(PracticeQuestionOption, pk=option_pk, question__id=pk)

    def patch(self, request, pk, option_pk):
        option   = self._get(pk, option_pk)
        question = option.question

        s = PracticeQuestionOptionAdminSerializer(option, data=request.data, partial=True)
        s.is_valid(raise_exception=True)

        # Enforce single-correct when marking as correct
        if s.validated_data.get("is_correct") and question.mcq_type == "single":
            question.options.exclude(pk=option_pk).filter(is_correct=True).update(is_correct=False)

        s.save()
        return success_response(s.data)

    def delete(self, request, pk, option_pk):
        self._get(pk, option_pk).delete()
        return success_response(None, status_code=status.HTTP_204_NO_CONTENT)


# ── Question image presign (admin) ────────────────────────────────────────────

class AdminPracticeQuestionBodyImagePresignView(APIView):
    """
    POST /admin/practice/questions/<pk>/question-image/presign/
    Body: { "filename": "diagram.png", "content_type": "image/png" }
    Returns: { "upload_url", "file_key", "cdn_url" }

    Generates a presigned PUT URL for the question-body image.
    Supported formats: JPEG, PNG, WebP, GIF, SVG, AVIF.
    The caller PUTs directly to R2; then PATCHes question_image_key onto the question.
    """
    permission_classes = [IsAdminUser]

    ALLOWED_MIME_PREFIXES = ("image/jpeg", "image/png", "image/webp",
                              "image/gif", "image/svg+xml", "image/avif")

    def post(self, request, pk):
        get_object_or_404(PracticeQuestion, pk=pk)
        filename     = request.data.get("filename", "image.jpg") or "image.jpg"
        content_type = request.data.get("content_type", "image/jpeg") or "image/jpeg"

        if not any(content_type.startswith(p) for p in self.ALLOWED_MIME_PREFIXES):
            return error_response(
                "Unsupported image format. Allowed: JPEG, PNG, WebP, GIF, SVG, AVIF.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        file_key   = build_file_key("image", filename)
        upload_url = generate_presigned_upload_url(file_key, content_type)
        cdn_url    = get_cdn_url(file_key)
        return success_response({
            "upload_url": upload_url,
            "file_key":   file_key,
            "cdn_url":    cdn_url,
        })


class AdminPracticeQuestionExplanationImagePresignView(APIView):
    """
    POST /admin/practice/questions/<pk>/explanation-image/presign/
    Body: { "filename": "diagram.png", "content_type": "image/png" }
    Returns: { "upload_url", "file_key", "cdn_url" }
    """
    permission_classes = [IsAdminUser]

    ALLOWED_MIME_PREFIXES = ("image/jpeg", "image/png", "image/webp",
                              "image/gif", "image/svg+xml", "image/avif")

    def post(self, request, pk):
        get_object_or_404(PracticeQuestion, pk=pk)
        filename     = request.data.get("filename", "image.jpg") or "image.jpg"
        content_type = request.data.get("content_type", "image/jpeg") or "image/jpeg"

        if not any(content_type.startswith(p) for p in self.ALLOWED_MIME_PREFIXES):
            return error_response(
                "Unsupported image format. Allowed: JPEG, PNG, WebP, GIF, SVG, AVIF.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        file_key   = build_file_key("image", filename)
        upload_url = generate_presigned_upload_url(file_key, content_type)
        cdn_url    = get_cdn_url(file_key)
        return success_response({
            "upload_url": upload_url,
            "file_key":   file_key,
            "cdn_url":    cdn_url,
        })


# ── Student-facing Practice API ───────────────────────────────────────────────

class StudentPracticeRootView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request):
        modules  = PracticeModule.objects.filter(parent__isnull=True, is_published=True).order_by("order", "created_at")
        sections = PracticeSection.objects.filter(module__isnull=True, is_published=True).order_by("order", "created_at")
        return success_response({
            "modules":  PracticeModuleSerializer(modules, many=True).data,
            "sections": PracticeSectionSerializer(sections, many=True).data,
        })


class StudentPracticeModuleView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request, pk):
        module = get_object_or_404(PracticeModule, pk=pk, is_published=True)
        children = module.children.filter(is_published=True).order_by("order", "created_at")
        sections = module.sections.filter(is_published=True).order_by("order", "created_at")
        return success_response({
            "module":   PracticeModuleSerializer(module).data,
            "children": PracticeModuleSerializer(children, many=True).data,
            "sections": PracticeSectionSerializer(sections, many=True).data,
        })


class StudentPracticeSectionView(APIView):
    """
    GET /students/practice/sections/<pk>/
    Returns section + module + questions with per-student progress_status.
    """
    permission_classes = [IsStudentUser]

    def get(self, request, pk):
        section   = get_object_or_404(PracticeSection, pk=pk, is_published=True)
        questions = section.questions.filter(is_published=True).order_by("order", "created_at")
        student   = _get_student(request)

        return success_response({
            "section":   PracticeSectionSerializer(section).data,
            "module":    PracticeModuleSerializer(section.module).data if section.module else None,
            "questions": _questions_with_progress(questions, student),
        })


class StudentPracticeQuestionView(APIView):
    """
    GET /students/practice/questions/<pk>/
    Returns bundled { question, section, module, options, prev_question_id,
                      next_question_id, attempt_info }.

    - options: list of MCQ options without is_correct (empty list for FIB)
    - attempt_info: { attempt_count, last_is_correct, correct_option_ids }
                    correct_option_ids is populated when student has already
                    attempted or completed (so explanation can highlight correctly).
    """
    permission_classes = [IsStudentUser]

    def get(self, request, pk):
        question = get_object_or_404(PracticeQuestion, pk=pk, is_published=True)
        section  = question.section
        student  = _get_student(request)

        # ── Ordered sibling question IDs (published only) ─────────────────────
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

        # ── Progress for this question ─────────────────────────────────────────
        progress = PracticeQuestionProgress.objects.filter(
            student=student, question=question
        ).first()
        progress_status = progress.status if progress else "not_visited"

        # ── Question data (strip fib_answer for students) ─────────────────────
        question_data = PracticeQuestionSerializer(question).data
        question_data.pop("fib_answer", None)
        question_data["progress_status"] = progress_status

        # ── MCQ options (without is_correct) ──────────────────────────────────
        options = []
        if question.question_type == "mcq":
            opts    = question.options.order_by("order", "created_at")
            options = PracticeQuestionOptionStudentSerializer(opts, many=True).data

        # ── Attempt info ──────────────────────────────────────────────────────
        # Returns correct_option_ids if student has already attempted/completed,
        # so the explanation panel can highlight correct answers.
        attempt_info = None
        if progress_status in (PROGRESS_ATTEMPTED, PROGRESS_COMPLETED):
            attempts = PracticeQuestionAttempt.objects.filter(
                student=student, question=question
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

        return success_response({
            "question":          question_data,
            "section":           PracticeSectionSerializer(section).data,
            "module":            PracticeModuleSerializer(section.module).data if section.module else None,
            "options":           list(options),
            "prev_question_id":  prev_question_id,
            "next_question_id":  next_question_id,
            "attempt_info":      attempt_info,
        })


class StudentPracticeQuestionProgressView(APIView):
    """
    POST /students/practice/questions/<pk>/progress/
    Body: { "status": "visited" | "attempted" | "completed" }

    Monotone state machine: not_visited → visited → attempted → completed.
    Status never regresses. Safe to call multiple times.

    Note: "completed" for FIB is posted directly from the student frontend
    when they reveal the FIB answer. "completed" for MCQ is set automatically
    by the submit endpoint on a correct submission.
    """
    permission_classes = [IsStudentUser]

    VALID_STATUSES = (PROGRESS_VISITED, PROGRESS_ATTEMPTED, PROGRESS_COMPLETED)

    def post(self, request, pk):
        question = get_object_or_404(PracticeQuestion, pk=pk, is_published=True)
        student  = _get_student(request)

        new_status = request.data.get("status")
        if new_status not in self.VALID_STATUSES:
            return error_response(
                "Invalid status. Must be 'visited', 'attempted', or 'completed'.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()

        progress, created = PracticeQuestionProgress.objects.get_or_create(
            student=student,
            question=question,
            defaults={
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

        return success_response({
            "question_id":        str(question.id),
            "status":             progress.status,
            "first_visited_at":   progress.first_visited_at,
            "first_attempted_at": progress.first_attempted_at,
            "first_completed_at": progress.first_completed_at,
        })


class StudentPracticeQuestionRevealAnswerView(APIView):
    """
    POST /students/practice/questions/<pk>/reveal-answer/

    MCQ  → returns { correct_option_ids }  — NO progress change.
            completed = answered correctly via /submit/. Viewing the
            explanation never counts as completing an MCQ question.

    FIB  → returns { fib_answer } and advances progress to "completed".
            FIB has no submit step, so revealing the answer IS completion.

    Correct answers are intentionally stripped from the normal question
    serializer so students cannot read them from the page source. This
    endpoint is the single gate that exposes the answer — only after
    the student has explicitly confirmed they want to see it.
    """
    permission_classes = [IsStudentUser]

    def post(self, request, pk):
        question = get_object_or_404(PracticeQuestion, pk=pk, is_published=True)

        # ── MCQ: just return correct option IDs, do not touch progress ───────
        # Progress for MCQ is driven exclusively by /submit/:
        #   wrong answer → attempted,  correct answer → completed.
        # Clicking "Show Explanation" must never inflate the student's score.
        if question.question_type == "mcq":
            correct_option_ids = [
                str(o.id)
                for o in question.options.filter(is_correct=True)
            ]
            return success_response({"correct_option_ids": correct_option_ids})

        # ── FIB: reveal answer + advance progress to completed ────────────────
        student = _get_student(request)
        now     = timezone.now()

        progress, created = PracticeQuestionProgress.objects.get_or_create(
            student=student,
            question=question,
            defaults={
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

        return success_response({"fib_answer": question.fib_answer})


class StudentPracticeQuestionSubmitView(APIView):
    """
    POST /students/practice/questions/<pk>/submit/
    Body: { "selected_option_ids": ["uuid1", "uuid2"] }

    Evaluates MCQ submission:
    - selected set must exactly match the correct option set for is_correct=True.
    - Records a PracticeQuestionAttempt with attempt_number auto-incremented.
    - Advances progress: attempted on wrong, completed on correct.
    - Returns { is_correct, attempt_number, correct_option_ids }.
      correct_option_ids are always returned so the frontend can highlight
      them in the explanation panel.
    """
    permission_classes = [IsStudentUser]

    def post(self, request, pk):
        question = get_object_or_404(PracticeQuestion, pk=pk, is_published=True)

        if question.question_type != "mcq":
            return error_response(
                "Submit is only valid for MCQ questions.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        student      = _get_student(request)
        selected_ids = request.data.get("selected_option_ids", [])

        if not isinstance(selected_ids, list) or not selected_ids:
            return error_response(
                "selected_option_ids must be a non-empty list.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Validate all IDs belong to this question
        valid_options = {
            str(o.id): o
            for o in question.options.filter(id__in=selected_ids)
        }
        if len(valid_options) != len(set(str(i) for i in selected_ids)):
            return error_response(
                "One or more selected option IDs are invalid.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Evaluate correctness
        correct_ids = {
            str(o.id)
            for o in question.options.filter(is_correct=True)
        }
        selected_set = {str(i) for i in selected_ids}
        is_correct   = selected_set == correct_ids

        # Record attempt
        max_attempt    = PracticeQuestionAttempt.objects.filter(
            student=student, question=question
        ).aggregate(m=Max("attempt_number"))["m"] or 0
        attempt_number = max_attempt + 1

        PracticeQuestionAttempt.objects.create(
            student=student,
            question=question,
            selected_option_ids=list(selected_set),
            is_correct=is_correct,
            attempt_number=attempt_number,
        )

        # Advance progress (monotone)
        now        = timezone.now()
        new_status = PROGRESS_COMPLETED if is_correct else PROGRESS_ATTEMPTED

        progress, created = PracticeQuestionProgress.objects.get_or_create(
            student=student,
            question=question,
            defaults={
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

        return success_response({
            "is_correct":         is_correct,
            "attempt_number":     attempt_number,
            "correct_option_ids": list(correct_ids),
        })
