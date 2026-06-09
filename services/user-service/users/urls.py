from django.urls import path
from .views import (
    HealthView,
    BatchListCreateView, BatchDetailView, AdminBatchStudentsView,
    AdminStudentListCreateView, AdminStudentDetailView,
    AdminStudentToggleStatusView, AdminStudentBulkCreateView,
    StudentMeView,
    StudentInquiryView,
    AdminInquiryListView, AdminInquiryMarkReadView,
    AdminScrollConfigView,
    AdminScrollUpdateListCreateView, AdminScrollUpdateDetailView, AdminScrollReorderView,
    StudentScrollView,
    OutboxDeadLetterListView, OutboxDeadLetterRetryView, OutboxHealthView,
)

urlpatterns = [
    # Health
    path("health/", HealthView.as_view(), name="user-health"),

    # Student own profile
    path("me/", StudentMeView.as_view(), name="student-me"),

    # Admin: Students
    path("students/", AdminStudentListCreateView.as_view(), name="student-list-create"),
    path("students/import/", AdminStudentBulkCreateView.as_view(), name="student-bulk-create"),
    path("students/<uuid:pk>/", AdminStudentDetailView.as_view(), name="student-detail"),
    path("students/<uuid:pk>/toggle-status/", AdminStudentToggleStatusView.as_view(), name="student-toggle-status"),

    # Admin: Batches
    path("batches/", BatchListCreateView.as_view(), name="batch-list-create"),
    path("batches/<uuid:pk>/", BatchDetailView.as_view(), name="batch-detail"),
    path("batches/<uuid:batch_id>/students/", AdminBatchStudentsView.as_view(), name="batch-students"),

    # Admin: Inquiries
    path("inquiries/", AdminInquiryListView.as_view(), name="inquiry-list"),
    path("inquiries/<uuid:pk>/mark-read/", AdminInquiryMarkReadView.as_view(), name="inquiry-mark-read"),

    # Student: Inquiry submit
    path("student/inquiries/", StudentInquiryView.as_view(), name="student-inquiry"),

    # Admin: Scroll
    path("scroll/config/", AdminScrollConfigView.as_view(), name="scroll-config"),
    path("scroll/updates/", AdminScrollUpdateListCreateView.as_view(), name="scroll-updates"),
    path("scroll/updates/<uuid:pk>/", AdminScrollUpdateDetailView.as_view(), name="scroll-update-detail"),
    path("scroll/reorder/", AdminScrollReorderView.as_view(), name="scroll-reorder"),

    # Public: Scroll (AllowAny)
    path("scroll/", StudentScrollView.as_view(), name="scroll-public"),

    # Super Admin: Outbox Dead-Letter Queue
    path("admin/outbox/dead-letters/", OutboxDeadLetterListView.as_view(), name="outbox-dead-letters"),
    path("admin/outbox/dead-letters/<uuid:pk>/retry/", OutboxDeadLetterRetryView.as_view(), name="outbox-retry"),
    path("admin/outbox/health/", OutboxHealthView.as_view(), name="outbox-health"),
]
