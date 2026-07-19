from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import TimeStampedModel, UIDMixin
from apps.event_services.models import EventService
from apps.users.models import User


class HireStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"


class Hire(UIDMixin, TimeStampedModel):
    """
    A customer's request to hire one seller service.

    The seller is not stored separately because it is already available through:

        hire.service.brand.seller

    Storing another seller ForeignKey would duplicate data and could create
    inconsistent records.
    """

    customer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="customer_hires",
        limit_choices_to={"role": "customer"},
    )

    service = models.ForeignKey(
        EventService,
        on_delete=models.PROTECT,
        related_name="hire_requests",
    )

    status = models.CharField(
        max_length=20,
        choices=HireStatus.choices,
        default=HireStatus.PENDING,
        db_index=True,
    )

    customer_note = models.TextField(
        blank=True,
        null=True,
        help_text="Additional information provided by the customer.",
    )

    seller_note = models.TextField(
        blank=True,
        null=True,
        help_text="Seller's response or explanation.",
    )

    accepted_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    rejected_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    cancelled_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    completed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    cancelled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="cancelled_hires",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Hire Request"
        verbose_name_plural = "Hire Requests"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["service", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return (
            f"{self.customer.full_name} hired "
            f"{self.service.get_service_name_display()} "
            f"from {self.service.brand.brand_name}"
        )

    @property
    def seller(self):
        return self.service.brand.seller

    @property
    def is_accept(self):
        """
        Compatibility property for frontend usage.

        Do not store this separately in the database.
        """
        return self.status == HireStatus.ACCEPTED

    @property
    def can_create_invoice(self):
        return self.status == HireStatus.ACCEPTED

    def clean(self):
        errors = {}

        if self.customer_id:
            if self.customer.role != "customer":
                errors["customer"] = "Only a customer can create a hire request."

        if self.service_id:
            seller = self.service.brand.seller

            if seller.role != "seller":
                errors["service"] = (
                    "The selected service does not belong to a valid seller."
                )

            if self.customer_id and self.customer_id == seller.id:
                errors["customer"] = (
                    "A seller cannot hire their own service."
                )

        if self.status == HireStatus.ACCEPTED and not self.accepted_at:
            errors["accepted_at"] = (
                "accepted_at is required when the hire is accepted."
            )

        if self.status == HireStatus.REJECTED and not self.rejected_at:
            errors["rejected_at"] = (
                "rejected_at is required when the hire is rejected."
            )

        if self.status == HireStatus.CANCELLED and not self.cancelled_at:
            errors["cancelled_at"] = (
                "cancelled_at is required when the hire is cancelled."
            )

        if self.status == HireStatus.COMPLETED and not self.completed_at:
            errors["completed_at"] = (
                "completed_at is required when the hire is completed."
            )

        if errors:
            raise ValidationError(errors)

    def accept(self, seller, note=None):
        """
        Accept the hire request.

        The seller argument should be request.user from the API.
        """
        if seller.pk != self.seller.pk:
            raise ValidationError(
                "Only the owner of this service can accept the hire request."
            )

        if self.status != HireStatus.PENDING:
            raise ValidationError(
                f"A {self.status} hire request cannot be accepted."
            )

        self.status = HireStatus.ACCEPTED
        self.accepted_at = timezone.now()
        self.rejected_at = None

        if note is not None:
            self.seller_note = note

        self.full_clean()
        self.save()

    def reject(self, seller, note=None):
        """
        Reject the hire request.
        """
        if seller.pk != self.seller.pk:
            raise ValidationError(
                "Only the owner of this service can reject the hire request."
            )

        if self.status != HireStatus.PENDING:
            raise ValidationError(
                f"A {self.status} hire request cannot be rejected."
            )

        self.status = HireStatus.REJECTED
        self.rejected_at = timezone.now()
        self.accepted_at = None

        if note is not None:
            self.seller_note = note

        self.full_clean()
        self.save()

    def cancel(self, user):
        """
        Customer or service owner can cancel a pending/accepted hire.
        """
        allowed_user_ids = {
            self.customer_id,
            self.seller.id,
        }

        if user.id not in allowed_user_ids:
            raise ValidationError(
                "You do not have permission to cancel this hire request."
            )

        if self.status not in {
            HireStatus.PENDING,
            HireStatus.ACCEPTED,
        }:
            raise ValidationError(
                f"A {self.status} hire request cannot be cancelled."
            )

        self.status = HireStatus.CANCELLED
        self.cancelled_at = timezone.now()
        self.cancelled_by = user

        self.full_clean()
        self.save()

    def mark_completed(self, seller):
        """
        Mark an accepted hire as completed.
        """
        if seller.pk != self.seller.pk:
            raise ValidationError(
                "Only the service owner can complete this hire."
            )

        if self.status != HireStatus.ACCEPTED:
            raise ValidationError(
                "Only an accepted hire can be completed."
            )

        self.status = HireStatus.COMPLETED
        self.completed_at = timezone.now()

        self.full_clean()
        self.save()


class HireBookingSlot(UIDMixin, TimeStampedModel):
    """
    One booked event date/time/place.

    A Hire can have multiple HireBookingSlot records, allowing customers
    to select multiple event dates.
    """

    hire = models.ForeignKey(
        Hire,
        on_delete=models.CASCADE,
        related_name="booking_slots",
    )

    starts_at = models.DateTimeField(
        db_index=True,
        help_text="Event starting date and time.",
    )

    ends_at = models.DateTimeField(
        db_index=True,
        help_text="Event ending date and time.",
    )

    venue_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Example: Grand Palace Convention Hall.",
    )

    venue_address = models.TextField(
        help_text="Full event location or address.",
    )

    location_note = models.TextField(
        blank=True,
        null=True,
        help_text="Optional directions or location instructions.",
    )

    class Meta:
        verbose_name = "Hire Booking Slot"
        verbose_name_plural = "Hire Booking Slots"
        ordering = ["starts_at"]

        constraints = [
            models.CheckConstraint(
                check=Q(ends_at__gt=F("starts_at")),
                name="hire_slot_end_after_start",
            ),
            models.UniqueConstraint(
                fields=[
                    "hire",
                    "starts_at",
                    "ends_at",
                ],
                name="unique_time_slot_per_hire",
            ),
        ]

        indexes = [
            models.Index(fields=["hire", "starts_at"]),
            models.Index(fields=["starts_at", "ends_at"]),
        ]

    def __str__(self):
        return (
            f"{self.hire.service.get_service_name_display()} - "
            f"{self.starts_at}"
        )

    def clean(self):
        errors = {}

        if self.starts_at and self.ends_at:
            if self.ends_at <= self.starts_at:
                errors["ends_at"] = (
                    "The ending time must be later than the starting time."
                )

        if errors:
            raise ValidationError(errors)