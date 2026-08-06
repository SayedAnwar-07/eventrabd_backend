from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TimeStampedModel, UIDMixin
from apps.hires.models import Hire, HireStatus


ZERO_AMOUNT = Decimal("0.00")

MAX_TERMS_CONDITIONS = 3
MAX_TERM_LENGTH = 300


def validate_terms_conditions(value):
    """
    Validate invoice terms and conditions.

    Rules:
        - Must be a list.
        - Maximum 3 items.
        - Every item must be non-empty text.
        - Every item can contain maximum 300 characters.
    """

    if not isinstance(value, list):
        raise ValidationError(
            "Terms and conditions must be provided as a list."
        )

    if len(value) > MAX_TERMS_CONDITIONS:
        raise ValidationError(
            "A maximum of 3 terms and conditions is allowed."
        )

    for index, item in enumerate(value, start=1):
        if not isinstance(item, str):
            raise ValidationError(
                f"Terms and conditions item {index} must be text."
            )

        cleaned_item = item.strip()

        if not cleaned_item:
            raise ValidationError(
                f"Terms and conditions item {index} cannot be empty."
            )

        if len(cleaned_item) > MAX_TERM_LENGTH:
            raise ValidationError(
                (
                    f"Terms and conditions item {index} cannot "
                    f"contain more than {MAX_TERM_LENGTH} characters."
                )
            )


class Invoice(UIDMixin, TimeStampedModel):
    """
    Financial invoice created for one accepted hire request.

    Relationship path:

        invoice.hire
        invoice.hire.customer
        invoice.hire.service
        invoice.hire.service.brand
        invoice.hire.service.brand.seller

    One hire can have only one invoice.
    """
    
    customer_agreed = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Null means pending, True means agreed, "
            "and False means disagreed."
        ),
    )

    hire = models.OneToOneField(
        Hire,
        on_delete=models.PROTECT,
        related_name="invoice",
    )

    invoice_number = models.CharField(
        max_length=40,
        unique=True,
        editable=False,
    )

    issue_date = models.DateField(
        default=timezone.localdate,
        db_index=True,
    )

    due_payment_last_date = models.DateField(
        db_index=True,
        help_text="The final date for paying the remaining amount.",
    )

    service_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="The agreed service price before discount.",
    )

    discount_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=ZERO_AMOUNT,
    )

    advance_payment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=ZERO_AMOUNT,
        help_text="Advance amount already paid by the customer.",
    )

    # Invoice snapshots
    customer_name_snapshot = models.CharField(
        max_length=255,
        editable=False,
    )

    customer_email_snapshot = models.EmailField(
        editable=False,
    )
    
    customer_whatsapp_snapshot = models.CharField(
        max_length=20,
        blank=True,
        null=True,
    )

    seller_name_snapshot = models.CharField(
        max_length=255,
        editable=False,
    )

    seller_contact_snapshot = models.CharField(
        max_length=30,
        blank=True,
        editable=False,
    )

    brand_name_snapshot = models.CharField(
        max_length=255,
        editable=False,
    )

    service_name_snapshot = models.CharField(
        max_length=255,
        editable=False,
    )

    seller_note = models.TextField(
        blank=True,
        null=True,
        help_text="Optional invoice note or payment instructions.",
    )
    
    terms_conditions = models.JSONField(
        default=list,
        blank=True,
        validators=[
            validate_terms_conditions,
        ],
        help_text=(
            "Optional invoice terms and conditions. "
            "Maximum 3 bullet points are allowed."
        ),
    )

    class Meta:
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"
        ordering = ["-created_at"]

        constraints = [
            models.CheckConstraint(
                check=Q(service_price__gte=ZERO_AMOUNT),
                name="invoice_service_price_non_negative",
            ),
            models.CheckConstraint(
                check=Q(discount_price__gte=ZERO_AMOUNT),
                name="invoice_discount_non_negative",
            ),
            models.CheckConstraint(
                check=Q(advance_payment__gte=ZERO_AMOUNT),
                name="invoice_advance_non_negative",
            ),
        ]

    def __str__(self):
        return (
            f"{self.invoice_number} - "
            f"{self.customer_name_snapshot} - "
            f"{self.service_name_snapshot}"
        )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    @property
    def customer(self):
        return self.hire.customer

    @property
    def seller(self):
        return self.hire.service.brand.seller

    @property
    def brand(self):
        return self.hire.service.brand

    @property
    def service(self):
        return self.hire.service

    # ---------------------------------------------------------
    # Automatic financial calculations
    # ---------------------------------------------------------

    @property
    def sub_total(self):
        return self.service_price or ZERO_AMOUNT

    @property
    def total(self):
        return self.sub_total - (
            self.discount_price or ZERO_AMOUNT
        )

    @property
    def due_payment(self):
        return self.total - (
            self.advance_payment or ZERO_AMOUNT
        )

    @property
    def is_paid(self):
        return self.due_payment == ZERO_AMOUNT

    @property
    def is_partially_paid(self):
        return (
            self.advance_payment > ZERO_AMOUNT
            and self.due_payment > ZERO_AMOUNT
        )

    @property
    def is_overdue(self):
        return (
            self.due_payment > ZERO_AMOUNT
            and self.due_payment_last_date < timezone.localdate()
        )

    @property
    def payment_status(self):
        if self.is_paid:
            return "paid"

        if self.is_overdue:
            return "overdue"

        if self.is_partially_paid:
            return "partially_paid"

        return "unpaid"

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    def clean(self):
        super().clean()

        errors = {}

        service_price = self.service_price or ZERO_AMOUNT
        discount_price = self.discount_price or ZERO_AMOUNT
        advance_payment = self.advance_payment or ZERO_AMOUNT

        if self._state.adding and self.hire_id:
            if self.hire.status != HireStatus.ACCEPTED:
                errors["hire"] = (
                    "An invoice can only be created for an accepted hire."
                )

        if service_price <= ZERO_AMOUNT:
            errors["service_price"] = (
                "Service price must be greater than zero."
            )

        if discount_price > service_price:
            errors["discount_price"] = (
                "Discount cannot be greater than the service price."
            )

        calculated_total = service_price - discount_price

        if advance_payment > calculated_total:
            errors["advance_payment"] = (
                "Advance payment cannot be greater than the total amount."
            )

        if (
            self.issue_date
            and self.due_payment_last_date
            and self.due_payment_last_date < self.issue_date
        ):
            errors["due_payment_last_date"] = (
                "Due payment date cannot be earlier than the invoice date."
            )

        if errors:
            raise ValidationError(errors)

    # ---------------------------------------------------------
    # Invoice number and snapshots
    # ---------------------------------------------------------

    def generate_invoice_number(self):
        date_part = timezone.localdate().strftime("%Y%m%d")

        return (
            f"INV-{date_part}-{self.id.upper()}"
        )

    def set_snapshots(self):
        customer = self.hire.customer
        service = self.hire.service
        brand = service.brand
        seller = brand.seller

        self.customer_name_snapshot = customer.full_name
        self.customer_email_snapshot = customer.email
        booking_slot = self.hire.booking_slots.first()

        self.customer_whatsapp_snapshot = (
            booking_slot.whatsapp_number
            if booking_slot else ""
        )

        self.seller_name_snapshot = seller.full_name
        self.seller_contact_snapshot = (
            seller.contact_number or ""
        )

        self.brand_name_snapshot = brand.brand_name
        self.service_name_snapshot = (
            service.get_service_name_display()
        )

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()

        if self._state.adding and self.hire_id:
            self.set_snapshots()

        self.full_clean()

        return super().save(*args, **kwargs)