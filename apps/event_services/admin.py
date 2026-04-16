from django.contrib import admin
from django.utils.html import format_html

from apps.event_services.models import EventService, ServiceGalleryImage


# ─────────────────────────────────────────────────────────────
# Inline for gallery images
# ─────────────────────────────────────────────────────────────
class ServiceGalleryImageInline(admin.TabularInline):
    model = ServiceGalleryImage
    extra = 1
    fields = ("image_preview", "image", "sort_order", "created_at")
    readonly_fields = ("image_preview", "created_at")
    ordering = ("sort_order",)

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" width="80" height="80" style="object-fit: cover;" />',
                obj.image.url,
            )
        return "-"
    
    image_preview.short_description = "Preview"


# ─────────────────────────────────────────────────────────────
# Event Service Admin
# ─────────────────────────────────────────────────────────────
@admin.register(EventService)
class EventServiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "service_name",
        "brand",
        "seller",
        "shift_charge",
        "created_at",
        "cover_preview",
    )

    list_filter = (
        "service_name",
        "created_at",
        "brand",
    )

    search_fields = (
        "service_name",
        "brand__brand_name",
        "brand__slug",
    )

    readonly_fields = (
        "slug",
        "created_at",
        "updated_at",
        "cover_preview",
    )

    inlines = [ServiceGalleryImageInline]

    fieldsets = (
        ("Basic Info", {
            "fields": (
                "brand",
                "service_name",
                "slug",
                "description",
            )
        }),
        ("Media", {
            "fields": (
                "cover_photo",
                "cover_preview",
                "drive_link",
            )
        }),
        ("Pricing & Details", {
            "fields": (
                "shift_charge",
                "shift_hour",
                "sound_system_payment",
                "lighting_payment",
            )
        }),
        ("Timestamps", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    def seller(self, obj):
        return obj.brand.seller
    seller.short_description = "Seller"

    def cover_preview(self, obj):
        if obj.cover_photo:
            return format_html(
                '<img src="{}" width="100" height="100" style="object-fit: cover;" />',
                obj.cover_photo.url,
            )
        return "-"
    
    cover_preview.short_description = "Cover Preview"


# ─────────────────────────────────────────────────────────────
# Gallery Image Admin
# ─────────────────────────────────────────────────────────────
@admin.register(ServiceGalleryImage)
class ServiceGalleryImageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "service",
        "sort_order",
        "created_at",
        "image_preview",
    )

    list_filter = ("created_at", "service")
    search_fields = ("service__service_name", "service__brand__brand_name")

    readonly_fields = ("created_at", "image_preview")

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" width="80" height="80" style="object-fit: cover;" />',
                obj.image.url,
            )
        return "-"
    
    image_preview.short_description = "Preview"