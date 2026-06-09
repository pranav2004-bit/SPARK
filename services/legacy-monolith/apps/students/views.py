import logging
from django.db import models, transaction, IntegrityError
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.generics import get_object_or_404

from apps.authentication.serializers import StudentLoginSerializer
from apps.authentication.tokens import get_tokens_for_user
from apps.batches.models import Batch
from core.permissions import IsAdminUser, IsStudentUser
from core.pagination import StandardResultsPagination
from core.responses import success_response, error_response
from .models import Student, Inquiry, ScrollConfig, ScrollUpdate, ResourceModule, ResourceSection, ResourceUpload
from .serializers import (
    StudentListSerializer, StudentDetailSerializer,
    StudentCreateSerializer, StudentEditSerializer,
    StudentProfileSerializer, ChangePasswordSerializer,
    InquirySerializer,
    ScrollConfigSerializer, ScrollUpdateSerializer, ScrollReorderSerializer,
    ResourceModuleSerializer, ResourceSectionSerializer, ResourceUploadSerializer,
    PresignedUploadRequestSerializer, ConfirmUploadSerializer, AddLinkSerializer,
)

User = get_user_model()

logger = logging.getLogger(__name__)
DEFAULT_PASSWORD = "ANITS@123"
INVALID_CREDENTIALS_MSG = "Invalid credentials"


# ── Student Login ──────────────────────────────────────────────────────────────

class StudentLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = StudentLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)

        student_id = serializer.validated_data["student_id"]
        password = serializer.validated_data["password"]

        try:
            student = Student.objects.select_related("user").get(student_id=student_id)
        except Student.DoesNotExist:
            logger.warning("Student login failed — unknown student_id: %s", student_id)
            return error_response(message=INVALID_CREDENTIALS_MSG, status_code=401)

        if not student.user.check_password(password):
            return error_response(message=INVALID_CREDENTIALS_MSG, status_code=401)

        if not student.is_active or not student.user.is_active:
            return error_response(message="Account is disabled. Contact admin.", status_code=403)

        tokens = get_tokens_for_user(student.user, student=student)
        return success_response(
            data={
                **tokens,
                "user": {
                    "student_id": student.student_id,
                    "role": student.user.role,
                    "is_profile_completed": student.is_profile_completed,
                    "fullname": student.fullname or "",
                },
            },
            message="Login successful",
        )


# ── Admin: Student CRUD ────────────────────────────────────────────────────────

def _student_queryset():
    return Student.objects.select_related("user", "batch").order_by("-created_at")


def _apply_filters(qs, request):
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
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = _apply_filters(_student_queryset(), request)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = StudentListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = StudentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        student = serializer.save()
        return success_response(
            data=StudentDetailSerializer(student).data,
            message="Student created successfully",
            status_code=201,
        )


class AdminStudentDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        return get_object_or_404(_student_queryset(), pk=pk)

    def get(self, request, pk):
        return success_response(data=StudentDetailSerializer(self._get(pk)).data)

    def put(self, request, pk):
        student = self._get(pk)
        serializer = StudentEditSerializer(student, data=request.data, partial=False)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(data=StudentDetailSerializer(self._get(pk)).data, message="Student updated")

    def patch(self, request, pk):
        student = self._get(pk)
        serializer = StudentEditSerializer(student, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(data=StudentDetailSerializer(self._get(pk)).data, message="Student updated")

    def delete(self, request, pk):
        student = self._get(pk)
        student.user.delete()  # cascades to student via OneToOne
        return success_response(message="Student deleted successfully")


class AdminStudentToggleStatusView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        student.is_active = not student.is_active
        student.user.is_active = student.is_active
        student.save(update_fields=["is_active"])
        student.user.save(update_fields=["is_active"])
        return success_response(
            data={"is_active": student.is_active},
            message=f"Student {'enabled' if student.is_active else 'disabled'} successfully",
        )


class AdminStudentResetPasswordView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        student = get_object_or_404(Student.objects.select_related("user"), pk=pk)
        student.user.set_password(DEFAULT_PASSWORD)
        student.user.save(update_fields=["password"])
        student.is_profile_completed = False
        student.save(update_fields=["is_profile_completed"])
        return success_response(message="Password reset to default successfully")


class AdminBatchStudentsView(APIView):
    """Students scoped to a specific batch."""
    permission_classes = [IsAdminUser]

    def get(self, request, batch_id):
        get_object_or_404(Batch, pk=batch_id)
        qs = _apply_filters(_student_queryset().filter(batch_id=batch_id), request)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = StudentListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# ── Student: Self-Profile ──────────────────────────────────────────────────────

class StudentProfileView(APIView):
    permission_classes = [IsStudentUser]

    def _get_student(self, request):
        return get_object_or_404(
            Student.objects.select_related("user", "batch"),
            user_id=request.user.id,
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
        student.refresh_from_db()
        if first_save:
            student.is_profile_completed = True
            student.save(update_fields=["is_profile_completed"])
        # Issue new tokens with updated is_profile_completed
        tokens = get_tokens_for_user(student.user, student=student)
        return success_response(
            data={"profile": StudentProfileSerializer(student).data, **tokens},
            message="Profile updated successfully",
        )

    def patch(self, request):
        student = self._get_student(request)
        serializer = StudentProfileSerializer(student, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        first_save = not student.is_profile_completed
        serializer.save()
        student.refresh_from_db()
        if first_save:
            student.is_profile_completed = True
            student.save(update_fields=["is_profile_completed"])
        tokens = get_tokens_for_user(student.user, student=student)
        return success_response(
            data={"profile": StudentProfileSerializer(student).data, **tokens},
            message="Profile updated successfully",
        )


class StudentChangePasswordView(APIView):
    permission_classes = [IsStudentUser]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)

        student = get_object_or_404(Student.objects.select_related("user"), user_id=request.user.id)
        user = student.user

        if not user.check_password(serializer.validated_data["current_password"]):
            return error_response(message="Current password is incorrect", status_code=400)

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])

        # Force re-auth — return fresh tokens
        tokens = get_tokens_for_user(user, student=student)
        return success_response(
            data=tokens,
            message="Password updated successfully. Please log in again.",
        )


# ── Admin: Bulk Student Import ─────────────────────────────────────────────────

