from django.contrib import admin

from .models import Invoice


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "customer_name_snapshot",
        "seller_name_snapshot",
        "brand_name_snapshot",
        "service_name_snapshot",
        "service_price",
        "display_total",
        "advance_payment",
        "display_due_payment",
        "display_payment_status",
        "customer_agreed",
        "issue_date",
        "due_payment_last_date",
    )

    list_filter = (
        "customer_agreed",
        "issue_date",
        "due_payment_last_date",
        "created_at",
    )

    search_fields = (
        "invoice_number",
        "customer_name_snapshot",
        "customer_email_snapshot",
        "customer_contact_snapshot",
        "seller_name_snapshot",
        "seller_contact_snapshot",
        "brand_name_snapshot",
        "service_name_snapshot",
        "hire__customer__email",
        "hire__service__brand__seller__email",
    )

    ordering = (
        "-created_at",
    )

    date_hierarchy = "issue_date"

    list_select_related = (
        "hire",
        "hire__customer",
        "hire__service",
        "hire__service__brand",
        "hire__service__brand__seller",
    )

    raw_id_fields = (
        "hire",
    )

    readonly_fields = (
        "invoice_number",
        "customer_name_snapshot",
        "customer_email_snapshot",
        "customer_contact_snapshot",
        "seller_name_snapshot",
        "seller_contact_snapshot",
        "brand_name_snapshot",
        "service_name_snapshot",
        "display_sub_total",
        "display_total",
        "display_due_payment",
        "display_payment_status",
        "display_is_paid",
        "display_is_overdue",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Invoice Information",
            {
                "fields": (
                    "invoice_number",
                    "hire",
                    "issue_date",
                    "due_payment_last_date",
                    "customer_agreed",
                ),
            },
        ),
        (
            "Financial Information",
            {
                "fields": (
                    "service_price",
                    "discount_price",
                    "advance_payment",
                    "display_sub_total",
                    "display_total",
                    "display_due_payment",
                    "display_payment_status",
                    "display_is_paid",
                    "display_is_overdue",
                ),
            },
        ),
        (
            "Customer Snapshot",
            {
                "fields": (
                    "customer_name_snapshot",
                    "customer_email_snapshot",
                    "customer_contact_snapshot",
                ),
            },
        ),
        (
            "Seller and Service Snapshot",
            {
                "fields": (
                    "seller_name_snapshot",
                    "seller_contact_snapshot",
                    "brand_name_snapshot",
                    "service_name_snapshot",
                ),
            },
        ),
        (
            "Additional Information",
            {
                "fields": (
                    "seller_note",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(
            super().get_readonly_fields(
                request,
                obj,
            )
        )

        if obj:
            readonly_fields.append("hire")

        return readonly_fields

    @admin.display(
        description="Subtotal",
    )
    def display_sub_total(self, obj):
        return obj.sub_total

    @admin.display(
        description="Total",
    )
    def display_total(self, obj):
        return obj.total

    @admin.display(
        description="Due Payment",
    )
    def display_due_payment(self, obj):
        return obj.due_payment

    @admin.display(
        description="Payment Status",
    )
    def display_payment_status(self, obj):
        return obj.payment_status.replace(
            "_",
            " ",
        ).title()

    @admin.display(
        boolean=True,
        description="Paid",
    )
    def display_is_paid(self, obj):
        return obj.is_paid

    @admin.display(
        boolean=True,
        description="Overdue",
    )
    def display_is_overdue(self, obj):
        return obj.is_overdue