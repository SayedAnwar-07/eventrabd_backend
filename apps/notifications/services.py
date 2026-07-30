from .models import Notification, NotificationType


INVOICE_FIELD_LABELS = {
    "service_price": "service price",
    "discount_price": "discount",
    "advance_payment": "advance payment",
    "due_payment_last_date": "payment due date",
    "seller_note": "seller note",
}


def create_invoice_created_notification(invoice):
    """
    Create an in-app notification for the invoice customer.
    """

    return Notification.objects.create(
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

    return Notification.objects.create(
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