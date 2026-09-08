from django.urls import path
from .views import (
    HealthView,
    AdminPaperListCreateView,
    AdminPaperDetailView,
    AdminPaperInstructionsView,
    AdminPaperSetsView,
    AdminSetDetailView,
    AdminSetQuestionsView,
    AdminSetSectionsView,
    AdminSectionDetailView,
    AdminSectionQuestionsView,
    AdminQuestionDetailView,
    AdminQuestionOptionsView,
    AdminQuestionOptionDetailView,
    AdminQuestionImagePresignView,
    AdminOptionImagePresignView,
    AdminSetImagePresignView,
    AdminAssignmentListCreateView,
    AdminAssignmentDetailView,
    AdminAssignmentStartView,
    AdminAssignmentCloseView,
    AdminAssignmentResyncRosterView,
    AdminAssignmentExtendSessionView,
    AdminAssignmentStatusView,
    StudentServerTimeView,
    StudentAssignmentListView,
    StudentAssignmentStartSessionView,
    StudentAnswerView,
    StudentSubmitView,
    StudentSessionQuestionsView,
    StudentActivityLogBulkCreateView,
    StudentResultsView,
    AdminAssignmentResultsView,
    AdminResultResponsesView,
    AdminQuestionResponsesView,
    AdminSessionTimelineView,
    AdminAssignmentResultsExportView,
    AdminAssignmentAnalyticsView,
    AdminAssignmentAnalyticsExportView,
    AdminAssignmentDashboardView,
    AdminAssignmentDashboardExportView,
    AdminTrialStartView,
    AdminTrialSessionQuestionsView,
    AdminTrialAnswerView,
    AdminTrialSubmitView,
    AdminTrialServerTimeView,
    AdminPaperTrialResultsView,
)