class AdminStudentBulkCreateView(APIView):
    """
    Bulk-create students from a list of student IDs.

    All students receive the same department, batch, and default password.
    Password is hashed once before the loop for performance.
    Each row is processed atomically — one failure never rolls back others.

    POST /api/admin/students/bulk-create/
    Body: { student_ids: string[], department: string, batch_id: uuid }
    Response: { total, created, rejected, results: [{student_id, status, reason?}] }
    """
    permission_classes = [IsAdminUser]
    MAX_IMPORT = 2000

    def post(self, request):
        student_ids_raw = request.data.get("student_ids")
        department = str(request.data.get("department", "")).strip()
        batch_id = request.data.get("batch_id", "")

        # ── Input validation ────────────────────────────────────────────────
        if not isinstance(student_ids_raw, list):
            return error_response(
                message="student_ids must be a list of strings.",
                status_code=400,
            )
        if not department:
            return error_response(message="department is required.", status_code=400)

        try:
            batch = Batch.objects.get(pk=batch_id)
        except (Batch.DoesNotExist, Exception):
            return error_response(message="Batch not found.", status_code=400)

        # Sanitize: stringify → strip → uppercase
        sanitized = [str(x).strip().upper() if x is not None else "" for x in student_ids_raw]

        if not sanitized:
            return error_response(message="No student IDs provided.", status_code=400)

        if len(sanitized) > self.MAX_IMPORT:
            return error_response(
                message=(
                    f"Maximum {self.MAX_IMPORT} students per import. "
                    f"Received {len(sanitized)}. Please split into smaller files."
                ),
                status_code=400,
            )

        # Pre-load all existing student_ids from this batch to avoid per-row queries
        non_empty = [s for s in sanitized if s]
        existing_ids: set = set(
            Student.objects.filter(student_id__in=non_empty).values_list("student_id", flat=True)
        )

        # Hash the default password ONCE — reused for every student in this import.
        # This is the critical performance optimisation: password hashing is CPU-bound
        # and would be O(n * ~100ms) if done per student.
        hashed_pw = make_password(DEFAULT_PASSWORD)

        results = []
        seen: set = set()
        created_count = 0
        rejected_count = 0

        for raw_id in sanitized:
            # ── Empty ──────────────────────────────────────────────────────
            if not raw_id:
                results.append({
                    "student_id": "(empty)",
                    "status": "rejected",
                    "reason": "Empty student ID",
                })
                rejected_count += 1
                continue

            # ── Too long ───────────────────────────────────────────────────
            if len(raw_id) > 100:
                results.append({
                    "student_id": raw_id[:30] + "…",
                    "status": "rejected",
                    "reason": "Student ID exceeds 100 characters",
                })
                rejected_count += 1
                continue

            # ── Duplicate within this import ───────────────────────────────
            if raw_id in seen:
                results.append({
                    "student_id": raw_id,
                    "status": "rejected",
                    "reason": "Duplicate in import file",
                })
                rejected_count += 1
                continue
            seen.add(raw_id)

            # ── Already exists in DB ───────────────────────────────────────
            if raw_id in existing_ids:
                results.append({
                    "student_id": raw_id,
                    "status": "rejected",
                    "reason": "Student ID already exists",
                })
                rejected_count += 1
                continue

            # ── Create ────────────────────────────────────────────────────
            try:
                with transaction.atomic():
                    email = f"{raw_id.lower()}@aptlogic.internal"
                    user = User(email=email, role="student", is_active=True)
                    user.password = hashed_pw  # pre-hashed — skip per-student hashing
                    user.save()
                    Student.objects.create(
                        student_id=raw_id,
                        user=user,
                        department=department,
                        batch=batch,
                    )
                # Track so same-file duplicates that slip past pre-check are caught
                existing_ids.add(raw_id)
                results.append({"student_id": raw_id, "status": "created"})
                created_count += 1

            except IntegrityError as exc:
                msg = str(exc).lower()
                if "email" in msg:
                    reason = "Email derived from this ID already in use"
                else:
                    reason = "Student ID already exists (conflict)"
                results.append({"student_id": raw_id, "status": "rejected", "reason": reason})
                rejected_count += 1
                logger.warning("Bulk create IntegrityError for %s: %s", raw_id, exc)

            except Exception as exc:
                results.append({
                    "student_id": raw_id,
                    "status": "rejected",
                    "reason": "Server error — contact administrator",
                })
                rejected_count += 1
                logger.error("Bulk create unexpected error for %s: %s", raw_id, exc, exc_info=True)

        logger.info(
            "Bulk student import complete: total=%d created=%d rejected=%d batch=%s dept=%s",
            len(sanitized), created_count, rejected_count, batch.batch_name, department,
        )

        return success_response(
            data={
                "total": len(sanitized),
                "created": created_count,
                "rejected": rejected_count,
                "results": results,
            },
            message=f"Import complete: {created_count} created, {rejected_count} rejected.",
        )


# ── Student: Submit Inquiry ───────────────────────────────────────────────────
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

        student = get_object_or_404(Student, user=request.user)
        inquiry = Inquiry.objects.create(student=student, message=message)
        serializer = InquirySerializer(inquiry)
        logger.info("Inquiry submitted by student %s", student.student_id)
        return success_response(data=serializer.data, status_code=201, message="Inquiry submitted successfully.")


# ── Admin: List & Mark-Read Inquiries ─────────────────────────────────────────
class AdminInquiryListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = (
            Inquiry.objects
            .select_related("student", "student__batch")
            .order_by("-created_at")
        )
        # Optional filter: unread only
        if request.query_params.get("unread") == "true":
            qs = qs.filter(is_read=False)

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = InquirySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminInquiryMarkReadView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        inquiry = get_object_or_404(Inquiry, pk=pk)
        inquiry.is_read = True
        inquiry.save(update_fields=["is_read"])
        return success_response(data=InquirySerializer(inquiry).data, message="Marked as read.")


