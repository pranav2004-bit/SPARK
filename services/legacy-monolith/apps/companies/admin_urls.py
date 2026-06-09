from django.urls import path
from .views import (
    CompanyListCreateView,
    CompanyDetailView,
    CompanyTogglePublishView,
    SectionListCreateView,
    SectionDetailView,
    UploadListView,
    UploadPresignedUrlView,
    UploadConfirmView,
    UploadAddLinkView,
    UploadDeleteView,
)

urlpatterns = [
    # Company CRUD
    path("", CompanyListCreateView.as_view(), name="admin_company_list_create"),
    path("<uuid:company_id>/", CompanyDetailView.as_view(), name="admin_company_detail"),
    path("<uuid:company_id>/toggle-publish/", CompanyTogglePublishView.as_view(), name="admin_company_toggle_publish"),

    # Sections under a company
    path("<uuid:company_id>/sections/", SectionListCreateView.as_view(), name="admin_section_list_create"),
    path("<uuid:company_id>/sections/<uuid:section_id>/", SectionDetailView.as_view(), name="admin_section_detail"),

    # Uploads under a section
    path("<uuid:company_id>/sections/<uuid:section_id>/uploads/", UploadListView.as_view(), name="admin_upload_list"),
    path("<uuid:company_id>/sections/<uuid:section_id>/uploads/get-upload-url/", UploadPresignedUrlView.as_view(), name="admin_upload_presigned_url"),
    path("<uuid:company_id>/sections/<uuid:section_id>/uploads/confirm/", UploadConfirmView.as_view(), name="admin_upload_confirm"),
    path("<uuid:company_id>/sections/<uuid:section_id>/uploads/add-link/", UploadAddLinkView.as_view(), name="admin_upload_add_link"),
    path("<uuid:company_id>/sections/<uuid:section_id>/uploads/<uuid:upload_id>/", UploadDeleteView.as_view(), name="admin_upload_delete"),
]
