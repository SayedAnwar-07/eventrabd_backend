from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import (
    TimeStampedModel,
    UIDMixin,
)


class NotificationType(models.TextChoices):
    """
    Supported in-app notification events.
    """

    # Customer creates a Hire request.
    # Recipient: Seller.
    HIRE_CREATED = (
        "hire_created",
        "New Hire Request",
    )

    # Seller creates an Invoice.
    # Recipient: Customer.
    INVOICE_CREATED = (
        "invoice_created",
        "Invoice Created",
    )

    # Seller updates an Invoice.
    # Recipient: Customer.
    INVOICE_UPDATED = (
        "invoice_updated",
        "Invoice Updated",
    )
    
    # Customer submits a service review.
    # Recipient: Seller.
    REVIEW_CREATED = (
        "review_created",
        "New Service Review",
    )


class NotificationQuerySet(models.QuerySet):
    """
    Optimized reusable notification queries.

    Keeping common queries here avoids duplicating
    filtering logic throughout views/services.
    """

    def for_recipient(self, user):
        return self.filter(
            recipient=user,
        )

    def unread(self):
        return self.filter(
            is_read=False,
        )

    def read(self):
        return self.filter(
            is_read=True,
        )

    def mark_all_read(self):
        """
        Mark all unread notifications in this
        queryset as read using one database query.

        Example:

            Notification.objects
            .for_recipient(user)
            .unread()
            .mark_all_read()
        """

        now = timezone.now()

        return self.filter(
            is_read=False,
        ).update(
            is_read=True,
            read_at=now,
            updated_at=now,
        )


