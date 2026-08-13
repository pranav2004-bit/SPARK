from django.urls import path
from .views import (
    HealthView,
    StudentAnalyticsView,
    AdminOverviewView,
    AdminTopPerformersView,
    AdminWeakTopicsView,
    AdminResourceUsageView,
    SuperAdminOverviewView,
    SuperAdminDepartmentsView,
    InternalEventView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("student/", StudentAnalyticsView.as_view(), name="student-analytics"),
    path("admin/overview/", AdminOverviewView.as_view(), name="admin-overview"),
    path("admin/top-performers/", AdminTopPerformersView.as_view(), name="admin-top-performers"),
    path("admin/weak-topics/", AdminWeakTopicsView.as_view(), name="admin-weak-topics"),
    path("admin/resource-usage/", AdminResourceUsageView.as_view(), name="admin-resource-usage"),
    path("super-admin/overview/", SuperAdminOverviewView.as_view(), name="superadmin-overview"),
    path("super-admin/departments/", SuperAdminDepartmentsView.as_view(), name="superadmin-departments"),
    path("internal/event/", InternalEventView.as_view(), name="internal-event"),
]
