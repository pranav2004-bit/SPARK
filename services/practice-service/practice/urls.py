from django.urls import path
from .views import (
    HealthView,
    # Admin
    AdminPracticeRootView,
    AdminPracticeModuleListCreateView,
    AdminPracticeModuleDetailView,
    AdminPracticeModuleChildrenView,
    AdminPracticeModuleSectionsView,
    AdminPracticeSectionListCreateView,
    AdminPracticeSectionDetailView,
    AdminPracticeQuestionListCreateView,
    AdminPracticeQuestionDetailView,
    AdminPracticeQuestionOptionListCreateView,
    AdminPracticeQuestionOptionDetailView,
    AdminPracticeQuestionBodyImagePresignView,
    AdminPracticeQuestionExplanationImagePresignView,
    # Student
    StudentPracticeRootView,
    StudentPracticeModuleView,
    StudentPracticeSectionView,
    StudentPracticeQuestionView,
    StudentPracticeQuestionProgressView,
    StudentPracticeQuestionRevealAnswerView,
    StudentPracticeQuestionSubmitView,
)

urlpatterns = [
    # Health
    path("health/", HealthView.as_view(), name="health"),

    # Admin — hub root (top-level modules + root sections)
    path("", AdminPracticeRootView.as_view(), name="admin_practice_root"),

    # Admin — modules
    path("modules/",                               AdminPracticeModuleListCreateView.as_view(),  name="admin_module_list_create"),
    path("modules/<uuid:pk>/",                     AdminPracticeModuleDetailView.as_view(),      name="admin_module_detail"),
    path("modules/<uuid:pk>/children/",            AdminPracticeModuleChildrenView.as_view(),    name="admin_module_children"),
    path("modules/<uuid:pk>/sections/",            AdminPracticeModuleSectionsView.as_view(),    name="admin_module_sections"),

    # Admin — sections
    path("sections/",                              AdminPracticeSectionListCreateView.as_view(), name="admin_section_list_create"),
    path("sections/<uuid:pk>/",                    AdminPracticeSectionDetailView.as_view(),     name="admin_section_detail"),
    path("sections/<uuid:section_id>/questions/",  AdminPracticeQuestionListCreateView.as_view(), name="admin_question_list_create"),

    # Admin — questions
    path("questions/<uuid:pk>/",                                  AdminPracticeQuestionDetailView.as_view(),                  name="admin_question_detail"),
    path("questions/<uuid:pk>/options/",                          AdminPracticeQuestionOptionListCreateView.as_view(),        name="admin_question_options"),
    path("questions/<uuid:pk>/options/<uuid:option_pk>/",         AdminPracticeQuestionOptionDetailView.as_view(),            name="admin_question_option_detail"),
    path("questions/<uuid:pk>/question-image/presign/",           AdminPracticeQuestionBodyImagePresignView.as_view(),        name="admin_question_body_image_presign"),
    path("questions/<uuid:pk>/explanation-image/presign/",        AdminPracticeQuestionExplanationImagePresignView.as_view(), name="admin_question_explanation_image_presign"),

    # Student
    path("student/",                                              StudentPracticeRootView.as_view(),                  name="student_root"),
    path("student/modules/<uuid:pk>/",                            StudentPracticeModuleView.as_view(),                name="student_module"),
    path("student/sections/<uuid:pk>/",                           StudentPracticeSectionView.as_view(),               name="student_section"),
    path("student/questions/<uuid:pk>/",                          StudentPracticeQuestionView.as_view(),              name="student_question"),
    path("student/questions/<uuid:pk>/progress/",                 StudentPracticeQuestionProgressView.as_view(),      name="student_question_progress"),
    path("student/questions/<uuid:pk>/reveal-answer/",            StudentPracticeQuestionRevealAnswerView.as_view(),  name="student_question_reveal"),
    path("student/questions/<uuid:pk>/submit/",                   StudentPracticeQuestionSubmitView.as_view(),        name="student_question_submit"),
]
