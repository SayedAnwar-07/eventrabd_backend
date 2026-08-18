from django.contrib import admin

from .models import ServiceReport


@admin.register(ServiceReport)
class ServiceReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "reporter",
        "service",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "reporter__full_name",
        "reporter__email",
        "service__service_name",
        "message",
    )

    readonly_fields = (
        "reporter",
        "hire",
        "service",
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)