urlpatterns = [
    # Health
    path("health/", HealthView.as_view(), name="health"),

    # Admin — question papers
    path("admin/papers/",                                  AdminPaperListCreateView.as_view(),   name="admin_paper_list_create"),
    path("admin/papers/<uuid:pk>/",                         AdminPaperDetailView.as_view(),       name="admin_paper_detail"),
    path("admin/papers/<uuid:pk>/instructions/",             AdminPaperInstructionsView.as_view(), name="admin_paper_instructions"),
    path("admin/papers/<uuid:pk>/sets/",                    AdminPaperSetsView.as_view(),         name="admin_paper_sets"),

    # Admin — sets
    path("admin/sets/<uuid:pk>/",                           AdminSetDetailView.as_view(),         name="admin_set_detail"),
    path("admin/sets/<uuid:pk>/questions/",                 AdminSetQuestionsView.as_view(),      name="admin_set_questions"),
    path("admin/sets/<uuid:pk>/sections/",                  AdminSetSectionsView.as_view(),       name="admin_set_sections"),
    path("admin/sets/<uuid:pk>/image-presign/",              AdminSetImagePresignView.as_view(),   name="admin_set_image_presign"),

    # Admin — question sections
    path("admin/sections/<uuid:pk>/",                       AdminSectionDetailView.as_view(),     name="admin_section_detail"),
    path("admin/sections/<uuid:pk>/questions/",              AdminSectionQuestionsView.as_view(),  name="admin_section_questions"),

    # Admin — questions
    path("admin/questions/<uuid:pk>/",                      AdminQuestionDetailView.as_view(),    name="admin_question_detail"),
    path("admin/questions/<uuid:pk>/options/",               AdminQuestionOptionsView.as_view(),   name="admin_question_options"),
    path("admin/questions/<uuid:pk>/options/<uuid:option_pk>/", AdminQuestionOptionDetailView.as_view(), name="admin_question_option_detail"),
    path("admin/questions/<uuid:pk>/image-presign/",        AdminQuestionImagePresignView.as_view(), name="admin_question_image_presign"),
    path("admin/questions/<uuid:pk>/options/<uuid:option_pk>/image-presign/", AdminOptionImagePresignView.as_view(), name="admin_option_image_presign"),

    # Admin — batch assignments (Task 3.2)
    path("admin/assignments/",                              AdminAssignmentListCreateView.as_view(), name="admin_assignment_list_create"),
    path("admin/assignments/<uuid:pk>/",                     AdminAssignmentDetailView.as_view(),     name="admin_assignment_detail"),
    path("admin/assignments/<uuid:pk>/start/",                AdminAssignmentStartView.as_view(),      name="admin_assignment_start"),
    path("admin/assignments/<uuid:pk>/close/",                AdminAssignmentCloseView.as_view(),      name="admin_assignment_close"),
    path("admin/assignments/<uuid:pk>/resync-roster/",        AdminAssignmentResyncRosterView.as_view(), name="admin_assignment_resync_roster"),
    path("admin/assignments/<uuid:pk>/sessions/<uuid:session_id>/extend/", AdminAssignmentExtendSessionView.as_view(), name="admin_assignment_extend_session"),
    path("admin/assignments/<uuid:pk>/status/",                AdminAssignmentStatusView.as_view(),     name="admin_assignment_status"),

    # Student (Task 4.2 / 5.1)
    path("student/server-time/", StudentServerTimeView.as_view(), name="student_server_time"),
    path("student/assignments/", StudentAssignmentListView.as_view(), name="student_assignment_list"),
    path("student/assignments/<uuid:pk>/start-session/", StudentAssignmentStartSessionView.as_view(), name="student_assignment_start_session"),
    path("student/sessions/<uuid:pk>/questions/", StudentSessionQuestionsView.as_view(), name="student_session_questions"),
    path("student/sessions/<uuid:pk>/questions/<uuid:qid>/answer/", StudentAnswerView.as_view(), name="student_answer"),
    path("student/sessions/<uuid:pk>/submit/", StudentSubmitView.as_view(), name="student_submit"),
    path("student/sessions/<uuid:pk>/activity-logs/", StudentActivityLogBulkCreateView.as_view(), name="student_activity_logs"),
    path("student/results/", StudentResultsView.as_view(), name="student_results"),

    # Admin — results (Phase 7)
    path("admin/assignments/<uuid:pk>/results/", AdminAssignmentResultsView.as_view(), name="admin_assignment_results"),
    path("admin/assignments/<uuid:pk>/results/export/", AdminAssignmentResultsExportView.as_view(), name="admin_assignment_results_export"),
    path("admin/results/<uuid:result_id>/responses/", AdminResultResponsesView.as_view(), name="admin_result_responses"),
    path("admin/assignments/<uuid:pk>/questions/<uuid:question_id>/responses/", AdminQuestionResponsesView.as_view(), name="admin_question_responses"),
    path("admin/sessions/<uuid:session_id>/timeline/", AdminSessionTimelineView.as_view(), name="admin_session_timeline"),
    path("admin/assignments/<uuid:pk>/analytics/", AdminAssignmentAnalyticsView.as_view(), name="admin_assignment_analytics"),
    path("admin/assignments/<uuid:pk>/analytics/export/", AdminAssignmentAnalyticsExportView.as_view(), name="admin_assignment_analytics_export"),

    # Admin — dashboard (Task 9.1)
    path("admin/assignments/<uuid:pk>/dashboard/", AdminAssignmentDashboardView.as_view(), name="admin_assignment_dashboard"),
    path("admin/assignments/<uuid:pk>/dashboard/export/", AdminAssignmentDashboardExportView.as_view(), name="admin_assignment_dashboard_export"),

    # Admin — mock/trial exam sessions (added 2026-08-27)
    path("admin/papers/<uuid:pk>/trial/start/", AdminTrialStartView.as_view(), name="admin_trial_start"),
    path("admin/papers/<uuid:pk>/trial-results/", AdminPaperTrialResultsView.as_view(), name="admin_paper_trial_results"),
    path("admin/trial/server-time/", AdminTrialServerTimeView.as_view(), name="admin_trial_server_time"),
    path("admin/trial/sessions/<uuid:pk>/questions/", AdminTrialSessionQuestionsView.as_view(), name="admin_trial_session_questions"),
    path("admin/trial/sessions/<uuid:pk>/questions/<uuid:qid>/answer/", AdminTrialAnswerView.as_view(), name="admin_trial_answer"),
    path("admin/trial/sessions/<uuid:pk>/submit/", AdminTrialSubmitView.as_view(), name="admin_trial_submit"),

    # Remaining admin endpoints land here starting Phase 10+ — see
    # docs/assessment-service-api.md for the full frozen contract.
]
