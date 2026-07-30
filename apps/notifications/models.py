from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TimeStampedModel, UIDMixin


class NotificationType(models.TextChoices):
    INVOICE_CREATED = (
        "invoice_created",
        "Invoice Created",
    )

    INVOICE_UPDATED = (
        "invoice_updated",
        "Invoice Updated",
    )


class Notification(UIDMixin, TimeStampedModel):
    """
    In-app notification shown to an authenticated user.

    The system creates notifications automatically.
    Users cannot manually create or edit notifications.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    invoice = models.ForeignKey(
        "invoices.Invoice",
        on_delete=models.SET_NULL,
        related_name="notifications",
        null=True,
        blank=True,
    )

    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        db_index=True,
    )

    title = models.CharField(
        max_length=255,
    )

    message = models.TextField()

    data = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Additional notification information, "
            "such as changed invoice fields."
        ),
    )

    is_read = models.BooleanField(
        default=False,
        db_index=True,
    )

    read_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=[
                    "recipient",
                    "-created_at",
                ],
                name="notif_recipient_created_idx",
            ),
            models.Index(
                fields=[
                    "recipient",
                    "is_read",
                ],
                name="notif_recipient_read_idx",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                check=(
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
                name="notification_read_state_valid",
            ),
        ]

    def __str__(self):
        return (
            f"{self.recipient} - "
            f"{self.title}"
        )

    def save(self, *args, **kwargs):
        if self.is_read and self.read_at is None:
            self.read_at = timezone.now()

        if not self.is_read:
            self.read_at = None

        return super().save(*args, **kwargs)

    def mark_as_read(self):
        if self.is_read:
            return False

        self.is_read = True
        self.read_at = timezone.now()

        self.save(
            update_fields=[
                "is_read",
                "read_at",
                "updated_at",
            ]
        )

        return True