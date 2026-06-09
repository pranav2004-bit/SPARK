from django.contrib import admin
from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("student_id", "fullname", "department", "batch", "is_active", "is_profile_completed")
    list_filter = ("is_active", "is_profile_completed", "department", "batch")
    search_fields = ("student_id", "fullname", "college_email_id")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")
