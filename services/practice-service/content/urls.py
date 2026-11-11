from django.urls import path

from .views import (
    ContentNodeListCreateView, ContentNodeDetailView, ContentNodeActionView, ContentNodeReorderView,
    ContentQuestionListCreateView, ContentQuestionDetailView, ContentQuestionActionView,
    ContentQuestionReorderView, ContentVersionListView, ContentVersionDetailView, ContentAuditListView,
    ContentQuestionImagePresignView, ContentQuestionImageConfirmView, ContentQuestionImageRemoveView,
    ContentHealthView,
)

urlpatterns = [
    path("health/", ContentHealthView.as_view(), name="content_health"),
    path("nodes/", ContentNodeListCreateView.as_view(), name="content_node_list_create"),
    path("nodes/reorder/", ContentNodeReorderView.as_view(), name="content_node_reorder"),
    path("nodes/<uuid:pk>/", ContentNodeDetailView.as_view(), name="content_node_detail"),
    path("nodes/<uuid:pk>/<str:action>/", ContentNodeActionView.as_view(), name="content_node_action"),

    path("questions/", ContentQuestionListCreateView.as_view(), name="content_question_list_create"),
    path("questions/reorder/", ContentQuestionReorderView.as_view(), name="content_question_reorder"),
    path("questions/<uuid:pk>/", ContentQuestionDetailView.as_view(), name="content_question_detail"),
    path("questions/<uuid:pk>/versions/", ContentVersionListView.as_view(), name="content_version_list"),
    path("questions/<uuid:pk>/versions/<int:version_no>/", ContentVersionDetailView.as_view(), name="content_version_detail"),

    path("questions/<uuid:pk>/image/presign/", ContentQuestionImagePresignView.as_view(), name="content_image_presign"),
    path("questions/<uuid:pk>/image/confirm/", ContentQuestionImageConfirmView.as_view(), name="content_image_confirm"),
    path("questions/<uuid:pk>/image/", ContentQuestionImageRemoveView.as_view(), name="content_image_remove"),
    path("questions/<uuid:pk>/<str:action>/", ContentQuestionActionView.as_view(), name="content_question_action"),

    path("audit/", ContentAuditListView.as_view(), name="content_audit_list"),
]
