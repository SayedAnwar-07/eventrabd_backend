from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError,
)
from django.db import models

from cloudinary.models import CloudinaryField

from apps.core.models import TimeStampedModel, UIDMixin
from apps.event_services.models import EventService
from apps.hires.models import Hire, HireStatus
from apps.users.models import User


class ReportStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    UNDER_REVIEW = "under_review", "Under Review"
    RESOLVED = "resolved", "Resolved"
    DISMISSED = "dismissed", "Dismissed"


class ServiceReport(UIDMixin, TimeStampedModel):
    reporter = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="service_reports",
        limit_choices_to={"role": "customer"},
    )

    # One completed hire can create only one report.
    hire = models.OneToOneField(
        Hire,
        on_delete=models.PROTECT,
        related_name="service_report",
    )

    # Store service directly for easy filtering/admin reporting.
    # This is always taken from hire.service by backend.
    service = models.ForeignKey(
        EventService,
        on_delete=models.PROTECT,
        related_name="reports",
    )

    message = models.TextField()

    image = CloudinaryField(
        "image",
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=ReportStatus.choices,
        default=ReportStatus.PENDING,
        db_index=True,
    )

    class Meta:
        verbose_name = "Service Report"
        verbose_name_plural = "Service Reports"
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["status", "created_at"],
            ),
            models.Index(
                fields=["service", "status"],
            ),
            models.Index(
                fields=["reporter", "created_at"],
            ),
        ]

    def __str__(self):
        return (
            f"{self.reporter.full_name} reported "
            f"{self.service.get_service_name_display()}"
        )

    def clean(self):
        super().clean()

        errors = {}

        # --------------------------------------------------
        # Reporter
        # --------------------------------------------------

        if self.reporter_id:
            if self.reporter.role != "customer":
                errors["reporter"] = (
                    "Only customers can create service reports."
                )

        # --------------------------------------------------
        # Hire
        # --------------------------------------------------

        if self.hire_id:
            if (
                self.reporter_id
                and self.hire.customer_id != self.reporter_id
            ):
                errors["hire"] = (
                    "You can only report a service "
                    "that you personally hired."
                )

            if (
                self.service_id
                and self.hire.service_id != self.service_id
            ):
                errors["service"] = (
                    "The reported service does not match "
                    "the service from this hire request."
                )

            # Hire must be fully completed.
            if self.hire.status != HireStatus.COMPLETED:
                errors["hire"] = (
                    "You can only report this service after "
                    "the hire has been completed."
                )

            # Invoice must exist and customer must have agreed.
            try:
                invoice = self.hire.invoice
            except ObjectDoesNotExist:
                invoice = None

            if invoice is None:
                errors["hire"] = (
                    "You can only report this service after "
                    "the invoice process has been completed."
                )

            elif invoice.customer_agreed is not True:
                errors["hire"] = (
                    "You can only report this service after "
                    "you have agreed to the completed invoice."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)