from django.urls import path
from .views import (
    StudentPracticeRootView,
    StudentPracticeModuleView,
    StudentPracticeSectionView,
    StudentPracticeQuestionView,
    StudentPracticeQuestionProgressView,
    StudentPracticeQuestionRevealAnswerView,
    StudentPracticeQuestionSubmitView,
)

urlpatterns = [
    path("",                                    StudentPracticeRootView.as_view(),                  name="student_practice_root"),
    path("modules/<uuid:pk>/",                  StudentPracticeModuleView.as_view(),                name="student_practice_module"),
    path("sections/<uuid:pk>/",                 StudentPracticeSectionView.as_view(),               name="student_practice_section"),
    path("questions/<uuid:pk>/",                StudentPracticeQuestionView.as_view(),              name="student_practice_question"),
    path("questions/<uuid:pk>/progress/",       StudentPracticeQuestionProgressView.as_view(),      name="student_practice_question_progress"),
    path("questions/<uuid:pk>/reveal-answer/",  StudentPracticeQuestionRevealAnswerView.as_view(),  name="student_practice_question_reveal_answer"),
    path("questions/<uuid:pk>/submit/",         StudentPracticeQuestionSubmitView.as_view(),        name="student_practice_question_submit"),
]
