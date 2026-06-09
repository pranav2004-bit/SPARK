from django.contrib import admin
from .models import Company, Section, Upload


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0
    readonly_fields = ("id", "created_at")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("company_name", "is_published", "created_at")
    list_filter = ("is_published",)
    search_fields = ("company_name",)
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [SectionInline]


class UploadInline(admin.TabularInline):
    model = Upload
    extra = 0
    readonly_fields = ("id", "created_at")


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("section_name", "company", "created_at")
    list_filter = ("company",)
    search_fields = ("section_name", "company__company_name")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [UploadInline]


@admin.register(Upload)
class UploadAdmin(admin.ModelAdmin):
    list_display = ("upload_type", "original_filename", "section", "file_size_bytes", "created_at")
    list_filter = ("upload_type",)
    search_fields = ("original_filename", "section__section_name")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at")
