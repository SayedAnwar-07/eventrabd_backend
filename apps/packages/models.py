from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel, UIDMixin
from apps.event_services.models import EventService, ServiceType

MAX_SHORT_INFO_ITEMS = 4
MAX_SHORT_INFO_LENGTH = 120


def validate_short_info(value):
    if value in (None, []):
        return

    if not isinstance(value, list):
        raise ValidationError(
            "Short info must be a list."
        )

    if len(value) > MAX_SHORT_INFO_ITEMS:
        raise ValidationError(
            f"You can add maximum "
            f"{MAX_SHORT_INFO_ITEMS} short info items."
        )

    for item in value:
        if not isinstance(item, str):
            raise ValidationError(
                "Each short info must be text."
            )

        if not item.strip():
            raise ValidationError(
                "Short info cannot be empty."
            )

        if len(item.strip()) > MAX_SHORT_INFO_LENGTH:
            raise ValidationError(
                f"Each short info can contain maximum "
                f"{MAX_SHORT_INFO_LENGTH} characters."
            )


PACKAGE_ALLOWED_SERVICE_TYPES = {
    ServiceType.PHOTOGRAPHY,
    ServiceType.VIDEOGRAPHY,
}


class ServicePackage(UIDMixin, TimeStampedModel):
    service = models.ForeignKey(
        EventService,
        on_delete=models.CASCADE,
        related_name="packages",
    )

    package_title = models.CharField(
        max_length=100,
    )

    package_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.01")),
        ],
    )
    
    short_info = models.JSONField(
        default=list,
        blank=True,
        validators=[
            validate_short_info,
        ],
    )

    class Meta:
        verbose_name = "Service Package"
        verbose_name_plural = "Service Packages"
        ordering = ["created_at"]

    def __str__(self):
        return (
            f"{self.service.get_service_name_display()} "
            f"- {self.package_title}"
        )

    def clean(self):
        errors = {}

        if (
            self.service_id
            and self.service.service_name
            not in PACKAGE_ALLOWED_SERVICE_TYPES
        ):
            errors["service"] = (
                "Packages are only allowed for "
                "Photography and Videography services."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)