from django.contrib import admin

from apps.hires.models import Hire, HireBookingSlot


class HireBookingSlotInline(admin.TabularInline):
    model = HireBookingSlot
    extra = 0
    show_change_link = True

    fields = [
        "starts_at",
        "ends_at",
        "venue_name",
        "venue_address",
        "location_note",
    ]


@admin.register(Hire)
class HireAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "customer",
        "seller_name",
        "service",
        "status",
        "accepted_status",
        "created_at",
    ]

    list_filter = [
        "status",
        "service__service_name",
        "created_at",
    ]

    search_fields = [
        "id",
        "customer__full_name",
        "customer__email",
        "service__brand__brand_name",
        "service__brand__seller__full_name",
        "service__brand__seller__email",
    ]

    readonly_fields = [
        "id",
        "seller_name",
        "created_at",
        "updated_at",
        "accepted_at",
        "rejected_at",
        "cancelled_at",
        "completed_at",
    ]

    list_select_related = [
        "customer",
        "service",
        "service__brand",
        "service__brand__seller",
        "cancelled_by",
    ]

    ordering = ["-created_at"]
    list_per_page = 25

    inlines = [HireBookingSlotInline]

    fieldsets = (
        (
            "Hire Information",
            {
                "fields": (
                    "id",
                    "customer",
                    "service",
                    "seller_name",
                    "status",
                )
            },
        ),
        (
            "Notes",
            {
                "fields": (
                    "customer_note",
                    "seller_note",
                )
            },
        ),
        (
            "Status Information",
            {
                "fields": (
                    "accepted_at",
                    "rejected_at",
                    "cancelled_at",
                    "completed_at",
                    "cancelled_by",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Seller")
    def seller_name(self, obj):
        return obj.service.brand.seller.full_name

    @admin.display(
        description="Accepted",
        boolean=True,
    )
    def accepted_status(self, obj):
        return obj.is_accept


@admin.register(HireBookingSlot)
class HireBookingSlotAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "hire",
        "starts_at",
        "ends_at",
        "venue_name",
        "created_at",
    ]

    list_filter = [
        "starts_at",
        "created_at",
    ]

    search_fields = [
        "id",
        "hire__id",
        "hire__customer__full_name",
        "hire__customer__email",
        "venue_name",
        "venue_address",
    ]

    readonly_fields = [
        "id",
        "created_at",
        "updated_at",
    ]

    list_select_related = [
        "hire",
        "hire__customer",
        "hire__service",
        "hire__service__brand",
    ]

    ordering = ["-starts_at"]
    list_per_page = 25