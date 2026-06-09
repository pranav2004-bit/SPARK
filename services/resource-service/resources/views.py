import logging
from django.core.cache import cache
from django.db.models import Count
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.generics import get_object_or_404

from core.permissions import IsAdminUser, IsStudentUser
from core.pagination import StandardResultsPagination
from core.responses import success_response, error_response
from core.storage import build_file_key, generate_presigned_upload_url, is_file_type
from .models import Company, Section, Upload, Module, ModuleSection, ModuleUpload
from .serializers import (
    CompanySerializer, SectionSerializer, UploadSerializer,
    PresignedUploadRequestSerializer, ConfirmUploadSerializer, AddLinkSerializer,
    ModuleSerializer, ModuleSectionSerializer, ModuleUploadSerializer,
)

logger = logging.getLogger(__name__)

_COMPANY_CACHE_TTL = 300  # 5 minutes


def _company_cache_key(institution_id):
    return f"resources:institution:{institution_id}:companies"


def _invalidate_company_cache(institution_id):
    cache.delete(_company_cache_key(institution_id))


# ── Health ─────────────────────────────────────────────────────────────────────

class HealthView(APIView):
    permission_classes = [AllowAny]

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
            "service": "resource-service",
            "db": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
        })


# ── Helpers ────────────────────────────────────────────────────────────────────

def _company_qs(institution_id=None):
    qs = Company.objects.annotate(section_count=Count("sections")).order_by("-created_at")
    if institution_id is not None:
        qs = qs.filter(institution_id=institution_id)
    return qs


def _section_qs(company):
    return (
        Section.objects
        .select_related("company")
        .filter(company=company)
        .annotate(upload_count=Count("uploads"))
        .order_by("section_name")
    )


def _get_company(pk, institution_id, published_only=False):
    qs = _company_qs(institution_id)
    if published_only:
        qs = qs.filter(is_published=True)
    return get_object_or_404(qs, pk=pk)


def _get_section_scoped(company_id, section_id, institution_id):
    company = get_object_or_404(Company, pk=company_id, institution_id=institution_id)
    return get_object_or_404(Section, pk=section_id, company=company)


# ── Admin: Company ─────────────────────────────────────────────────────────────

class CompanyListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        cached = cache.get(_company_cache_key(institution_id))
        if cached is not None:
            data = cached
        else:
            qs = _company_qs(institution_id)
            data = list(CompanySerializer(qs, many=True).data)
            cache.set(_company_cache_key(institution_id), data, _COMPANY_CACHE_TTL)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response(page)

    def post(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        serializer = CompanySerializer(data=request.data, context={"institution_id": institution_id})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        company = serializer.save(institution_id=institution_id)
        _invalidate_company_cache(institution_id)
        return success_response(
            data=CompanySerializer(_company_qs(institution_id).get(pk=company.pk)).data,
            message="Company created successfully",
            status_code=201,
        )


class CompanyDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, company_id):
        institution_id = getattr(request.user, "institution_id", None)
        return success_response(data=CompanySerializer(_get_company(company_id, institution_id)).data)

    def put(self, request, company_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = _get_company(company_id, institution_id)
        serializer = CompanySerializer(company, data=request.data, context={"institution_id": institution_id})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        _invalidate_company_cache(institution_id)
        return success_response(data=CompanySerializer(_get_company(company_id, institution_id)).data, message="Company updated")

    def patch(self, request, company_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = _get_company(company_id, institution_id)
        serializer = CompanySerializer(company, data=request.data, partial=True, context={"institution_id": institution_id})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        _invalidate_company_cache(institution_id)
        return success_response(data=CompanySerializer(_get_company(company_id, institution_id)).data, message="Company updated")

    def delete(self, request, company_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = get_object_or_404(Company, pk=company_id, institution_id=institution_id)
        if company.sections.exists():
            return error_response(
                message="Cannot delete a company that has sections. Remove all sections first.",
                status_code=400,
            )
        company.delete()
        _invalidate_company_cache(institution_id)
        return success_response(message="Company deleted successfully")


class CompanyTogglePublishView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, company_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = get_object_or_404(Company, pk=company_id, institution_id=institution_id)
        company.is_published = not company.is_published
        company.save(update_fields=["is_published"])
        _invalidate_company_cache(institution_id)
        return success_response(
            data=CompanySerializer(_company_qs(institution_id).get(pk=company.pk)).data,
            message=f"Company {'published' if company.is_published else 'unpublished'} successfully",
        )


# ── Admin: Section ─────────────────────────────────────────────────────────────

class SectionListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, company_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = get_object_or_404(Company, pk=company_id, institution_id=institution_id)
        qs = _section_qs(company)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(SectionSerializer(page, many=True).data)

    def post(self, request, company_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = get_object_or_404(Company, pk=company_id, institution_id=institution_id)
        serializer = SectionSerializer(data=request.data, context={"company": company})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        section = serializer.save(company=company)
        _invalidate_company_cache(institution_id)
        return success_response(
            data=SectionSerializer(_section_qs(company).get(pk=section.pk)).data,
            status_code=201,
            message="Section created successfully",
        )


class SectionDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, company_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = get_object_or_404(Company, pk=company_id, institution_id=institution_id)
        section = get_object_or_404(_section_qs(company), pk=section_id)
        return success_response(data=SectionSerializer(section).data)

    def put(self, request, company_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = get_object_or_404(Company, pk=company_id, institution_id=institution_id)
        section = get_object_or_404(Section, pk=section_id, company=company)
        serializer = SectionSerializer(section, data=request.data, context={"company": company})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(
            data=SectionSerializer(get_object_or_404(_section_qs(company), pk=section_id)).data,
            message="Section updated",
        )

    def patch(self, request, company_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = get_object_or_404(Company, pk=company_id, institution_id=institution_id)
        section = get_object_or_404(Section, pk=section_id, company=company)
        serializer = SectionSerializer(section, data=request.data, partial=True, context={"company": company})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(
            data=SectionSerializer(get_object_or_404(_section_qs(company), pk=section_id)).data,
            message="Section updated",
        )

    def delete(self, request, company_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = get_object_or_404(Company, pk=company_id, institution_id=institution_id)
        section = get_object_or_404(Section, pk=section_id, company=company)
        if section.uploads.exists():
            return error_response(message="Cannot delete section with uploads. Remove uploads first.", status_code=400)
        section.delete()
        _invalidate_company_cache(institution_id)
        return success_response(message="Section deleted successfully")


# ── Admin: Uploads ─────────────────────────────────────────────────────────────

class UploadListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, company_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        section = _get_section_scoped(company_id, section_id, institution_id)
        uploads = Upload.objects.filter(section=section).order_by("-created_at")
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(uploads, request)
        return paginator.get_paginated_response(UploadSerializer(page, many=True).data)


class UploadPresignedUrlView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, company_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        _get_section_scoped(company_id, section_id, institution_id)
        serializer = PresignedUploadRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        filename = serializer.validated_data["filename"]
        content_type = serializer.validated_data["content_type"]
        upload_type = serializer.validated_data["upload_type"]
        file_key = build_file_key(upload_type, filename)
        try:
            upload_url = generate_presigned_upload_url(file_key, content_type)
        except RuntimeError as exc:
            logger.error("R2 not configured: %s", exc)
            return error_response(message="File storage is not configured.", status_code=503)
        return success_response(data={"upload_url": upload_url, "file_key": file_key})


class UploadConfirmView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, company_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        section = _get_section_scoped(company_id, section_id, institution_id)
        serializer = ConfirmUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        upload = Upload.objects.create(
            section=section,
            upload_type=serializer.validated_data["upload_type"],
            file_url=serializer.validated_data["file_key"],
            original_filename=serializer.validated_data["original_filename"],
            file_size_bytes=serializer.validated_data["file_size_bytes"],
        )
        _invalidate_company_cache(institution_id)
        return success_response(data=UploadSerializer(upload).data, status_code=201, message="Upload confirmed")


class UploadAddLinkView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, company_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        section = _get_section_scoped(company_id, section_id, institution_id)
        serializer = AddLinkSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        upload = Upload.objects.create(
            section=section,
            upload_type=serializer.validated_data["upload_type"],
            file_url=serializer.validated_data["file_url"],
        )
        return success_response(data=UploadSerializer(upload).data, status_code=201, message="Link added")


class UploadDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, company_id, section_id, upload_id):
        institution_id = getattr(request.user, "institution_id", None)
        section = _get_section_scoped(company_id, section_id, institution_id)
        upload = get_object_or_404(Upload, pk=upload_id, section=section)
        name = (request.data.get("original_filename") or "").strip()
        if not name:
            return error_response(message="Name cannot be empty.", status_code=400)
        if len(name) > 500:
            return error_response(message="Name is too long. Maximum 500 characters.", status_code=400)
        upload.original_filename = name
        upload.save(update_fields=["original_filename"])
        return success_response(data=UploadSerializer(upload).data, message="Upload renamed")

    def delete(self, request, company_id, section_id, upload_id):
        institution_id = getattr(request.user, "institution_id", None)
        section = _get_section_scoped(company_id, section_id, institution_id)
        upload = get_object_or_404(Upload, pk=upload_id, section=section)
        file_key = upload.file_url
        upload_type = upload.upload_type
        upload.delete()
        _invalidate_company_cache(institution_id)
        if is_file_type(upload_type):
            from .tasks import async_delete_file
            async_delete_file.delay(file_key)
        return success_response(message="Upload deleted successfully")


# ── Student: Company (published only, institution-scoped) ─────────────────────

class StudentCompanyListView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        qs = _company_qs(institution_id).filter(is_published=True)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(CompanySerializer(page, many=True).data)


class StudentCompanyDetailView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request, company_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = _get_company(company_id, institution_id, published_only=True)
        return success_response(data=CompanySerializer(company).data)


class StudentSectionListView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request, company_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = get_object_or_404(Company, pk=company_id, institution_id=institution_id, is_published=True)
        qs = _section_qs(company)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(SectionSerializer(page, many=True).data)


class StudentUploadListView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request, company_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        company = get_object_or_404(Company, pk=company_id, institution_id=institution_id, is_published=True)
        section = get_object_or_404(Section, pk=section_id, company=company)
        uploads = Upload.objects.filter(section=section).order_by("-created_at")
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(uploads, request)
        return paginator.get_paginated_response(UploadSerializer(page, many=True).data)


# ── General Modules (migrated from user-service) ───────────────────────────────

def _ensure_system_module(institution_id):
    """
    Guarantee exactly one system Module exists for this institution.
    Uses filter+deduplicate instead of get_or_create to avoid
    MultipleObjectsReturned under concurrent requests.
    """
    qs = Module.objects.filter(is_system=True, institution_id=institution_id).order_by("created_at")
    count = qs.count()
    if count == 0:
        Module.objects.create(
            name="Company Resources",
            is_system=True,
            is_published=True,
            order=0,
            institution_id=institution_id,
        )
    else:
        obj = qs.first()
        if count > 1:
            qs.exclude(pk=obj.pk).delete()
        if obj.name in ("Company Resourcess", "CompanyResources", "company resources"):
            obj.name = "Company Resources"
            obj.save(update_fields=["name"])


def _check_publish_chain(module):
    current = module
    while current is not None:
        if not current.is_published:
            return False
        current = current.parent
    return True


def _get_scoped_module_section(institution_id, module_id, section_id):
    module = get_object_or_404(Module, pk=module_id, institution_id=institution_id)
    return get_object_or_404(ModuleSection, pk=section_id, module=module)


# ── Admin: Module ──────────────────────────────────────────────────────────────

class AdminModuleListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        _ensure_system_module(institution_id)
        modules = Module.objects.filter(parent=None, institution_id=institution_id)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(modules, request)
        return paginator.get_paginated_response(ModuleSerializer(page, many=True).data)

    def post(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        serializer = ModuleSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        from django.db.models import Max
        max_order = Module.objects.filter(institution_id=institution_id).aggregate(m=Max("order"))["m"] or 0
        serializer.save(order=max_order + 1, is_system=False, institution_id=institution_id)
        return success_response(data=serializer.data, status_code=201, message="Module created.")


class AdminModuleDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk, institution_id):
        return get_object_or_404(Module, pk=pk, institution_id=institution_id)

    def get(self, request, pk):
        institution_id = getattr(request.user, "institution_id", None)
        module = self._get(pk, institution_id)
        children = Module.objects.filter(parent=module)
        sections = ModuleSection.objects.filter(module=module)
        return success_response(data={
            "module":   ModuleSerializer(module).data,
            "children": ModuleSerializer(children, many=True).data,
            "sections": ModuleSectionSerializer(sections, many=True).data,
        })

    def patch(self, request, pk):
        institution_id = getattr(request.user, "institution_id", None)
        module = self._get(pk, institution_id)
        serializer = ModuleSerializer(module, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(data=serializer.data, message="Module updated.")

    def delete(self, request, pk):
        institution_id = getattr(request.user, "institution_id", None)
        module = self._get(pk, institution_id)
        if module.is_system:
            return error_response(message="The system module cannot be deleted.", status_code=403)
        module.delete()
        return success_response(message="Module deleted.")


class AdminModuleChildrenView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        institution_id = getattr(request.user, "institution_id", None)
        parent = get_object_or_404(Module, pk=pk, institution_id=institution_id)
        serializer = ModuleSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        from django.db.models import Max
        max_order = Module.objects.filter(parent=parent).aggregate(m=Max("order"))["m"] or 0
        serializer.save(parent=parent, order=max_order + 1, is_system=False, institution_id=institution_id)
        return success_response(data=serializer.data, status_code=201, message="Sub-module created.")


class AdminModuleSectionListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        institution_id = getattr(request.user, "institution_id", None)
        module = get_object_or_404(Module, pk=pk, institution_id=institution_id)
        serializer = ModuleSectionSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        from django.db.models import Max
        max_order = ModuleSection.objects.filter(module=module).aggregate(m=Max("order"))["m"] or 0
        serializer.save(module=module, order=max_order + 1)
        return success_response(data=serializer.data, status_code=201, message="Section created.")


class AdminModuleSectionDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get(self, pk, institution_id):
        return get_object_or_404(
            ModuleSection.objects.select_related("module"),
            pk=pk,
            module__institution_id=institution_id,
        )

    def patch(self, request, pk):
        institution_id = getattr(request.user, "institution_id", None)
        section = self._get(pk, institution_id)
        serializer = ModuleSectionSerializer(section, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(data=serializer.data, message="Section updated.")

    def delete(self, request, pk):
        institution_id = getattr(request.user, "institution_id", None)
        section = self._get(pk, institution_id)
        if section.uploads.exists():
            return error_response(
                message="Cannot delete section with uploads. Remove uploads first.",
                status_code=400,
            )
        section.delete()
        return success_response(message="Section deleted.")


# ── Admin: Module Uploads ──────────────────────────────────────────────────────

class AdminModuleUploadListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, module_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        section = _get_scoped_module_section(institution_id, module_id, section_id)
        uploads = ModuleUpload.objects.filter(section=section).order_by("-created_at")
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(uploads, request)
        return paginator.get_paginated_response(ModuleUploadSerializer(page, many=True).data)


class AdminModuleUploadPresignedUrlView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, module_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        _get_scoped_module_section(institution_id, module_id, section_id)
        serializer = PresignedUploadRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        filename = serializer.validated_data["filename"]
        content_type = serializer.validated_data["content_type"]
        upload_type = serializer.validated_data["upload_type"]
        file_key = build_file_key(upload_type, filename)
        try:
            upload_url = generate_presigned_upload_url(file_key, content_type)
        except RuntimeError as exc:
            logger.error("Storage not configured: %s", exc)
            return error_response(message="File storage is not configured.", status_code=503)
        return success_response(data={"upload_url": upload_url, "file_key": file_key})


class AdminModuleUploadConfirmView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, module_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        section = _get_scoped_module_section(institution_id, module_id, section_id)
        serializer = ConfirmUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        upload = ModuleUpload.objects.create(
            section=section,
            upload_type=serializer.validated_data["upload_type"],
            file_url=serializer.validated_data["file_key"],
            original_filename=serializer.validated_data["original_filename"],
            file_size_bytes=serializer.validated_data["file_size_bytes"],
        )
        return success_response(data=ModuleUploadSerializer(upload).data, status_code=201, message="Upload confirmed.")


class AdminModuleUploadAddLinkView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, module_id, section_id):
        institution_id = getattr(request.user, "institution_id", None)
        section = _get_scoped_module_section(institution_id, module_id, section_id)
        serializer = AddLinkSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        upload = ModuleUpload.objects.create(
            section=section,
            upload_type=serializer.validated_data["upload_type"],
            file_url=serializer.validated_data["file_url"],
        )
        return success_response(data=ModuleUploadSerializer(upload).data, status_code=201, message="Link added.")


class AdminModuleUploadDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, module_id, section_id, upload_id):
        institution_id = getattr(request.user, "institution_id", None)
        section = _get_scoped_module_section(institution_id, module_id, section_id)
        upload = get_object_or_404(ModuleUpload, pk=upload_id, section=section)
        name = (request.data.get("original_filename") or "").strip()
        if not name:
            return error_response(message="Name cannot be empty.", status_code=400)
        if len(name) > 500:
            return error_response(message="Name is too long. Maximum 500 characters.", status_code=400)
        upload.original_filename = name
        upload.save(update_fields=["original_filename"])
        return success_response(data=ModuleUploadSerializer(upload).data, message="Upload renamed.")

    def delete(self, request, module_id, section_id, upload_id):
        institution_id = getattr(request.user, "institution_id", None)
        section = _get_scoped_module_section(institution_id, module_id, section_id)
        upload = get_object_or_404(ModuleUpload, pk=upload_id, section=section)
        file_key = upload.file_url
        upload_type = upload.upload_type
        upload.delete()
        if is_file_type(upload_type):
            from .tasks import async_delete_file
            async_delete_file.delay(file_key)
        return success_response(message="Upload deleted successfully.")


# ── Student: Module (read-only) ────────────────────────────────────────────────

class StudentModuleHubView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request):
        institution_id = getattr(request.user, "institution_id", None)
        modules = Module.objects.filter(
            parent=None, is_published=True, institution_id=institution_id
        ).order_by("order", "created_at")
        return success_response(data=ModuleSerializer(modules, many=True).data)


class StudentModuleDetailView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request, pk):
        institution_id = getattr(request.user, "institution_id", None)
        module = get_object_or_404(Module, pk=pk, institution_id=institution_id)
        if not _check_publish_chain(module):
            return error_response(message="This resource module is not available.", status_code=404)
        children = Module.objects.filter(parent=module, is_published=True).order_by("order", "created_at")
        sections = ModuleSection.objects.filter(module=module, is_published=True).order_by("order", "created_at")
        return success_response(data={
            "module":   ModuleSerializer(module).data,
            "children": ModuleSerializer(children, many=True).data,
            "sections": ModuleSectionSerializer(sections, many=True).data,
        })


class StudentModuleSectionView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request, module_pk, section_pk):
        institution_id = getattr(request.user, "institution_id", None)
        module = get_object_or_404(Module, pk=module_pk, institution_id=institution_id)
        section = get_object_or_404(ModuleSection, pk=section_pk, module=module)
        if not _check_publish_chain(module) or not section.is_published:
            return error_response(message="This section is not available.", status_code=404)
        uploads = ModuleUpload.objects.filter(section=section).order_by("created_at")
        return success_response(data={
            "module":  ModuleSerializer(module).data,
            "section": ModuleSectionSerializer(section).data,
            "uploads": ModuleUploadSerializer(uploads, many=True).data,
        })
