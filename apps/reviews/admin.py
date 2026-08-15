from django.contrib import admin

from apps.reviews.models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "customer_name",
        "service_name",
        "brand_name",
        "rating",
        "stars",
        "hire_status",
        "created_at",
    ]

    list_filter = [
        "rating",
        "hire__status",
        "created_at",
        "updated_at",
    ]

    search_fields = [
        "id",
        "hire__id",
        "hire__customer__full_name",
        "hire__customer__email",
        "hire__service__service_name",
        "hire__service__brand__brand_name",
        "comment",
    ]

    readonly_fields = [
        "id",
        "customer_name",
        "service_name",
        "brand_name",
        "stars",
        "created_at",
        "updated_at",
    ]

    list_select_related = [
        "hire",
        "hire__customer",
        "hire__service",
        "hire__service__brand",
    ]

    ordering = [
        "-created_at",
    ]

    list_per_page = 25

    fieldsets = (
        (
            "Review Information",
            {
                "fields": (
                    "id",
                    "hire",
                    "customer_name",
                    "service_name",
                    "brand_name",
                )
            },
        ),
        (
            "Review",
            {
                "fields": (
                    "rating",
                    "stars",
                    "comment",
                    "image",
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

    @admin.display(description="Customer")
    def customer_name(self, obj):
        return obj.hire.customer.full_name

    @admin.display(description="Service")
    def service_name(self, obj):
        return obj.hire.service.get_service_name_display()

    @admin.display(description="Brand")
    def brand_name(self, obj):
        return obj.hire.service.brand.brand_name

    @admin.display(description="Hire Status")
    def hire_status(self, obj):
        return obj.hire.status

    @admin.display(description="Stars")
    def stars(self, obj):
        return obj.stars