from django.contrib import admin
from .models import EventBrand, EventBrandSlugHistory


class EventBrandSlugHistoryInline(admin.TabularInline):
    model = EventBrandSlugHistory
    extra = 0
    readonly_fields = ["old_slug", "created_at"]
    can_delete = False
    ordering = ["-created_at"]


@admin.register(EventBrand)
class EventBrandAdmin(admin.ModelAdmin):
    list_display = [
        "brand_name",
        "seller",
        "division",
        "district",
        "created_at",
    ]
    list_filter = ["division", "district"]
    search_fields = [
        "brand_name",
        "seller__email",
        "seller__full_name",
        "whatsapp_number",
    ]
    readonly_fields = [
        "id",
        "slug",
        "brand_name_last_changed",
        "created_at",
        "updated_at",
    ]
    autocomplete_fields = ["seller"]
    inlines = [EventBrandSlugHistoryInline]

    fieldsets = (
        (None, {
            "fields": ("seller", "brand_name", "slug", "logo")
        }),
        ("Location", {
            "fields": ("division", "district")
        }),
        ("Contact & Details", {
            "fields": ("whatsapp_number", "short_description")
        }),
        ("Metadata", {
            "fields": ("id", "brand_name_last_changed", "created_at", "updated_at")
        }),
    )


@admin.register(EventBrandSlugHistory)
class EventBrandSlugHistoryAdmin(admin.ModelAdmin):
    list_display = ["brand", "old_slug", "created_at"]
    search_fields = ["brand__brand_name", "old_slug"]
    readonly_fields = ["brand", "old_slug", "created_at"]