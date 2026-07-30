from rest_framework import serializers

from apps.invoices.models import Invoice

from .models import Notification


class NotificationInvoiceSerializer(
    serializers.ModelSerializer
):
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
            "invoice_number",
            "brand_name_snapshot",
            "service_name_snapshot",
            "service_price",
            "discount_price",
            "advance_payment",
            "total",
            "due_payment",
            "payment_status",
            "due_payment_last_date",
        ]

        read_only_fields = fields


class NotificationSerializer(
    serializers.ModelSerializer
):
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
            "invoice",
            "is_read",
            "read_at",
            "created_at",
        ]

        read_only_fields = fields


class NotificationCountSerializer(
    serializers.Serializer
):
    total_count = serializers.IntegerField(
        read_only=True,
    )

    unread_count = serializers.IntegerField(
        read_only=True,
    )


class NotificationMarkAllReadSerializer(
    serializers.Serializer
):
    updated_count = serializers.IntegerField(
        read_only=True,
    )

    unread_count = serializers.IntegerField(
        read_only=True,
    )