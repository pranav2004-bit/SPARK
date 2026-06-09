from django.urls import path
from .views import (
    AdminStudentListCreateView,
    AdminStudentDetailView,
    AdminStudentToggleStatusView,
    AdminStudentResetPasswordView,
    AdminStudentBulkCreateView,
    AdminInquiryListView,
    AdminInquiryMarkReadView,
    AdminScrollConfigView,
    AdminScrollUpdateListCreateView,
    AdminScrollUpdateDetailView,
    AdminScrollReorderView,
    AdminResourceModuleListCreateView,
    AdminResourceModuleDetailView,
    AdminResourceModuleChildrenView,
    AdminResourceSectionListCreateView,
    AdminResourceSectionDetailView,
    AdminResourceUploadListView,
    AdminResourceUploadPresignedUrlView,
    AdminResourceUploadConfirmView,
    AdminResourceUploadAddLinkView,
    AdminResourceUploadDetailView,
)

urlpatterns = [
    path("", AdminStudentListCreateView.as_view(), name="admin_student_list_create"),
    path("bulk-create/", AdminStudentBulkCreateView.as_view(), name="admin_student_bulk_create"),
    path("<uuid:pk>/", AdminStudentDetailView.as_view(), name="admin_student_detail"),
    path("<uuid:pk>/toggle-status/", AdminStudentToggleStatusView.as_view(), name="admin_student_toggle"),
    path("<uuid:pk>/reset-password/", AdminStudentResetPasswordView.as_view(), name="admin_student_reset_password"),
    path("inquiries/", AdminInquiryListView.as_view(), name="admin_inquiry_list"),
    path("inquiries/<uuid:pk>/mark-read/", AdminInquiryMarkReadView.as_view(), name="admin_inquiry_mark_read"),
    # Scroll updates
    path("scroll/config/", AdminScrollConfigView.as_view(), name="admin_scroll_config"),
    path("scroll/updates/", AdminScrollUpdateListCreateView.as_view(), name="admin_scroll_update_list_create"),
    path("scroll/updates/<uuid:pk>/", AdminScrollUpdateDetailView.as_view(), name="admin_scroll_update_detail"),
    path("scroll/updates/reorder/", AdminScrollReorderView.as_view(), name="admin_scroll_reorder"),
    # Resource modules (hub-level)
    path("resource-modules/", AdminResourceModuleListCreateView.as_view(), name="admin_resource_module_list_create"),
    path("resource-modules/<uuid:pk>/", AdminResourceModuleDetailView.as_view(), name="admin_resource_module_detail"),
    # Sub-modules under a module
    path("resource-modules/<uuid:pk>/children/", AdminResourceModuleChildrenView.as_view(), name="admin_resource_module_children"),
    # Sections under a module
    path("resource-modules/<uuid:pk>/sections/", AdminResourceSectionListCreateView.as_view(), name="admin_resource_section_list_create"),
    path("resource-sections/<uuid:pk>/", AdminResourceSectionDetailView.as_view(), name="admin_resource_section_detail"),
    # Uploads under a resource section
    path("resource-modules/<uuid:module_id>/sections/<uuid:section_id>/uploads/", AdminResourceUploadListView.as_view(), name="admin_resource_upload_list"),
    path("resource-modules/<uuid:module_id>/sections/<uuid:section_id>/uploads/get-upload-url/", AdminResourceUploadPresignedUrlView.as_view(), name="admin_resource_upload_presigned"),
    path("resource-modules/<uuid:module_id>/sections/<uuid:section_id>/uploads/confirm/", AdminResourceUploadConfirmView.as_view(), name="admin_resource_upload_confirm"),
    path("resource-modules/<uuid:module_id>/sections/<uuid:section_id>/uploads/add-link/", AdminResourceUploadAddLinkView.as_view(), name="admin_resource_upload_add_link"),
    path("resource-modules/<uuid:module_id>/sections/<uuid:section_id>/uploads/<uuid:upload_id>/", AdminResourceUploadDetailView.as_view(), name="admin_resource_upload_detail"),
]
