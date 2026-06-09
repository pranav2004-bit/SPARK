import logging
from django.db import models, transaction, IntegrityError
from core.auth_client import create_student_auth, set_student_active, delete_student_auth
from users.models import OutboxEvent
from django.db.models import Count, Q
from django.contrib.auth.hashers import make_password
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.generics import get_object_or_404

from core.permissions import IsAdminUser, IsStudentUser, IsAdminOrSuperAdmin, IsSuperAdminUser
from core.pagination import StandardResultsPagination
from core.responses import success_response, error_response
from .models import Batch, Student, Inquiry, ScrollConfig, ScrollUpdate, OutboxEvent
from .serializers import (
    BatchSerializer,
    StudentListSerializer, StudentDetailSerializer,
    StudentCreateSerializer, StudentEditSerializer,
    StudentProfileSerializer,
    InquirySerializer,
    ScrollConfigSerializer, ScrollUpdateSerializer, ScrollReorderSerializer,
    OutboxEventSerializer,
)

logger = logging.getLogger(__name__)


# ── Health ─────────────────────────────────────────────────────────────────────

class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        from django.db import connection
        from django.core.cache import cache

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
            "service": "user-service",
            "db": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
        })


# ── Batches ────────────────────────────────────────────────────────────────────

def _batch_queryset(institution_id=None):
    qs = Batch.objects.annotate(student_count=Count("students")).order_by("-created_at")
    if institution_id:
        qs = qs.filter(institution_id=institution_id)
    return qs