# ── Admin: Scroll Config & Updates ───────────────────────────────────────────

class AdminScrollConfigView(APIView):
    """GET/PATCH the singleton scroll configuration."""
    permission_classes = [IsAdminUser]

    def _get_config(self):
        config, _ = ScrollConfig.objects.get_or_create(pk=1)
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
    """List all scroll updates or create a new one."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        updates = ScrollUpdate.objects.all()
        return success_response(data=ScrollUpdateSerializer(updates, many=True).data)

    def post(self, request):
        # New items go to the end: max existing order + 1
        max_order = ScrollUpdate.objects.aggregate(
            m=models.Max("order")
        )["m"] or 0
        data = {**request.data, "order": max_order + 1}
        serializer = ScrollUpdateSerializer(data=data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        update = serializer.save()
        return success_response(
            data=ScrollUpdateSerializer(update).data,
            message="Scroll update created.",
            status_code=201,
        )


class AdminScrollUpdateDetailView(APIView):
    """Retrieve, edit, or delete a single scroll update."""
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
    """
    POST { ids: [uuid, uuid, ...] }
    Sets the `order` field of each ScrollUpdate to match the position in the list.
    """
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
        all_updates = ScrollUpdate.objects.all()
        return success_response(
            data=ScrollUpdateSerializer(all_updates, many=True).data,
            message="Order saved.",
        )


# ── Student: Scroll Updates (read-only) ──────────────────────────────────────

class StudentScrollView(APIView):
    """
    Returns scroll config + updates.
    Public (AllowAny) — scroll announcements contain no sensitive data and
    must be visible on landing page, login pages, and all authenticated views.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        config, _ = ScrollConfig.objects.get_or_create(pk=1)
        updates = ScrollUpdate.objects.all() if config.is_enabled else ScrollUpdate.objects.none()
        return success_response(data={
            "is_enabled": config.is_enabled,
            "direction": config.direction,
            "updates": ScrollUpdateSerializer(updates, many=True).data,
        })


# ── Resource Modules ──────────────────────────────────────────────────────────

class AdminResourceModuleListCreateView(APIView):
    """List all resource modules or create a new one."""
    permission_classes = [IsAdminUser]

    def _ensure_system_module(self):
        """Guarantee the Company Resources system module always exists.
        Also self-heals the canonical name if it was accidentally mis-typed
        (e.g. "Company Resourcess") — only corrects the exact known typo so
        admin-intentional renames are preserved."""
        obj, created = ResourceModule.objects.get_or_create(
            is_system=True,
            defaults={"name": "Company Resources", "is_published": True, "order": 0},
        )
        if not created and obj.name in ("Company Resourcess", "CompanyResources", "company resources"):
            obj.name = "Company Resources"
            obj.save(update_fields=["name"])

    def get(self, request):
        self._ensure_system_module()
        modules = ResourceModule.objects.filter(parent=None)
        return success_response(data=ResourceModuleSerializer(modules, many=True).data)

    def post(self, request):
        serializer = ResourceModuleSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        max_order = ResourceModule.objects.aggregate(m=models.Max("order"))["m"] or 0
        serializer.save(order=max_order + 1, is_system=False)
        return success_response(data=serializer.data, status_code=201, message="Module created.")


