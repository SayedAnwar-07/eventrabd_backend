from .models import Notification, NotificationType


INVOICE_FIELD_LABELS = {
    "service_price": "service price",
    "discount_price": "discount",
    "advance_payment": "advance payment",
    "due_payment_last_date": "payment due date",
    "seller_note": "seller note",
}


def send_notification_to_user(notification):
    """
    Send realtime notification event.
    """

    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()

    async_to_sync(
        channel_layer.group_send
    )(
        f"user_{notification.recipient_id}",
        {
            "type": "notification_message",
            "notification_id": str(notification.id),
            "notification_type": notification.notification_type,
        },
    )


def create_invoice_created_notification(invoice):
    """
    Create an in-app notification for the invoice customer.
    """

    notification = Notification.objects.create(
        recipient_id=invoice.hire.customer_id,
        invoice=invoice,
        notification_type=(
            NotificationType.INVOICE_CREATED
        ),
        title="New invoice created",
        message=(
            f"Invoice {invoice.invoice_number} "
            f"has been created for "
            f"{invoice.service_name_snapshot}."
        ),
        data={
            "invoice_id": str(invoice.id),
        },
    )

    send_notification_to_user(notification)

    return notification


def create_invoice_updated_notification(
    invoice,
    changed_fields,
):
    """
    Create an in-app notification when actual invoice
    information has changed.
    """

    readable_changed_fields = [
        INVOICE_FIELD_LABELS.get(
            field_name,
            field_name.replace("_", " "),
        )
        for field_name in changed_fields
    ]

    changed_text = ", ".join(
        readable_changed_fields
    )

    notification = Notification.objects.create(
        recipient_id=invoice.hire.customer_id,
        invoice=invoice,
        notification_type=(
            NotificationType.INVOICE_UPDATED
        ),
        title="Invoice updated",
        message=(
            f"Invoice {invoice.invoice_number} "
            f"has been updated. "
            f"Updated information: {changed_text}."
        ),
        data={
            "invoice_id": str(invoice.id),
            "changed_fields": changed_fields,
        },
    )

    send_notification_to_user(notification)

    return notification