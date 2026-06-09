from django.urls import path
from .views import BatchListCreateView, BatchDetailView
from apps.students.views import AdminBatchStudentsView

urlpatterns = [
    path("", BatchListCreateView.as_view(), name="batch_list_create"),
    path("<uuid:pk>/", BatchDetailView.as_view(), name="batch_detail"),
    path("<uuid:batch_id>/students/", AdminBatchStudentsView.as_view(), name="batch_students"),
]
