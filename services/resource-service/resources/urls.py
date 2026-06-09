from django.urls import path
from .views import (
    HealthView,
    # Company endpoints
    CompanyListCreateView, CompanyDetailView, CompanyTogglePublishView,
    SectionListCreateView, SectionDetailView,
    UploadListView, UploadPresignedUrlView, UploadConfirmView,
    UploadAddLinkView, UploadDetailView,
    StudentCompanyListView, StudentCompanyDetailView,
    StudentSectionListView, StudentUploadListView,
    # Module endpoints (migrated from user-service)
    AdminModuleListCreateView, AdminModuleDetailView,
    AdminModuleChildrenView, AdminModuleSectionListCreateView,
    AdminModuleSectionDetailView,
    AdminModuleUploadListView, AdminModuleUploadPresignedUrlView,
    AdminModuleUploadConfirmView, AdminModuleUploadAddLinkView,
    AdminModuleUploadDetailView,
    StudentModuleHubView, StudentModuleDetailView, StudentModuleSectionView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="resource-health"),

    # ── Admin: Companies ──────────────────────────────────────────────────────
    path("companies/", CompanyListCreateView.as_view(), name="company-list-create"),
    path("companies/<uuid:company_id>/", CompanyDetailView.as_view(), name="company-detail"),
    path("companies/<uuid:company_id>/toggle-publish/", CompanyTogglePublishView.as_view(), name="company-toggle-publish"),

    # ── Admin: Company Sections ───────────────────────────────────────────────
    path("companies/<uuid:company_id>/sections/", SectionListCreateView.as_view(), name="section-list-create"),
    path("companies/<uuid:company_id>/sections/<uuid:section_id>/", SectionDetailView.as_view(), name="section-detail"),

    # ── Admin: Company Uploads ────────────────────────────────────────────────
    path("companies/<uuid:company_id>/sections/<uuid:section_id>/uploads/", UploadListView.as_view(), name="upload-list"),
    path("companies/<uuid:company_id>/sections/<uuid:section_id>/uploads/presign/", UploadPresignedUrlView.as_view(), name="upload-presign"),
    path("companies/<uuid:company_id>/sections/<uuid:section_id>/uploads/confirm/", UploadConfirmView.as_view(), name="upload-confirm"),
    path("companies/<uuid:company_id>/sections/<uuid:section_id>/uploads/add-link/", UploadAddLinkView.as_view(), name="upload-add-link"),
    path("companies/<uuid:company_id>/sections/<uuid:section_id>/uploads/<uuid:upload_id>/", UploadDetailView.as_view(), name="upload-detail"),

    # ── Student: published companies ──────────────────────────────────────────
    path("student/companies/", StudentCompanyListView.as_view(), name="student-company-list"),
    path("student/companies/<uuid:company_id>/", StudentCompanyDetailView.as_view(), name="student-company-detail"),
    path("student/companies/<uuid:company_id>/sections/", StudentSectionListView.as_view(), name="student-section-list"),
    path("student/companies/<uuid:company_id>/sections/<uuid:section_id>/uploads/", StudentUploadListView.as_view(), name="student-upload-list"),

    # ── Admin: General Modules ────────────────────────────────────────────────
    path("modules/", AdminModuleListCreateView.as_view(), name="module-list-create"),
    path("modules/<uuid:pk>/", AdminModuleDetailView.as_view(), name="module-detail"),
    path("modules/<uuid:pk>/children/", AdminModuleChildrenView.as_view(), name="module-children"),
    path("modules/<uuid:pk>/sections/", AdminModuleSectionListCreateView.as_view(), name="module-section-create"),

    # ── Admin: Module Sections ────────────────────────────────────────────────
    path("sections/<uuid:pk>/", AdminModuleSectionDetailView.as_view(), name="module-section-detail"),

    # ── Admin: Module Uploads ─────────────────────────────────────────────────
    path("modules/<uuid:module_id>/sections/<uuid:section_id>/uploads/", AdminModuleUploadListView.as_view(), name="module-upload-list"),
    path("modules/<uuid:module_id>/sections/<uuid:section_id>/presign/", AdminModuleUploadPresignedUrlView.as_view(), name="module-presign"),
    path("modules/<uuid:module_id>/sections/<uuid:section_id>/confirm/", AdminModuleUploadConfirmView.as_view(), name="module-confirm"),
    path("modules/<uuid:module_id>/sections/<uuid:section_id>/add-link/", AdminModuleUploadAddLinkView.as_view(), name="module-add-link"),
    path("modules/<uuid:module_id>/sections/<uuid:section_id>/uploads/<uuid:upload_id>/", AdminModuleUploadDetailView.as_view(), name="module-upload-detail"),

    # ── Student: General Modules (read-only) ──────────────────────────────────
    path("student/modules/", StudentModuleHubView.as_view(), name="student-module-hub"),
    path("student/modules/<uuid:pk>/", StudentModuleDetailView.as_view(), name="student-module-detail"),
    path("student/modules/<uuid:module_pk>/sections/<uuid:section_pk>/", StudentModuleSectionView.as_view(), name="student-module-section"),
]
