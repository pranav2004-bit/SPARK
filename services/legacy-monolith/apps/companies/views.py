import logging
from django.db.models import Count
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404

from core.permissions import IsAdminUser, IsStudentUser
from core.pagination import StandardResultsPagination
from core.responses import success_response, error_response
from core.storage import build_file_key, generate_presigned_upload_url, is_file_type
from .models import Company, Section, Upload
from .serializers import (
    CompanySerializer,
    SectionSerializer,
    UploadSerializer,
    PresignedUploadRequestSerializer,
    ConfirmUploadSerializer,
    AddLinkSerializer,
)
from .tasks import async_delete_file

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _company_qs():
    return Company.objects.annotate(section_count=Count("sections")).order_by("-created_at")


def _section_qs(company):
    return Section.objects.filter(company=company).annotate(upload_count=Count("uploads")).order_by("section_name")


def _get_company(pk, published_only=False):
    qs = _company_qs()
    if published_only:
        qs = qs.filter(is_published=True)
    return get_object_or_404(qs, pk=pk)


def _get_section(company, section_id):
    return get_object_or_404(_section_qs(company), pk=section_id)


def _get_section_scoped(company_id, section_id):
    """Return section ensuring it belongs to the given company."""
    company = get_object_or_404(Company, pk=company_id)
    return get_object_or_404(Section, pk=section_id, company=company)


# ── Admin: Company ─────────────────────────────────────────────────────────────

class CompanyListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = _company_qs()
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(CompanySerializer(page, many=True).data)

    def post(self, request):
        serializer = CompanySerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        company = serializer.save()
        return success_response(
            data=CompanySerializer(_company_qs().get(pk=company.pk)).data,
            message="Company created successfully",
            status_code=201,
        )


class CompanyDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, company_id):
        return success_response(data=CompanySerializer(_get_company(company_id)).data)

    def put(self, request, company_id):
        company = _get_company(company_id)
        serializer = CompanySerializer(company, data=request.data, partial=False)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(
            data=CompanySerializer(_get_company(company_id)).data,
            message="Company updated successfully",
        )

    def patch(self, request, company_id):
        company = _get_company(company_id)
        serializer = CompanySerializer(company, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(
            data=CompanySerializer(_get_company(company_id)).data,
            message="Company updated successfully",
        )

    def delete(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id)
        if company.sections.exists():
            return error_response(
                message="Cannot delete a company that has sections. Remove all sections first.",
                status_code=400,
            )
        company.delete()
        return success_response(message="Company deleted successfully")


class CompanyTogglePublishView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id)
        company.is_published = not company.is_published
        company.save(update_fields=["is_published"])
        return success_response(
            data=CompanySerializer(_company_qs().get(pk=company.pk)).data,
            message=f"Company {'published' if company.is_published else 'unpublished'} successfully",
        )


# ── Admin: Section ─────────────────────────────────────────────────────────────

class SectionListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id)
        qs = _section_qs(company)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(SectionSerializer(page, many=True).data)

    def post(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id)
        serializer = SectionSerializer(data=request.data, context={"company": company})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        section = serializer.save(company=company)
        return success_response(
            data=SectionSerializer(_section_qs(company).get(pk=section.pk)).data,
            message="Section created successfully",
            status_code=201,
        )


class SectionDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, company_id, section_id):
        company = get_object_or_404(Company, pk=company_id)
        section = _get_section(company, section_id)
        return success_response(data=SectionSerializer(section).data)

    def put(self, request, company_id, section_id):
        company = get_object_or_404(Company, pk=company_id)
        section = _get_section(company, section_id)
        serializer = SectionSerializer(section, data=request.data, partial=False, context={"company": company})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(
            data=SectionSerializer(_get_section(company, section_id)).data,
            message="Section updated successfully",
        )

    def patch(self, request, company_id, section_id):
        company = get_object_or_404(Company, pk=company_id)
        section = _get_section(company, section_id)
        serializer = SectionSerializer(section, data=request.data, partial=True, context={"company": company})
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)
        serializer.save()
        return success_response(
            data=SectionSerializer(_get_section(company, section_id)).data,
            message="Section updated successfully",
        )

    def delete(self, request, company_id, section_id):
        company = get_object_or_404(Company, pk=company_id)
        section = get_object_or_404(Section, pk=section_id, company=company)
        if section.uploads.exists():
            return error_response(
                message="Cannot delete a section that has uploads. Remove all uploads first.",
                status_code=400,
            )
        section.delete()
        return success_response(message="Section deleted successfully")


# ── Admin: Uploads ─────────────────────────────────────────────────────────────

class UploadListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, company_id, section_id):
        section = _get_section_scoped(company_id, section_id)
        uploads = Upload.objects.filter(section=section).order_by("-created_at")
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(uploads, request)
        return paginator.get_paginated_response(UploadSerializer(page, many=True).data)


class UploadPresignedUrlView(APIView):
    """
    Step 1 of the R2 upload flow.

    Validates file metadata and returns:
      - upload_url: presigned S3 PUT URL (expires in R2_PRESIGNED_URL_EXPIRY seconds)
      - file_key:   the R2 object key to pass back in the confirm step

    The browser PUTs the binary file directly to R2 — the backend never
    handles the file body, keeping the API server free for 20,000+ users.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, company_id, section_id):
        _get_section_scoped(company_id, section_id)  # validates ownership
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
            return error_response(
                message="File storage is not configured. Contact the administrator.",
                status_code=503,
            )

        return success_response(
            data={"upload_url": upload_url, "file_key": file_key},
            message="Presigned upload URL generated. PUT your file to upload_url, then call confirm.",
        )


class UploadConfirmView(APIView):
    """
    Step 2 of the R2 upload flow.

    Called after the browser has successfully PUT the file to R2.
    Creates the Upload database record.
    The read_url in the response is a Cloudflare CDN URL — no expiry,
    edge-cached globally.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, company_id, section_id):
        section = _get_section_scoped(company_id, section_id)
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
        return success_response(
            data=UploadSerializer(upload).data,
            message="Upload confirmed successfully",
            status_code=201,
        )


class UploadAddLinkView(APIView):
    """Add an external link or video link as an upload record (no R2 storage)."""
    permission_classes = [IsAdminUser]

    def post(self, request, company_id, section_id):
        section = _get_section_scoped(company_id, section_id)
        serializer = AddLinkSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors, status_code=400)

        upload = Upload.objects.create(
            section=section,
            upload_type=serializer.validated_data["upload_type"],
            file_url=serializer.validated_data["file_url"],
            original_filename=None,
            file_size_bytes=None,
        )
        return success_response(
            data=UploadSerializer(upload).data,
            message="Link added successfully",
            status_code=201,
        )


class UploadDeleteView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, company_id, section_id, upload_id):
        """Rename an upload's display name (original_filename).

        No uniqueness constraint — the same name may appear across sections
        and companies. Only the display label is changed; the stored file/URL
        is never touched.
        """
        section = _get_section_scoped(company_id, section_id)
        upload = get_object_or_404(Upload, pk=upload_id, section=section)

        name = (request.data.get("original_filename") or "").strip()
        if not name:
            return error_response(
                message="Name cannot be empty.",
                status_code=400,
            )
        if len(name) > 500:
            return error_response(
                message="Name is too long. Maximum 500 characters.",
                status_code=400,
            )

        upload.original_filename = name
        upload.save(update_fields=["original_filename"])
        return success_response(
            data=UploadSerializer(upload).data,
            message="Upload renamed successfully",
        )

    def delete(self, request, company_id, section_id, upload_id):
        section = _get_section_scoped(company_id, section_id)
        upload = get_object_or_404(Upload, pk=upload_id, section=section)

        file_key = upload.file_url
        upload_type = upload.upload_type
        upload.delete()

        # Queue async R2 deletion — only for physical files, not links
        if is_file_type(upload_type):
            async_delete_file.delay(file_key)
            logger.info("Queued R2 deletion for key=%s", file_key)

        return success_response(message="Upload deleted successfully")


# ── Student: Company (published only) ─────────────────────────────────────────

class StudentCompanyListView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request):
        qs = _company_qs().filter(is_published=True)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(CompanySerializer(page, many=True).data)


class StudentCompanyDetailView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request, company_id):
        return success_response(data=CompanySerializer(_get_company(company_id, published_only=True)).data)


# ── Student: Section (under published company) ────────────────────────────────

class StudentSectionListView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request, company_id):
        company = get_object_or_404(Company, pk=company_id, is_published=True)
        qs = _section_qs(company)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(SectionSerializer(page, many=True).data)


# ── Student: Uploads (under published company's section) ──────────────────────

class StudentUploadListView(APIView):
    permission_classes = [IsStudentUser]

    def get(self, request, company_id, section_id):
        company = get_object_or_404(Company, pk=company_id, is_published=True)
        section = get_object_or_404(Section, pk=section_id, company=company)
        uploads = Upload.objects.filter(section=section).order_by("-created_at")
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(uploads, request)
        return paginator.get_paginated_response(UploadSerializer(page, many=True).data)
