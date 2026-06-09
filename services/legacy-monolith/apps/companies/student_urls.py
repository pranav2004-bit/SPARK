from django.urls import path
from .views import (
    StudentCompanyListView,
    StudentCompanyDetailView,
    StudentSectionListView,
    StudentUploadListView,
)

urlpatterns = [
    # Published companies
    path("", StudentCompanyListView.as_view(), name="student_company_list"),
    path("<uuid:company_id>/", StudentCompanyDetailView.as_view(), name="student_company_detail"),

    # Sections under published company
    path("<uuid:company_id>/sections/", StudentSectionListView.as_view(), name="student_section_list"),

    # Uploads under section of published company
    path("<uuid:company_id>/sections/<uuid:section_id>/uploads/", StudentUploadListView.as_view(), name="student_upload_list"),
]
