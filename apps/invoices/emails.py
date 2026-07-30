import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import Invoice


logger = logging.getLogger(__name__)


def send_invoice_created_email(invoice_pk):
    """
    Send an invoice-created email to the customer
    after the database transaction is committed.
    """

    try:
        invoice = (
            Invoice.objects
            .select_related(
                "hire",
                "hire__customer",
                "hire__service",
                "hire__service__brand",
                "hire__service__brand__seller",
            )
            .get(pk=invoice_pk)
        )

        customer_email = (
            invoice.customer_email_snapshot
            or invoice.hire.customer.email
        )

        if not customer_email:
            logger.warning(
                "Invoice email skipped because customer email "
                "is missing. Invoice ID: %s",
                invoice.pk,
            )
            return

        context = {
            "customer_name": (
                invoice.customer_name_snapshot
                or "Customer"
            ),
            "seller_name": (
                invoice.seller_name_snapshot
                or "Seller"
            ),
            "invoice_number": invoice.invoice_number,
            "issue_date": invoice.issue_date,
        }

        subject = (
            f"Your invoice has been created - "
            f"{invoice.invoice_number}"
        )

        text_content = render_to_string(
            "invoiceEmail/invoice_created.txt",
            context,
        )

        html_content = render_to_string(
            "invoiceEmail/invoice_created.html",
            context,
        )

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[customer_email],
        )

        email.attach_alternative(
            html_content,
            "text/html",
        )

        email.send(fail_silently=False)

        logger.info(
            "Invoice-created email sent successfully. "
            "Invoice ID: %s",
            invoice.pk,
        )

    except Invoice.DoesNotExist:
        logger.warning(
            "Invoice email could not be sent because invoice "
            "does not exist. Invoice ID: %s",
            invoice_pk,
        )

    except Exception:
        logger.exception(
            "Failed to send invoice-created email. "
            "Invoice ID: %s",
            invoice_pk,
        )