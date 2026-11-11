from django.urls import path
from .views import (
    HealthView,
    AdminPaperListCreateView,
    AdminPaperDetailView,
    AdminPaperSetsView,
    AdminSetDetailView,
    AdminSetQuestionView,
    AdminQuestionDetailView,
    AdminEssayAssignmentListCreateView,
    AdminEssayAssignmentDetailView,
    AdminEssayAssignmentStartView,
    AdminEssayAssignmentCloseView,
    AdminEssayAssignmentResyncRosterView,
    StudentEssayServerTimeView,
    StudentEssayAssignmentListView,
    StudentEssayAttemptStartView,
    StudentEssayAttemptDetailView,
    StudentEssayAutosaveView,
    StudentEssaySubmitView,
    StudentEssayMalpracticeEventBulkCreateView,
    AdminSubmissionsOverviewView,
    AdminSubmissionsListView,
    AdminSubmissionDetailView,
    AdminSubmissionsPipelineHealthView,
    AdminSubmissionRetriggerView,
    AdminSubmissionTraceView,
    AdminLLMAnalyticsView,
    AdminSubmissionScoreOverrideView,
    AdminEssayAssignmentResultsView,
    AdminEssayAssignmentResultsExportView,
    AdminSubmissionGeneralScoreOverrideView,
    AdminEssayAssignmentAnalyticsView,
    AdminEssayAssignmentDashboardView,
    AdminAssignmentReportListView,
    AdminReportRegenerateView,
    AdminSubmissionReportResendView,
    AdminAssignmentReportBulkResendView,
    AdminAssignmentReportBulkDownloadView,
    AdminDLQListView,
    AdminDLQDetailView,
    AdminDLQRetryView,
    AdminDLQResolveView,
    AdminDLQBulkRetryView,
    AdminPipelineHealthSummaryView,
    AdminSendDailySummaryView,
    StudentEssayResultsView,
)