class AdminResourceModuleDetailView(APIView):
    """GET detail (module + children + sections), PATCH update, DELETE a module."""
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        return get_object_or_404(ResourceModule, pk=pk)

    def get(self, request, pk):
        module   = self._get(pk)
        children = ResourceModule.objects.filter(parent=module)
        sections = ResourceSection.objects.filter(module=module)
        return success_response(data={
            "module":   ResourceModuleSerializer(module).data,
            "children": ResourceModuleSerializer(children, many=True).data,
            "sections": ResourceSectionSerializer(sections, many=True).data,
        })

    def patch(self, request, pk):
        module = self._get(pk)
        serializer = ResourceModuleSerializer(module, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(data=serializer.data, message="Module updated.")

    def delete(self, request, pk):
        module = self._get(pk)
        if module.is_system:
            return error_response(message="The system module cannot be deleted.", status_code=403)
        module.delete()
        return success_response(message="Module deleted.")


class AdminResourceModuleChildrenView(APIView):
    """Create a child sub-module under a parent module."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        parent = get_object_or_404(ResourceModule, pk=pk)
        serializer = ResourceModuleSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        max_order = ResourceModule.objects.filter(parent=parent).aggregate(m=models.Max("order"))["m"] or 0
        serializer.save(parent=parent, order=max_order + 1, is_system=False)
        return success_response(data=serializer.data, status_code=201, message="Sub-module created.")


class AdminResourceSectionListCreateView(APIView):
    """List or create sections under a module."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        module = get_object_or_404(ResourceModule, pk=pk)
        serializer = ResourceSectionSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        max_order = ResourceSection.objects.filter(module=module).aggregate(m=models.Max("order"))["m"] or 0
        serializer.save(module=module, order=max_order + 1)
        return success_response(data=serializer.data, status_code=201, message="Section created.")


class AdminResourceSectionDetailView(APIView):
    """PATCH or DELETE a single resource section."""
    permission_classes = [IsAdminUser]

    def _get(self, pk):
        return get_object_or_404(ResourceSection, pk=pk)

    def patch(self, request, pk):
        section = self._get(pk)
        serializer = ResourceSectionSerializer(section, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(data=serializer.data, message="Section updated.")

    def delete(self, request, pk):
        section = self._get(pk)
        if section.uploads.exists():
            return error_response(
                message="Cannot delete a section that has uploads. Remove all uploads first.",
                status_code=400,
            )
        section.delete()
        return success_response(message="Section deleted.")


# ── Resource Uploads ──────────────────────────────────────────────────────────

def _get_resource_section_scoped(module_id, section_id):
    module = get_object_or_404(ResourceModule, pk=module_id)
    return get_object_or_404(ResourceSection, pk=section_id, module=module)


class AdminResourceUploadListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, module_id, section_id):
        section = _get_resource_section_scoped(module_id, section_id)
        uploads = ResourceUpload.objects.filter(resource_section=section).order_by("-created_at")
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(uploads, request)
        return paginator.get_paginated_response(ResourceUploadSerializer(page, many=True).data)


class AdminResourceUploadPresignedUrlView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, module_id, section_id):
        from core.storage import build_file_key, generate_presigned_upload_url
        _get_resource_section_scoped(module_id, section_id)
        serializer = PresignedUploadRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        filename     = serializer.validated_data["filename"]
        content_type = serializer.validated_data["content_type"]
        upload_type  = serializer.validated_data["upload_type"]
        file_key = build_file_key(upload_type, filename)
        try:
            upload_url = generate_presigned_upload_url(file_key, content_type)
        except RuntimeError as exc:
            logger.error("R2 not configured: %s", exc)
            return error_response(message="File storage is not configured.", status_code=503)
        return success_response(data={"upload_url": upload_url, "file_key": file_key})


class AdminResourceUploadConfirmView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, module_id, section_id):
        section = _get_resource_section_scoped(module_id, section_id)
        serializer = ConfirmUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        upload = ResourceUpload.objects.create(
            resource_section=section,
            upload_type=serializer.validated_data["upload_type"],
            file_url=serializer.validated_data["file_key"],
            original_filename=serializer.validated_data["original_filename"],
            file_size_bytes=serializer.validated_data["file_size_bytes"],
        )
        return success_response(data=ResourceUploadSerializer(upload).data, status_code=201)


class AdminResourceUploadAddLinkView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, module_id, section_id):
        section = _get_resource_section_scoped(module_id, section_id)
        serializer = AddLinkSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        upload = ResourceUpload.objects.create(
            resource_section=section,
            upload_type=serializer.validated_data["upload_type"],
            file_url=serializer.validated_data["file_url"],
        )
        return success_response(data=ResourceUploadSerializer(upload).data, status_code=201)


class AdminResourceUploadDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, module_id, section_id, upload_id):
        section = _get_resource_section_scoped(module_id, section_id)
        upload  = get_object_or_404(ResourceUpload, pk=upload_id, resource_section=section)
        name = (request.data.get("original_filename") or "").strip()
        if not name:
            return error_response(message="Name cannot be empty.", status_code=400)
        upload.original_filename = name
        upload.save(update_fields=["original_filename"])
        return success_response(data=ResourceUploadSerializer(upload).data, message="Renamed.")

    def delete(self, request, module_id, section_id, upload_id):
        from core.storage import is_file_type
        from apps.companies.tasks import async_delete_file
        section = _get_resource_section_scoped(module_id, section_id)
        upload  = get_object_or_404(ResourceUpload, pk=upload_id, resource_section=section)
        file_key    = upload.file_url
        upload_type = upload.upload_type
        upload.delete()
        if is_file_type(upload_type):
            async_delete_file.delay(file_key)
        return success_response(message="Upload deleted.")


# ── Student-facing Resource API ───────────────────────────────────────────────

def _check_publish_chain(module):
    """
    Walk the ancestor chain from this module to root.
    Returns True only if EVERY module in the chain (inclusive) is published.
    Edge cases:
      - Root module unpublished → False (nothing below visible)
      - Any ancestor unpublished → False regardless of current module
      - Orphan (no parent, is_published=True) → True
    """
    current = module
    while current is not None:
        if not current.is_published:
            return False
        current = current.parent
    return True


class StudentResourceHubView(APIView):
    """
    Returns all top-level (parent=None) published resource modules.
    Students see this as the Resources hub.

    Publish cascade: only parent=None modules that are is_published=True.
    No ancestor chain needed here because top-level modules have no parent.
    """
    permission_classes = [IsStudentUser]

    def get(self, request):
        modules = ResourceModule.objects.filter(parent=None, is_published=True).order_by("order", "created_at")
        return success_response(data=ResourceModuleSerializer(modules, many=True).data)


class StudentResourceModuleView(APIView):
    """
    Returns a module's published children and published sections — but ONLY
    if the entire ancestor chain from root down to this module is published.

    Publish cascade rules enforced:
      - If this module is unpublished → 404
      - If any ancestor of this module is unpublished → 404
      - Children: only those with is_published=True
      - Sections: only those with is_published=True
    """
    permission_classes = [IsStudentUser]

    def get(self, request, pk):
        module = get_object_or_404(ResourceModule, pk=pk)

        # Full ancestor-chain check (top-down cascade)
        if not _check_publish_chain(module):
            return error_response(
                message="This resource module is not available.",
                status_code=404,
            )

        # Only published items at this level
        children = ResourceModule.objects.filter(parent=module, is_published=True).order_by("order", "created_at")
        sections = ResourceSection.objects.filter(module=module, is_published=True).order_by("order", "created_at")

        return success_response(data={
            "module":   ResourceModuleSerializer(module).data,
            "children": ResourceModuleSerializer(children, many=True).data,
            "sections": ResourceSectionSerializer(sections, many=True).data,
        })


class StudentResourceSectionView(APIView):
    """
    Returns uploads for a resource section — only if the ENTIRE chain
    (all module ancestors + the module + the section itself) is published.

    Publish cascade rules enforced:
      - Section must belong to the given module
      - Section must be is_published=True
      - Module and all its ancestors must be is_published=True
    Edge cases:
      - Section exists but module chain broken → 404
      - Section exists, is published, but module is not → 404
      - Section belongs to a different module → 404 (scoped FK lookup)
    """
    permission_classes = [IsStudentUser]

    def get(self, request, module_pk, section_pk):
        module  = get_object_or_404(ResourceModule, pk=module_pk)
        section = get_object_or_404(ResourceSection, pk=section_pk, module=module)

        # Full ancestor chain check + section publish check
        if not _check_publish_chain(module) or not section.is_published:
            return error_response(
                message="This section is not available.",
                status_code=404,
            )

        uploads = ResourceUpload.objects.filter(resource_section=section).order_by("created_at")
        return success_response(data={
            "module":  ResourceModuleSerializer(module).data,
            "section": ResourceSectionSerializer(section).data,
            "uploads": ResourceUploadSerializer(uploads, many=True).data,
        })