class BatchListCreateView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        if request.user.role == "super_admin":
            institution_id = None
        qs = _batch_queryset(institution_id)
        return success_response(data=BatchSerializer(qs, many=True).data)

    def post(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        serializer = BatchSerializer(data=request.data, context={"institution_id": institution_id})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        batch = serializer.save(institution_id=institution_id)
        result = BatchSerializer(Batch.objects.annotate(student_count=Count("students")).get(pk=batch.pk))
        return success_response(data=result.data, message="Batch created successfully", status_code=201)


class BatchDetailView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def _get_batch(self, pk, institution_id=None):
        qs = Batch.objects.annotate(student_count=Count("students"))
        if institution_id:
            qs = qs.filter(institution_id=institution_id)
        return get_object_or_404(qs, pk=pk)

    def _institution_id(self, request):
        if request.user.role == "super_admin":
            return None
        return getattr(request.user, "institution_id", None)

    def get(self, request, pk):
        batch = self._get_batch(pk, self._institution_id(request))
        return success_response(data=BatchSerializer(batch).data)

    def put(self, request, pk):
        institution_id = self._institution_id(request)
        batch = self._get_batch(pk, institution_id)
        serializer = BatchSerializer(batch, data=request.data, context={"institution_id": institution_id})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        updated = Batch.objects.annotate(student_count=Count("students")).get(pk=pk)
        return success_response(data=BatchSerializer(updated).data, message="Batch updated successfully")

    def patch(self, request, pk):
        institution_id = self._institution_id(request)
        batch = self._get_batch(pk, institution_id)
        serializer = BatchSerializer(batch, data=request.data, partial=True, context={"institution_id": institution_id})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        updated = Batch.objects.annotate(student_count=Count("students")).get(pk=pk)
        return success_response(data=BatchSerializer(updated).data, message="Batch updated successfully")

    def delete(self, request, pk):
        institution_id = self._institution_id(request)
        batch = self._get_batch(pk, institution_id)
        if batch.students.exists():
            return error_response(message="Cannot delete batch with existing students", status_code=400)
        batch.delete()
        return success_response(message="Batch deleted successfully")


# ── Students (Admin) ───────────────────────────────────────────────────────────

def _student_queryset(institution_id=None):
    qs = Student.objects.select_related("batch").order_by("-created_at")
    if institution_id:
        qs = qs.filter(institution_id=institution_id)
    return qs


def _apply_student_filters(qs, request):
    search = request.query_params.get("search", "").strip()
    department = request.query_params.get("department", "").strip()
    batch_id = request.query_params.get("batch_id", "").strip()
    if search:
        qs = qs.filter(
            Q(student_id__icontains=search) | Q(fullname__icontains=search)
        )
    if department:
        qs = qs.filter(department__iexact=department)
    if batch_id:
        qs = qs.filter(batch_id=batch_id)
    return qs


class AdminStudentListCreateView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def _institution_id(self, request):
        if request.user.role == "super_admin":
            return None
        return getattr(request.user, "institution_id", None)

    def get(self, request):
        qs = _apply_student_filters(_student_queryset(self._institution_id(request)), request)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(StudentListSerializer(page, many=True).data)

    def post(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        serializer = StudentCreateSerializer(data=request.data, context={"institution_id": institution_id})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        student = serializer.save()
        return success_response(
            data=StudentDetailSerializer(student).data,
            message="Student created successfully",
            status_code=201,
        )


class AdminStudentDetailView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def _institution_id(self, request):
        if request.user.role == "super_admin":
            return None
        return getattr(request.user, "institution_id", None)

    def _get(self, pk, institution_id=None):
        return get_object_or_404(_student_queryset(institution_id), pk=pk)

    def get(self, request, pk):
        return success_response(data=StudentDetailSerializer(self._get(pk, self._institution_id(request))).data)

    def put(self, request, pk):
        institution_id = self._institution_id(request)
        student = self._get(pk, institution_id)
        serializer = StudentEditSerializer(student, data=request.data, partial=False)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(data=StudentDetailSerializer(self._get(pk, institution_id)).data, message="Student updated")

    def patch(self, request, pk):
        institution_id = self._institution_id(request)
        student = self._get(pk, institution_id)
        serializer = StudentEditSerializer(student, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(data=StudentDetailSerializer(self._get(pk, institution_id)).data, message="Student updated")

    def delete(self, request, pk):
        institution_id = self._institution_id(request)
        student = self._get(pk, institution_id)
        student_id = student.student_id
        user_id = str(student.user_id)

        # Atomic: delete the profile AND enqueue the auth cleanup in one
        # transaction.  If the HTTP response never reaches the client (crash,
        # timeout), the outbox event survives and the worker retries the
        # auth-service call.  The student can no longer log in after the auth
        # account is removed; the outbox worker delivers that within seconds
        # under normal conditions.
        with transaction.atomic():
            student.delete()
            OutboxEvent.objects.create(
                event_type=OutboxEvent.EventType.DELETE_STUDENT_AUTH,
                payload={
                    'version': 1,
                    'student_id': student_id,
                    'user_id': user_id,
                },
            )

        return success_response(message="Student deleted successfully")


class AdminStudentToggleStatusView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        institution_id = getattr(request.user, "institution_id", None)
        student = get_object_or_404(Student, pk=pk, institution_id=institution_id)
        student.is_active = not student.is_active
        student.save(update_fields=["is_active"])
        set_student_active(student.student_id, student.is_active)
        return success_response(
            data={"is_active": student.is_active},
            message=f"Student {'enabled' if student.is_active else 'disabled'} successfully",
        )


class AdminBatchStudentsView(APIView):
    permission_classes = [IsAdminOrSuperAdmin]

    def get(self, request, batch_id):
        institution_id = None if request.user.role == "super_admin" else getattr(request.user, "institution_id", None)
        qs = Batch.objects.filter(pk=batch_id)
        if institution_id:
            qs = qs.filter(institution_id=institution_id)
        get_object_or_404(qs)
        students = _apply_student_filters(_student_queryset(institution_id).filter(batch_id=batch_id), request)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(students, request)
        return paginator.get_paginated_response(StudentListSerializer(page, many=True).data)


# ── Bulk Student Import ────────────────────────────────────────────────────────

class AdminStudentBulkCreateView(APIView):
    permission_classes = [IsAdminUser]
    MAX_IMPORT = 1000

    def post(self, request):
        student_ids_raw = request.data.get("student_ids")
        department = str(request.data.get("department", "")).strip()
        batch_id = request.data.get("batch_id", "")
        institution_id = getattr(request.user, "institution_id", None)

        if not isinstance(student_ids_raw, list):
            return error_response(message="student_ids must be a list of strings.", status_code=400)
        if not department:
            return error_response(message="department is required.", status_code=400)

        try:
            batch_qs = Batch.objects.filter(pk=batch_id)
            if institution_id:
                batch_qs = batch_qs.filter(institution_id=institution_id)
            batch = batch_qs.get()
        except (Batch.DoesNotExist, Exception):
            return error_response(message="Batch not found.", status_code=400)

        sanitized = [str(x).strip().upper() if x is not None else "" for x in student_ids_raw]
        if not sanitized:
            return error_response(message="No student IDs provided.", status_code=400)
        if len(sanitized) > self.MAX_IMPORT:
            return error_response(
                message=f"Maximum {self.MAX_IMPORT} students per import. Received {len(sanitized)}.",
                status_code=400,
            )

        non_empty = [s for s in sanitized if s]
        existing_ids: set = set(
            Student.objects.filter(student_id__in=non_empty).values_list("student_id", flat=True)
        )

        results = []
        seen: set = set()
        created_count = 0
        rejected_count = 0

        for raw_id in sanitized:
            if not raw_id:
                results.append({"student_id": "(empty)", "status": "rejected", "reason": "Empty student ID"})
                rejected_count += 1
                continue

            if len(raw_id) > 100:
                results.append({"student_id": raw_id[:30] + "…", "status": "rejected", "reason": "Student ID exceeds 100 characters"})
                rejected_count += 1
                continue

            if raw_id in seen:
                results.append({"student_id": raw_id, "status": "rejected", "reason": "Duplicate in import file"})
                rejected_count += 1
                continue
            seen.add(raw_id)

            if raw_id in existing_ids:
                results.append({"student_id": raw_id, "status": "rejected", "reason": "Student ID already exists"})
                rejected_count += 1
                continue

            try:
                import uuid as _uuid
                user_id = _uuid.uuid4()

                # Create auth account first; skip this student on failure.
                try:
                    create_student_auth(
                        user_id=str(user_id),
                        student_id=raw_id,
                        institution_id=str(institution_id) if institution_id else None,
                    )
                except RuntimeError as exc:
                    results.append({"student_id": raw_id, "status": "rejected", "reason": f"Auth error: {exc}"})
                    rejected_count += 1
                    continue

                with transaction.atomic():
                    Student.objects.create(
                        user_id=user_id,
                        student_id=raw_id,
                        department=department,
                        batch=batch,
                        institution_id=institution_id,
                    )
                existing_ids.add(raw_id)
                results.append({"student_id": raw_id, "status": "created"})
                created_count += 1

            except IntegrityError as exc:
                # Profile creation failed after auth account was created — roll back auth.
                delete_student_auth(raw_id)
                results.append({"student_id": raw_id, "status": "rejected", "reason": "Student ID already exists (conflict)"})
                rejected_count += 1
                logger.warning("Bulk create IntegrityError for %s: %s", raw_id, exc)

            except Exception as exc:
                delete_student_auth(raw_id)
                results.append({"student_id": raw_id, "status": "rejected", "reason": "Server error"})
                rejected_count += 1
                logger.error("Bulk create error for %s: %s", raw_id, exc, exc_info=True)

        return success_response(
            data={
                "total": len(sanitized),
                "created": created_count,
                "rejected": rejected_count,
                "results": results,
            },
            message=f"Import complete: {created_count} created, {rejected_count} rejected.",
        )


# ── Student: Own Profile ───────────────────────────────────────────────────────

class StudentMeView(APIView):
    permission_classes = [IsStudentUser]

    def _get_student(self, request):
        return get_object_or_404(
            Student.objects.select_related("batch"),
            user_id=request.user.id,
            is_active=True,
        )

    def get(self, request):
        return success_response(data=StudentProfileSerializer(self._get_student(request)).data)

    def put(self, request):
        student = self._get_student(request)
        serializer = StudentProfileSerializer(student, data=request.data, partial=False)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        first_save = not student.is_profile_completed
        serializer.save()
        if first_save:
            student.refresh_from_db()
            student.is_profile_completed = True
            student.save(update_fields=["is_profile_completed"])
        return success_response(
            data=StudentProfileSerializer(student).data,
            message="Profile updated successfully",
        )

    def patch(self, request):
        student = self._get_student(request)
        serializer = StudentProfileSerializer(student, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        first_save = not student.is_profile_completed
        serializer.save()
        if first_save:
            student.refresh_from_db()
            student.is_profile_completed = True
            student.save(update_fields=["is_profile_completed"])
        return success_response(
            data=StudentProfileSerializer(student).data,
            message="Profile updated successfully",
        )


# ── Inquiries ─────────────────────────────────────────────────────────────────

class StudentInquiryView(APIView):
    permission_classes = [IsStudentUser]

    def post(self, request):
        message = str(request.data.get("message", "")).strip()
        if not message:
            return error_response(message="Message cannot be empty.", status_code=400)
        if len(message) < 10:
            return error_response(message="Message must be at least 10 characters.", status_code=400)
        if len(message) > 2000:
            return error_response(message="Message cannot exceed 2000 characters.", status_code=400)

        student = get_object_or_404(Student, user_id=request.user.id, is_active=True)
        inquiry = Inquiry.objects.create(student=student, message=message)
        return success_response(data=InquirySerializer(inquiry).data, status_code=201, message="Inquiry submitted.")


class AdminInquiryListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        qs = (
            Inquiry.objects
            .select_related("student", "student__batch")
            .filter(student__institution_id=institution_id)
            .order_by("-created_at")
        )
        if request.query_params.get("unread") == "true":
            qs = qs.filter(is_read=False)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(InquirySerializer(page, many=True).data)


class AdminInquiryMarkReadView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        institution_id = getattr(request.user, "institution_id", None)
        inquiry = get_object_or_404(
            Inquiry.objects.select_related("student"),
            pk=pk,
            student__institution_id=institution_id,
        )
        inquiry.is_read = True
        inquiry.save(update_fields=["is_read"])
        return success_response(data=InquirySerializer(inquiry).data, message="Marked as read.")


# ── Scroll Config & Updates ───────────────────────────────────────────────────

class AdminScrollConfigView(APIView):
    permission_classes = [IsAdminUser]

    def _get_config(self):
        config = ScrollConfig.objects.filter(pk=1).first()
        if config is None:
            config = ScrollConfig.objects.create()  # save() override forces pk=1
        return config

    def get(self, request):
        return success_response(data=ScrollConfigSerializer(self._get_config()).data)

    def patch(self, request):
        config = self._get_config()
        serializer = ScrollConfigSerializer(config, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(data=serializer.data, message="Scroll configuration updated.")


class AdminScrollUpdateListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        updates = ScrollUpdate.objects.all()
        return success_response(data=ScrollUpdateSerializer(updates, many=True).data)

    def post(self, request):
        max_order = ScrollUpdate.objects.aggregate(m=models.Max("order"))["m"] or 0
        data = {**request.data, "order": max_order + 1}
        serializer = ScrollUpdateSerializer(data=data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        update = serializer.save()
        return success_response(data=ScrollUpdateSerializer(update).data, status_code=201, message="Scroll update created.")


class AdminScrollUpdateDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        return get_object_or_404(ScrollUpdate, pk=pk)

    def get(self, request, pk):
        return success_response(data=ScrollUpdateSerializer(self._get(pk)).data)

    def patch(self, request, pk):
        item = self._get(pk)
        serializer = ScrollUpdateSerializer(item, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(data=serializer.data, message="Scroll update saved.")

    def delete(self, request, pk):
        self._get(pk).delete()
        return success_response(message="Scroll update deleted.")


class AdminScrollReorderView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = ScrollReorderSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        ids = serializer.validated_data["ids"]
        updates = {str(u.pk): u for u in ScrollUpdate.objects.filter(pk__in=ids)}
        if len(updates) != len(ids):
            return error_response(message="One or more IDs not found.", status_code=400)
        to_save = []
        for position, uid in enumerate(ids):
            item = updates[str(uid)]
            item.order = position
            to_save.append(item)
        ScrollUpdate.objects.bulk_update(to_save, ["order"])
        return success_response(data=ScrollUpdateSerializer(ScrollUpdate.objects.all(), many=True).data, message="Order saved.")


class StudentScrollView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        config = ScrollConfig.objects.filter(pk=1).first()
        if config is None:
            config = ScrollConfig.objects.create()
        updates = ScrollUpdate.objects.all() if config.is_enabled else ScrollUpdate.objects.none()
        return success_response(data={
            "is_enabled": config.is_enabled,
            "direction": config.direction,
            "updates": ScrollUpdateSerializer(updates, many=True).data,
        })


# ── Super Admin: Outbox Dead-Letter Queue ─────────────────────────────────────

class OutboxDeadLetterListView(APIView):
    """
    GET /api/users/admin/outbox/dead-letters/
    Returns a paginated list of dead_letter OutboxEvent records, newest first.
    Permission: IsSuperAdminUser only.
    """
    permission_classes = [IsSuperAdminUser]

    def get(self, request):
        qs = OutboxEvent.objects.filter(
            status=OutboxEvent.Status.DEAD_LETTER
        ).order_by('-created_at')
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(OutboxEventSerializer(page, many=True).data)


class OutboxDeadLetterRetryView(APIView):
    """
    POST /api/users/admin/outbox/dead-letters/<pk>/retry/
    Resets a single dead_letter event back to pending so the worker picks it
    up on the next poll cycle.  Returns 404 if the event does not exist or is
    not currently in dead_letter status.
    Permission: IsSuperAdminUser only.
    """
    permission_classes = [IsSuperAdminUser]

    def post(self, request, pk):
        event = get_object_or_404(
            OutboxEvent,
            pk=pk,
            status=OutboxEvent.Status.DEAD_LETTER,
        )
        event.status = OutboxEvent.Status.PENDING
        event.retry_after = None
        event.last_error = ''
        event.save(update_fields=['status', 'retry_after', 'last_error'])
        logger.info(
            "Super admin manually retried dead-letter outbox event %s (student_id=%s).",
            event.id, event.payload.get('student_id', '?'),
        )
        return success_response(
            data=OutboxEventSerializer(event).data,
            message="Event reset to pending — worker will retry on next poll.",
        )


class OutboxHealthView(APIView):
    """
    GET /api/users/admin/outbox/health/
    Returns event counts per status for a health summary widget.
    Permission: IsSuperAdminUser only.
    """
    permission_classes = [IsSuperAdminUser]

    def get(self, request):
        counts = (
            OutboxEvent.objects
            .values('status')
            .annotate(count=models.Count('id'))
        )
        data = {row['status']: row['count'] for row in counts}
        return success_response(data={
            'pending':    data.get('pending',    0),
            'processing': data.get('processing', 0),
            'done':       data.get('done',       0),
            'dead_letter': data.get('dead_letter', 0),
        })
