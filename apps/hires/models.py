from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models, transaction
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
        """
        Invoice is allowed only for an existing accepted hire
        that does not already have an invoice.
        """
        return bool(
            self.pk
            and self.status == HireStatus.ACCEPTED
            and not hasattr(self, "invoice")
        )

    def clean(self):
        errors = {}

        if self.customer_id:
            if self.customer.role != "customer":
                errors["customer"] = "Only a customer can create a hire request."

        if self.service_id:
            # FIX: self.service.brand or brand.seller can be missing/unset,
            # which raises ObjectDoesNotExist deep inside attribute access
            # instead of surfacing as a clean validation error.
            try:
                seller = self.service.brand.seller
            except ObjectDoesNotExist:
                errors["service"] = (
                    "The selected service does not belong to a valid seller."
                )
                seller = None

            if seller is not None:
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

        # Customer and service become permanent after hire creation.
        if not self._state.adding:
            previous = (
                Hire.objects
                .filter(pk=self.pk)
                .values(
                    "customer_id",
                    "service_id",
                )
                .first()
            )

            if previous:
                if previous["customer_id"] != self.customer_id:
                    errors["customer"] = (
                        "The customer cannot be changed after "
                        "the hire request is created."
                    )

                if previous["service_id"] != self.service_id:
                    errors["service"] = (
                        "The service cannot be changed after "
                        "the hire request is created."
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """
        Enforce model validation whenever a hire is saved.
        """

        self.full_clean()
        return super().save(*args, **kwargs)
    
    def accept(self, seller, note=None):
        if seller.pk != self.seller.pk:
            raise ValidationError(
                "Only the owner of this service can accept the hire request."
            )

        with transaction.atomic():
            current = (
                Hire.objects
                .select_for_update()
                .get(pk=self.pk)
            )

            if current.status != HireStatus.PENDING:
                raise ValidationError(
                    f"A {current.status} hire request cannot be accepted."
                )

            existing_bookings = (
                HireBookingSlot.objects
                .select_for_update()
                .filter(
                    hire__service_id=self.service_id,
                    hire__status__in=[
                        HireStatus.ACCEPTED,
                        HireStatus.COMPLETED,
                    ],
                )
                .exclude(hire_id=self.pk)
            )

            for requested_slot in self.booking_slots.all():
                conflict_exists = existing_bookings.filter(
                    starts_at=requested_slot.starts_at,
                ).exists()

                if conflict_exists:
                    raise ValidationError({
                        "booking_slots": (
                            "This service already has a booking for the requested start time."
                        )
                    })

            self.status = HireStatus.ACCEPTED
            self.accepted_at = timezone.now()
            self.rejected_at = None

            if note is not None:
                self.seller_note = note

            self.save()

    def reject(self, seller, note=None):
        if seller.pk != self.seller.pk:
            raise ValidationError(
                "Only the owner of this service can reject the hire request."
            )

        # FIX: same row-locking gap as accept() — lock and re-check
        # status before writing.
        with transaction.atomic():
            current = (
                Hire.objects
                .select_for_update()
                .get(pk=self.pk)
            )

            if current.status != HireStatus.PENDING:
                raise ValidationError(
                    f"A {current.status} hire request cannot be rejected."
                )

            self.status = HireStatus.REJECTED
            self.rejected_at = timezone.now()
            self.accepted_at = None

            if note is not None:
                self.seller_note = note

            self.save()

    def cancel(self, user):
        """
        Customer or service owner can cancel a pending or accepted hire.

        An invoiced hire cannot be cancelled until invoice cancellation
        or voiding is implemented.
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

        if hasattr(self, "invoice"):
            raise ValidationError({
                "invoice": (
                    "This hire already has an invoice and cannot be "
                    "cancelled directly."
                )
            })

        self.status = HireStatus.CANCELLED
        self.cancelled_at = timezone.now()
        self.cancelled_by = user

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

        self.save()


class HireBookingSlot(UIDMixin, TimeStampedModel):
    """
    One booked event date/time/place.

    Booking slots may only be created or modified while the related
    hire request is pending.
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
    
    whatsapp_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Customer WhatsApp number.",
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
    
    google_map_link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Optional Google Maps shared location link.",
    )

    class Meta:
        verbose_name = "Hire Booking Slot"
        verbose_name_plural = "Hire Booking Slots"
        ordering = ["starts_at"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "hire",
                    "starts_at",
                ],
                name="unique_time_slot_per_hire",
            ),
        ]

        indexes = [
            models.Index(fields=["hire", "starts_at"]),
            models.Index(fields=["starts_at"]),
        ]

    def __str__(self):
        return (
            f"{self.hire.service.get_service_name_display()} - "
            f"{self.starts_at}"
        )

    def ensure_mutable(self):
        """
        Prevent creating, updating, moving, or deleting a booking slot
        after the hire leaves pending status.
        """

        if not self.hire_id:
            return

        if self._state.adding:
            related_hire = self.hire

        else:
            original_slot = (
                HireBookingSlot.objects
                .select_related("hire")
                .get(pk=self.pk)
            )

            if original_slot.hire_id != self.hire_id:
                raise ValidationError({
                    "hire": (
                        "A booking slot cannot be moved from one "
                        "hire request to another."
                    )
                })

            related_hire = original_slot.hire

        if related_hire.status != HireStatus.PENDING:
            raise ValidationError({
                "hire": (
                    "Booking details cannot be changed after the "
                    "hire request has been accepted, rejected, "
                    "cancelled, or completed."
                )
            })

        if hasattr(related_hire, "invoice"):
            raise ValidationError({
                "hire": (
                    "Booking details cannot be changed after an "
                    "invoice has been created."
                )
            })


    def save(self, *args, **kwargs):
        """
        Django does not automatically call model.clean() during save().
        Calling full_clean() here enforces validation outside serializers too.
        """

        self.ensure_mutable()
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Prevent directly deleting one slot from a locked hire.
        """

        self.ensure_mutable()
        return super().delete(*args, **kwargs)