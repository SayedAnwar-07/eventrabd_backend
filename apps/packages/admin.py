from django.contrib import admin

from apps.packages.models import ServicePackage


@admin.register(ServicePackage)
class ServicePackageAdmin(admin.ModelAdmin):
    list_display = (
        "package_title",
        "service",
        "package_price",
        "created_at",
    )

    list_filter = (
        "service__service_name",
        "created_at",
    )

    search_fields = (
        "package_title",
        "service__brand__brand_name",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

    ordering = (
        "-created_at",
    )