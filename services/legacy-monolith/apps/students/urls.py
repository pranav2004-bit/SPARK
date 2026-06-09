from django.urls import path
from .views import (
    StudentLoginView, StudentProfileView,
    StudentChangePasswordView, StudentInquiryView,
    StudentScrollView,
    StudentResourceHubView,
    StudentResourceModuleView,
    StudentResourceSectionView,
)

urlpatterns = [
    path("login/", StudentLoginView.as_view(), name="student_login"),
    path("profile/", StudentProfileView.as_view(), name="student_profile"),
    path("change-password/", StudentChangePasswordView.as_view(), name="student_change_password"),
    path("inquiries/", StudentInquiryView.as_view(), name="student_inquiry_submit"),
    path("scroll/", StudentScrollView.as_view(), name="student_scroll"),
    # Student-facing resource hub and module pages
    path("resources/", StudentResourceHubView.as_view(), name="student_resource_hub"),
    path("resources/<uuid:pk>/", StudentResourceModuleView.as_view(), name="student_resource_module"),
    path("resources/<uuid:module_pk>/sections/<uuid:section_pk>/", StudentResourceSectionView.as_view(), name="student_resource_section"),
]
