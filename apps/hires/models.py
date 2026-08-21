from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
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


class EventType(models.TextChoices):
    HOLUD = "holud", "Holud"
    MEHEDI = "mehedi", "Mehedi"
    AKHD_WALIMA = "akhd_walima", "Akhd/Walima"
    WEDDING_CEREMONY = "wedding_ceremony", "Wedding Ceremony"
    RECEPTION = "reception", "Reception"
    ANNIVERSARY = "anniversary", "Anniversary"
    BIRTHDAY = "birthday", "Birthday"
    OTHERS = "others", "Others"


class Hire(UIDMixin, TimeStampedModel):
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

    # Keep old fields temporarily for existing hires/invoices.
    package = models.ForeignKey(
        "packages.ServicePackage",
        on_delete=models.SET_NULL,
        related_name="hire_requests",
        blank=True,
        null=True,
    )

    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )

    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
        blank=True,
        null=True,
        db_index=True,
    )

    customer_whatsapp_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
    )

    package_title_snapshot = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        editable=False,
    )

    package_price_snapshot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        editable=False,
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
    )

    seller_note = models.TextField(
        blank=True,
        null=True,
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
        return self.status == HireStatus.ACCEPTED

    @property
    def can_create_invoice(self):
        return bool(
            self.pk
            and self.status == HireStatus.ACCEPTED
            and not hasattr(self, "invoice")
        )

    def _legacy_unit_price(self):
        if self.package_price_snapshot is not None:
            return self.package_price_snapshot

        return self.service.shift_charge or Decimal("0.00")

    @property
    def booking_title(self):
        if self.pk:
            items = list(self.booking_items.all())

            if len(items) == 1:
                return items[0].booking_title

            if len(items) > 1:
                return (
                    f"{self.service.get_service_name_display()} "
                    f"({len(items)} booking options)"
                )

        if self.package_title_snapshot:
            return self.package_title_snapshot

        return self.service.get_service_name_display()

    @property
    def booking_price(self):
        """
        Backward compatible price.

        Multiple booking items return their total base amount.
        """
        if self.pk:
            items = list(self.booking_items.all())

            if len(items) == 1:
                return items[0].unit_price

            if len(items) > 1:
                return sum(
                    (item.total_price for item in items),
                    Decimal("0.00"),
                )

        return self._legacy_unit_price()

    @property
    def total_booking_price(self):
        if self.pk:
            items = list(self.booking_items.all())

            if items:
                return sum(
                    (item.total_price for item in items),
                    Decimal("0.00"),
                )

        return self._legacy_unit_price() * self.quantity

    @property
    def is_package_hire(self):
        if self.pk and self.booking_items.exists():
            return self.booking_items.filter(
                package__isnull=False,
            ).exists()

        return bool(
            self.package_id
            or self.package_price_snapshot is not None
        )

    def clean(self):
        errors = {}

        if self.customer_id and self.customer.role != "customer":
            errors["customer"] = (
                "Only a customer can create a hire request."
            )

        if self.service_id:
            try:
                seller = self.service.brand.seller
            except ObjectDoesNotExist:
                seller = None
                errors["service"] = (
                    "The selected service does not belong "
                    "to a valid seller."
                )

            if seller is not None:
                if seller.role != "seller":
                    errors["service"] = (
                        "The selected service does not belong "
                        "to a valid seller."
                    )

                if (
                    self.customer_id
                    and self.customer_id == seller.id
                ):
                    errors["customer"] = (
                        "A seller cannot hire their own service."
                    )

            # Legacy package validation.
            if (
                self.package_id
                and self.package.service_id != self.service_id
            ):
                errors["package"] = (
                    "The selected package does not belong "
                    "to this service."
                )

        if (
            self.status == HireStatus.ACCEPTED
            and not self.accepted_at
        ):
            errors["accepted_at"] = (
                "accepted_at is required when the hire is accepted."
            )

        if (
            self.status == HireStatus.REJECTED
            and not self.rejected_at
        ):
            errors["rejected_at"] = (
                "rejected_at is required when the hire is rejected."
            )

        if (
            self.status == HireStatus.CANCELLED
            and not self.cancelled_at
        ):
            errors["cancelled_at"] = (
                "cancelled_at is required when the hire is cancelled."
            )

        if (
            self.status == HireStatus.COMPLETED
            and not self.completed_at
        ):
            errors["completed_at"] = (
                "completed_at is required when the hire is completed."
            )

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
                        "The customer cannot be changed "
                        "after hire creation."
                    )

                if previous["service_id"] != self.service_id:
                    errors["service"] = (
                        "The service cannot be changed "
                        "after hire creation."
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def accept(self, seller, note=None):
        if seller.pk != self.seller.pk:
            raise ValidationError(
                "Only the owner of this service can accept "
                "the hire request."
            )

        with transaction.atomic():
            current = (
                Hire.objects
                .select_for_update()
                .get(pk=self.pk)
            )

            if current.status != HireStatus.PENDING:
                raise ValidationError(
                    f"A {current.status} hire request "
                    f"cannot be accepted."
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
                if requested_slot.starts_at is None:
                    continue

                if existing_bookings.filter(
                    starts_at=requested_slot.starts_at,
                ).exists():
                    raise ValidationError({
                        "booking_slots": (
                            "This service already has a booking "
                            "for the requested start time."
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
                "Only the owner of this service can reject "
                "the hire request."
            )

        with transaction.atomic():
            current = (
                Hire.objects
                .select_for_update()
                .get(pk=self.pk)
            )

            if current.status != HireStatus.PENDING:
                raise ValidationError(
                    f"A {current.status} hire request "
                    f"cannot be rejected."
                )

            self.status = HireStatus.REJECTED
            self.rejected_at = timezone.now()
            self.accepted_at = None

            if note is not None:
                self.seller_note = note

            self.save()

    def cancel(self, user):
        allowed_user_ids = {
            self.customer_id,
            self.seller.id,
        }

        if user.id not in allowed_user_ids:
            raise ValidationError(
                "You do not have permission to cancel "
                "this hire request."
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
                    "This hire already has an invoice and "
                    "cannot be cancelled directly."
                )
            })

        self.status = HireStatus.CANCELLED
        self.cancelled_at = timezone.now()
        self.cancelled_by = user

        self.save()

    def mark_completed(self, seller):
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


class HireBookingItem(UIDMixin, TimeStampedModel):
    """
    One selected booking option.
    package=None means normal service.
    """

    hire = models.ForeignKey(
        Hire,
        on_delete=models.CASCADE,
        related_name="booking_items",
    )

    package = models.ForeignKey(
        "packages.ServicePackage",
        on_delete=models.SET_NULL,
        related_name="hire_booking_items",
        blank=True,
        null=True,
    )

    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )

    package_title_snapshot = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        editable=False,
    )

    package_price_snapshot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        editable=False,
    )

    class Meta:
        verbose_name = "Hire Booking Item"
        verbose_name_plural = "Hire Booking Items"
        ordering = ["created_at"]

        constraints = [
            # Same package should use quantity instead.
            models.UniqueConstraint(
                fields=["hire", "package"],
                condition=Q(package__isnull=False),
                name="unique_package_per_hire",
            ),

            # Only one normal-service item per Hire.
            models.UniqueConstraint(
                fields=["hire"],
                condition=Q(package__isnull=True),
                name="one_normal_service_item_per_hire",
            ),
        ]

    def __str__(self):
        return (
            f"{self.booking_title} × {self.quantity}"
        )

    @property
    def booking_title(self):
        if self.package_title_snapshot:
            return self.package_title_snapshot

        if self.package_id:
            return self.package.package_title

        return self.hire.service.get_service_name_display()

    @property
    def unit_price(self):
        if self.package_price_snapshot is not None:
            return self.package_price_snapshot

        if self.package_id:
            return self.package.package_price

        return self.hire.service.shift_charge or Decimal("0.00")

    @property
    def total_price(self):
        return self.unit_price * self.quantity

    @property
    def is_package(self):
        return bool(
            self.package_id
            or self.package_price_snapshot is not None
        )

    def ensure_mutable(self):
        if not self.hire_id:
            return

        if self.hire.status != HireStatus.PENDING:
            raise ValidationError({
                "hire": (
                    "Booking options cannot be changed "
                    "after the hire leaves pending status."
                )
            })

        if hasattr(self.hire, "invoice"):
            raise ValidationError({
                "hire": (
                    "Booking options cannot be changed "
                    "after invoice creation."
                )
            })

    def clean(self):
        errors = {}

        if (
            self.package_id
            and self.hire_id
            and self.package.service_id != self.hire.service_id
        ):
            errors["package"] = (
                "The selected package does not belong "
                "to this service."
            )

        if self.hire_id:
            siblings = (
                HireBookingItem.objects
                .filter(hire_id=self.hire_id)
                .exclude(pk=self.pk)
            )

            # Multiple different options => every item quantity must be 1.
            if siblings.exists():
                if self.quantity != 1:
                    errors["quantity"] = (
                        "Quantity must be 1 when multiple "
                        "booking options are selected."
                    )

                if siblings.filter(quantity__gt=1).exists():
                    errors["quantity"] = (
                        "Another booking option already has "
                        "quantity greater than 1."
                    )

        if not self._state.adding:
            previous = (
                HireBookingItem.objects
                .filter(pk=self.pk)
                .values(
                    "hire_id",
                    "package_id",
                )
                .first()
            )

            if previous:
                if previous["hire_id"] != self.hire_id:
                    errors["hire"] = (
                        "Booking item cannot be moved "
                        "to another hire."
                    )

                if previous["package_id"] != self.package_id:
                    errors["package"] = (
                        "Package cannot be changed after "
                        "the booking item is created."
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.ensure_mutable()

        if self.package_id:
            self.package_title_snapshot = (
                self.package.package_title
            )
            self.package_price_snapshot = (
                self.package.package_price
            )

        self.full_clean()

        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.ensure_mutable()
        return super().delete(*args, **kwargs)


class HireBookingSlot(UIDMixin, TimeStampedModel):
    hire = models.ForeignKey(
        Hire,
        on_delete=models.CASCADE,
        related_name="booking_slots",
    )

    # Links this event to Normal Service / exact Package.
    booking_item = models.ForeignKey(
        HireBookingItem,
        on_delete=models.CASCADE,
        related_name="booking_slots",
        blank=True,
        null=True,
    )

    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
        blank=True,
        null=True,
        db_index=True,
    )

    starts_at = models.DateTimeField(
        blank=True,
        null=True,
        db_index=True,
    )

    venue_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    venue_address = models.TextField(
        blank=True,
        null=True,
    )

    google_map_link = models.URLField(
        max_length=500,
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Hire Booking Slot"
        verbose_name_plural = "Hire Booking Slots"
        ordering = ["starts_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["hire", "starts_at"],
                name="unique_time_slot_per_hire",
            ),

            # Same event type may exist under different packages.
            models.UniqueConstraint(
                fields=["booking_item", "event_type"],
                name="unique_event_type_per_booking_item",
            ),
        ]

    def __str__(self):
        title = (
            self.booking_item.booking_title
            if self.booking_item_id
            else self.hire.service.get_service_name_display()
        )

        return f"{title} - {self.starts_at}"

    def ensure_mutable(self):
        if not self.hire_id:
            return

        if self.booking_item_id:
            if self.booking_item.hire_id != self.hire_id:
                raise ValidationError({
                    "booking_item": (
                        "Booking item does not belong "
                        "to this hire."
                    )
                })

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
                        "Booking slot cannot be moved "
                        "to another hire."
                    )
                })

            if (
                original_slot.booking_item_id
                != self.booking_item_id
            ):
                raise ValidationError({
                    "booking_item": (
                        "Booking slot cannot be moved "
                        "to another booking item."
                    )
                })

            related_hire = original_slot.hire

        if related_hire.status != HireStatus.PENDING:
            raise ValidationError({
                "hire": (
                    "Booking details cannot be changed "
                    "after the hire leaves pending status."
                )
            })

        if hasattr(related_hire, "invoice"):
            raise ValidationError({
                "hire": (
                    "Booking details cannot be changed "
                    "after invoice creation."
                )
            })

    def save(self, *args, **kwargs):
        self.ensure_mutable()
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.ensure_mutable()
        return super().delete(*args, **kwargs)