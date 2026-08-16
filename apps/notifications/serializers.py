from rest_framework import serializers

from apps.hires.models import Hire
from apps.invoices.models import Invoice

from .models import Notification


# =========================================================
# Hire notification summary
# =========================================================


class NotificationHireSerializer(
    serializers.ModelSerializer
):
    """
    Lightweight Hire information for seller notifications.

    IMPORTANT:
    Do not use HireDetailSerializer here.

    Notification list should remain lightweight and must
    not load booking_items, booking_slots, packages, etc.

    The seller can open the Hire detail endpoint when
    full booking information is actually required.
    """

    customer_name = serializers.CharField(
        source="customer.full_name",
        read_only=True,
    )

    service_name = serializers.CharField(
        source="service.service_name",
        read_only=True,
    )

    service_display_name = serializers.CharField(
        source="service.get_service_name_display",
        read_only=True,
    )

    class Meta:
        model = Hire

        fields = [
            "id",
            "status",
            "customer_name",
            "customer_whatsapp_number",
            "service_name",
            "service_display_name",
            "created_at",
        ]

        read_only_fields = fields


# =========================================================
# Invoice notification summary
# =========================================================


class NotificationInvoiceSerializer(
    serializers.ModelSerializer
):
    """
    Lightweight Invoice information for customer
    notifications.

    Uses Invoice snapshots wherever possible.

    No Hire/Service/Brand relationship traversal is
    required here, so notification serialization stays
    cheap.
    """
    hire_id = serializers.CharField(
        read_only=True,
    )

    total = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    due_payment = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    payment_status = serializers.CharField(
        read_only=True,
    )

    class Meta:
        model = Invoice

        fields = [
            "id",
            "hire_id",
            "invoice_number",

            "brand_name_snapshot",
            "display_name_snapshot",
            "service_name_snapshot",

            "issue_date",
            "due_payment_last_date",

            "service_price",
            "additional_charge",
            "discount_price",
            "advance_payment",

            "total",
            "due_payment",
            "payment_status",

            "customer_agreed",

            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


# =========================================================
# Main notification serializer
# =========================================================


class NotificationSerializer(
    serializers.ModelSerializer
):
    """
    Main notification response.

    Exactly one source should exist:

        HIRE_CREATED
            -> hire != null
            -> invoice == null

        INVOICE_CREATED / INVOICE_UPDATED
            -> invoice != null
            -> hire == null

    This serializer performs no custom database queries.
    """

    hire = NotificationHireSerializer(
        read_only=True,
    )

    invoice = NotificationInvoiceSerializer(
        read_only=True,
    )

    class Meta:
        model = Notification

        fields = [
            "id",
            "notification_type",
            "title",
            "message",
            "data",

            "hire",
            "invoice",

            "is_read",
            "read_at",

            "created_at",
        ]

        read_only_fields = fields

    # ---------------------------------------------------------
    # Query optimization
    # ---------------------------------------------------------

    @staticmethod
    def setup_eager_loading(queryset):
        """
        Apply all relations required by this serializer.

        This prevents N+1 database queries.

        Example:

            queryset = Notification.objects.filter(
                recipient=request.user
            )

            queryset = (
                NotificationSerializer
                .setup_eager_loading(queryset)
            )

        Only JOINs are used here.

        No prefetch_related() is needed because notification
        list does not expose booking_items or booking_slots.
        """

        return queryset.select_related(
            "hire",
            "hire__customer",
            "hire__service",
            "invoice",
        )


# =========================================================
# Notification counts
# =========================================================


class NotificationCountSerializer(
    serializers.Serializer
):
    """
    Response for:

        GET /notifications/count/

    Example:

        {
            "total_count": 15,
            "unread_count": 4
        }
    """

    total_count = serializers.IntegerField(
        read_only=True,
    )

    unread_count = serializers.IntegerField(
        read_only=True,
    )


# =========================================================
# Mark all as read response
# =========================================================


class NotificationMarkAllReadSerializer(
    serializers.Serializer
):
    """
    Response after marking all unread notifications
    as read.

    Example:

        {
            "updated_count": 4,
            "unread_count": 0
        }
    """

    updated_count = serializers.IntegerField(
        read_only=True,
    )

    unread_count = serializers.IntegerField(
        read_only=True,
    )