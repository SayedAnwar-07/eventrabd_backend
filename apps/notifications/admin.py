from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "recipient",
        "notification_type",
        "is_read",
        "created_at",
    )

    list_filter = (
        "notification_type",
        "is_read",
    )

    search_fields = (
        "recipient__email",
        "recipient__full_name",
        "title",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "read_at",
    )

    ordering = (
        "-created_at",
    )

    list_select_related = (
        "recipient",
        "hire",
        "invoice",
    )