class Notification(
    UIDMixin,
    TimeStampedModel,
):
    """
    In-app notification for an authenticated user.

    Current event flow:

        Hire created
            Customer -> Seller

        Invoice created
            Seller -> Customer

        Invoice updated
            Seller -> Customer

    Notifications are created only by backend services.

    Users cannot manually create notification records
    through the public API.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    # ---------------------------------------------------------
    # Notification source
    # ---------------------------------------------------------

    hire = models.ForeignKey(
        "hires.Hire",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )

    invoice = models.ForeignKey(
        "invoices.Invoice",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    
    review = models.ForeignKey(
        "reviews.Review",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )

    # ---------------------------------------------------------
    # Notification content
    # ---------------------------------------------------------

    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
    )

    title = models.CharField(
        max_length=255,
    )

    message = models.TextField()

    data = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Small additional metadata required by "
            "the frontend. Do not store complete "
            "Hire or Invoice objects here."
        ),
    )

    # ---------------------------------------------------------
    # Read state
    # ---------------------------------------------------------

    is_read = models.BooleanField(
        default=False,
    )

    read_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    objects = NotificationQuerySet.as_manager()

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

        ordering = [
            "-created_at",
        ]

        indexes = [
            # Main notification list:
            #
            # WHERE recipient_id = ?
            # ORDER BY created_at DESC
            models.Index(
                fields=[
                    "recipient",
                    "-created_at",
                ],
                name="notif_rec_created_idx",
            ),

            # Unread list + unread count.
            #
            # This is a partial index, so PostgreSQL
            # only indexes unread notifications.
            models.Index(
                fields=[
                    "recipient",
                    "-created_at",
                ],
                condition=Q(
                    is_read=False,
                ),
                name="notif_unread_rec_idx",
            ),
        ]

        constraints = [
            # -------------------------------------------------
            # Read-state integrity
            # -------------------------------------------------

            models.CheckConstraint(
                condition=(
                    Q(
                        is_read=False,
                        read_at__isnull=True,
                    )
                    |
                    Q(
                        is_read=True,
                        read_at__isnull=False,
                    )
                ),
                name="notif_read_state_chk",
            ),

            # -------------------------------------------------
            # Every notification must belong to exactly
            # one source:
            #
            # Hire OR Invoice
            # -------------------------------------------------

            models.CheckConstraint(
                condition=(
                    Q(
                        hire__isnull=False,
                        invoice__isnull=True,
                        review__isnull=True,
                    )
                    |
                    Q(
                        hire__isnull=True,
                        invoice__isnull=False,
                        review__isnull=True,
                    )
                    |
                    Q(
                        hire__isnull=True,
                        invoice__isnull=True,
                        review__isnull=False,
                    )
                ),
                name="notif_one_source_chk",
            ),

            # -------------------------------------------------
            # Notification type must match its source.
            # -------------------------------------------------

            models.CheckConstraint(
                condition=(
                    Q(
                        notification_type=(
                            NotificationType.HIRE_CREATED
                        ),
                        hire__isnull=False,
                        invoice__isnull=True,
                        review__isnull=True,
                    )
                    |
                    Q(
                        notification_type__in=[
                            NotificationType.INVOICE_CREATED,
                            NotificationType.INVOICE_UPDATED,
                        ],
                        hire__isnull=True,
                        invoice__isnull=False,
                        review__isnull=True,
                    )
                    |
                    Q(
                        notification_type=(
                            NotificationType.REVIEW_CREATED
                        ),
                        hire__isnull=True,
                        invoice__isnull=True,
                        review__isnull=False,
                    )
                ),
                name="notif_type_source_chk",
            ),

            # -------------------------------------------------
            # Prevent duplicate "Hire Created"
            # notification.
            #
            # One seller should receive only one
            # HIRE_CREATED notification for one Hire.
            # -------------------------------------------------

            models.UniqueConstraint(
                fields=[
                    "recipient",
                    "hire",
                    "notification_type",
                ],
                condition=Q(
                    notification_type=(
                        NotificationType.HIRE_CREATED
                    ),
                ),
                name="notif_unique_hire_created",
            ),

            # -------------------------------------------------
            # Prevent duplicate "Invoice Created"
            # notification.
            #
            # Invoice updates are intentionally NOT unique,
            # because an invoice may be edited multiple times.
            # -------------------------------------------------

            models.UniqueConstraint(
                fields=[
                    "recipient",
                    "invoice",
                    "notification_type",
                ],
                condition=Q(
                    notification_type=(
                        NotificationType.INVOICE_CREATED
                    ),
                ),
                name="notif_unique_invoice_created",
            ),
            
            models.UniqueConstraint(
                fields=[
                    "recipient",
                    "review",
                    "notification_type",
                ],
                condition=Q(
                    notification_type=(
                        NotificationType.REVIEW_CREATED
                    ),
                ),
                name="notif_unique_review_created",
            ),
        ]

    def __str__(self):
        return (
            f"{self.recipient} - "
            f"{self.notification_type} - "
            f"{self.title}"
        )

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------

    def save(self, *args, **kwargs):
        """
        Keep is_read and read_at synchronized.

        Handles normal saves and update_fields safely.
        """

        if self.is_read:
            if self.read_at is None:
                self.read_at = timezone.now()

        else:
            self.read_at = None

        update_fields = kwargs.get(
            "update_fields"
        )

        if update_fields is not None:
            update_fields = set(
                update_fields
            )

            update_fields.add(
                "read_at"
            )

            update_fields.add(
                "updated_at"
            )

            kwargs["update_fields"] = list(
                update_fields
            )

        return super().save(
            *args,
            **kwargs,
        )

    # ---------------------------------------------------------
    # Read helpers
    # ---------------------------------------------------------

    def mark_as_read(self):
        """
        Mark this notification as read.

        Uses a conditional UPDATE so repeated requests
        are idempotent and do not perform unnecessary
        writes.
        """

        if self.is_read:
            return False

        now = timezone.now()

        updated_count = (
            type(self)
            .objects
            .filter(
                pk=self.pk,
                is_read=False,
            )
            .update(
                is_read=True,
                read_at=now,
                updated_at=now,
            )
        )

        if updated_count:
            self.is_read = True
            self.read_at = now
            self.updated_at = now

            return True

        return False

    def mark_as_unread(self):
        """
        Optional helper for future use.

        Currently this does not need to be exposed
        through the public API.
        """

        if not self.is_read:
            return False

        now = timezone.now()

        updated_count = (
            type(self)
            .objects
            .filter(
                pk=self.pk,
                is_read=True,
            )
            .update(
                is_read=False,
                read_at=None,
                updated_at=now,
            )
        )

        if updated_count:
            self.is_read = False
            self.read_at = None
            self.updated_at = now

            return True

        return False