urlpatterns = [
    # Health
    path("health/", HealthView.as_view(), name="health"),

    # Admin — Question Bank (Phase 2)
    path("admin/papers/",                AdminPaperListCreateView.as_view(), name="admin_paper_list_create"),
    path("admin/papers/<uuid:pk>/",      AdminPaperDetailView.as_view(),     name="admin_paper_detail"),
    path("admin/papers/<uuid:pk>/sets/", AdminPaperSetsView.as_view(),      name="admin_paper_sets"),
    path("admin/sets/<uuid:pk>/",        AdminSetDetailView.as_view(),      name="admin_set_detail"),
    path("admin/sets/<uuid:pk>/question/", AdminSetQuestionView.as_view(),  name="admin_set_question"),
    path("admin/questions/<uuid:pk>/",   AdminQuestionDetailView.as_view(), name="admin_question_detail"),

    # Admin — Assessment Assign (Phase 3)
    path("admin/assignments/",                    AdminEssayAssignmentListCreateView.as_view(), name="admin_assignment_list_create"),
    path("admin/assignments/<uuid:pk>/",          AdminEssayAssignmentDetailView.as_view(),      name="admin_assignment_detail"),
    path("admin/assignments/<uuid:pk>/start/",    AdminEssayAssignmentStartView.as_view(),       name="admin_assignment_start"),
    path("admin/assignments/<uuid:pk>/close/",    AdminEssayAssignmentCloseView.as_view(),       name="admin_assignment_close"),
    path("admin/assignments/<uuid:pk>/resync-roster/", AdminEssayAssignmentResyncRosterView.as_view(), name="admin_assignment_resync_roster"),

    # Student — Essay-Writing Exam Experience (Phase 4)
    path("student/server-time/",                     StudentEssayServerTimeView.as_view(),    name="student_server_time"),
    path("student/assignments/",                     StudentEssayAssignmentListView.as_view(), name="student_assignment_list"),
    path("student/assignments/<uuid:pk>/start-attempt/", StudentEssayAttemptStartView.as_view(), name="student_attempt_start"),
    path("student/attempts/<uuid:pk>/",              StudentEssayAttemptDetailView.as_view(),  name="student_attempt_detail"),
    path("student/attempts/<uuid:pk>/autosave/",     StudentEssayAutosaveView.as_view(),       name="student_attempt_autosave"),
    path("student/attempts/<uuid:pk>/submit/",       StudentEssaySubmitView.as_view(),         name="student_attempt_submit"),
    path("student/attempts/<uuid:pk>/malpractice-events/", StudentEssayMalpracticeEventBulkCreateView.as_view(), name="student_attempt_malpractice_events"),

    # Admin — Submissions Module (Phase 6)
    path("admin/submissions/overview/",        AdminSubmissionsOverviewView.as_view(),      name="admin_submissions_overview"),
    path("admin/submissions/pipeline-health/", AdminSubmissionsPipelineHealthView.as_view(), name="admin_submissions_pipeline_health"),
    path("admin/submissions/",                 AdminSubmissionsListView.as_view(),          name="admin_submissions_list"),
    path("admin/submissions/<uuid:pk>/",       AdminSubmissionDetailView.as_view(),         name="admin_submission_detail"),

    # Admin — LLM Controls Module (Phase 7)
    path("admin/llm-controls/analytics/",              AdminLLMAnalyticsView.as_view(),          name="admin_llm_analytics"),
    path("admin/submissions/<uuid:pk>/retrigger/",      AdminSubmissionRetriggerView.as_view(),   name="admin_submission_retrigger"),
    path("admin/submissions/<uuid:pk>/trace/",          AdminSubmissionTraceView.as_view(),       name="admin_submission_trace"),
    path("admin/submissions/<uuid:pk>/override-score/", AdminSubmissionScoreOverrideView.as_view(), name="admin_submission_override_score"),

    # Admin — Results Module (Phase 8)
    path("admin/assignments/<uuid:pk>/results/",        AdminEssayAssignmentResultsView.as_view(),       name="admin_assignment_results"),
    path("admin/assignments/<uuid:pk>/results/export/",  AdminEssayAssignmentResultsExportView.as_view(), name="admin_assignment_results_export"),
    path("admin/submissions/<uuid:pk>/general-override-score/", AdminSubmissionGeneralScoreOverrideView.as_view(), name="admin_submission_general_override_score"),

    # Admin — Analytics Module (Phase 9)
    path("admin/assignments/<uuid:pk>/analytics/", AdminEssayAssignmentAnalyticsView.as_view(), name="admin_assignment_analytics"),

    # Admin — Dashboard Module (Phase 10)
    path("admin/assignments/<uuid:pk>/dashboard/", AdminEssayAssignmentDashboardView.as_view(), name="admin_assignment_dashboard"),

    # Admin — Reports Module (Phase 11)
    path("admin/assignments/<uuid:pk>/reports/",               AdminAssignmentReportListView.as_view(),         name="admin_assignment_reports"),
    path("admin/assignments/<uuid:pk>/reports/bulk-download/", AdminAssignmentReportBulkDownloadView.as_view(), name="admin_assignment_reports_bulk_download"),
    path("admin/assignments/<uuid:pk>/reports/bulk-resend/",   AdminAssignmentReportBulkResendView.as_view(),   name="admin_assignment_reports_bulk_resend"),
    path("admin/submissions/<uuid:pk>/regenerate-report/",     AdminReportRegenerateView.as_view(),             name="admin_submission_regenerate_report"),
    path("admin/submissions/<uuid:pk>/resend-report/",         AdminSubmissionReportResendView.as_view(),       name="admin_submission_resend_report"),

    # Admin — DLQ Module (Phase 12)
    path("admin/dlq/",                  AdminDLQListView.as_view(),      name="admin_dlq_list"),
    path("admin/dlq/bulk-retry/",       AdminDLQBulkRetryView.as_view(), name="admin_dlq_bulk_retry"),
    path("admin/dlq/<uuid:pk>/",        AdminDLQDetailView.as_view(),    name="admin_dlq_detail"),
    path("admin/dlq/<uuid:pk>/retry/",  AdminDLQRetryView.as_view(),     name="admin_dlq_retry"),
    path("admin/dlq/<uuid:pk>/resolve/", AdminDLQResolveView.as_view(),  name="admin_dlq_resolve"),

    # Admin — Notifications Module (Phase 13)
    path("admin/notifications/summary/",      AdminPipelineHealthSummaryView.as_view(), name="admin_notifications_summary"),
    path("admin/notifications/send-summary/", AdminSendDailySummaryView.as_view(),      name="admin_notifications_send_summary"),

    # Student — Past Results Interface (Phase 14)
    path("student/results/", StudentEssayResultsView.as_view(), name="student_results"),

    # Remaining admin endpoints land here starting Phase 15+ — see
    # LIVETRACKER3_V1.md for the full phase-by-phase plan.
]
