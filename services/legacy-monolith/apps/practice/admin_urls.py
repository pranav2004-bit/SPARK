from django.urls import path
from .views import (
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
)

urlpatterns = [
    # Hub root — modules (parent=null) + sections (module=null)
    path("", AdminPracticeRootView.as_view(), name="admin_practice_root"),

    # Modules
    path("modules/",                           AdminPracticeModuleListCreateView.as_view(),  name="admin_practice_module_list_create"),
    path("modules/<uuid:pk>/",                 AdminPracticeModuleDetailView.as_view(),      name="admin_practice_module_detail"),
    path("modules/<uuid:pk>/children/",        AdminPracticeModuleChildrenView.as_view(),    name="admin_practice_module_children"),
    path("modules/<uuid:pk>/sections/",        AdminPracticeModuleSectionsView.as_view(),    name="admin_practice_module_sections"),

    # Sections
    path("sections/",                          AdminPracticeSectionListCreateView.as_view(), name="admin_practice_section_list_create"),
    path("sections/<uuid:pk>/",                AdminPracticeSectionDetailView.as_view(),     name="admin_practice_section_detail"),
    path("sections/<uuid:section_id>/questions/", AdminPracticeQuestionListCreateView.as_view(), name="admin_practice_question_list_create"),

    # Questions — CRUD
    path("questions/<uuid:pk>/",              AdminPracticeQuestionDetailView.as_view(),                  name="admin_practice_question_detail"),

    # Questions — MCQ options CRUD
    path("questions/<uuid:pk>/options/",                        AdminPracticeQuestionOptionListCreateView.as_view(), name="admin_practice_question_options"),
    path("questions/<uuid:pk>/options/<uuid:option_pk>/",       AdminPracticeQuestionOptionDetailView.as_view(),     name="admin_practice_question_option_detail"),

    # Questions — presign: question body image
    path("questions/<uuid:pk>/question-image/presign/",     AdminPracticeQuestionBodyImagePresignView.as_view(),        name="admin_practice_question_body_image_presign"),
    # Questions — presign: explanation image
    path("questions/<uuid:pk>/explanation-image/presign/",  AdminPracticeQuestionExplanationImagePresignView.as_view(), name="admin_practice_question_explanation_image_presign"),
]
