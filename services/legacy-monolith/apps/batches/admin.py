from django.contrib import admin
from .models import Batch


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("batch_name", "created_at")
    search_fields = ("batch_name",)
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")
