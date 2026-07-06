from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from cloudinary.models import CloudinaryField

from apps.core.models import TimeStampedModel, UIDMixin
from apps.event_planner.models import EventBrand
from django.utils.crypto import get_random_string


class ServiceType(models.TextChoices):
    PHOTOGRAPHY = "photography", "Photography"
    VIDEOGRAPHY = "videography", "Videography"
    STAGE_DESIGNER = "stage_designer", "Stage Designer"
    SOUND_LIGHTING = "sound_lighting", "Sound System and Lighting"
    DJ = "dj", "DJ"


SERVICE_IMAGE_LIMITS = {
    ServiceType.PHOTOGRAPHY: 4,
    ServiceType.STAGE_DESIGNER: 4,
    ServiceType.DJ: 2,
    ServiceType.VIDEOGRAPHY: 0,
    ServiceType.SOUND_LIGHTING: 0,
}


class EventService(UIDMixin, TimeStampedModel):
    brand = models.ForeignKey(
        EventBrand,
        on_delete=models.CASCADE,
        related_name="services",
    )

    service_name = models.CharField(
        max_length=50,
        choices=ServiceType.choices,
        db_index=True,
    )

    slug = models.SlugField(
        max_length=255,
        unique=True,
        db_index=True,
        blank=True,
    )

    cover_photo = CloudinaryField(
        "image",
        blank=True,
        null=True,
    )

    drive_link = models.URLField(
        blank=True,
        null=True,
        help_text="Google Drive or YouTube URL where applicable.",
    )

    shift_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    # Type specific fields
    shift_hour = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Used for Photography, Videography, DJ.",
    )

    sound_system_payment = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Used for Sound System and Lighting.",
    )

    lighting_payment = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Used for Sound System and Lighting.",
    )

    class Meta:
        verbose_name = "Event Service"
        verbose_name_plural = "Event Services"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["brand", "service_name"],
                name="unique_service_name_per_brand",
            )
        ]
        indexes = [
            models.Index(fields=["service_name"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return f"{self.brand.brand_name} - {self.get_service_name_display()}"

    def clean(self):
        errors = {}

        # Reset validation expectations by service type
        if self.service_name == ServiceType.PHOTOGRAPHY:
            if not self.shift_hour:
                errors["shift_hour"] = "shift_hour is required for Photography."

        elif self.service_name == ServiceType.VIDEOGRAPHY:
            if not self.shift_hour:
                errors["shift_hour"] = "shift_hour is required for Videography."
            if not self.drive_link:
                errors["drive_link"] = "drive_link is required for Videography."

        elif self.service_name == ServiceType.STAGE_DESIGNER:
            pass

        elif self.service_name == ServiceType.SOUND_LIGHTING:
            if not self.shift_hour:
                errors["shift_hour"] = "shift_hour is required for Sound Lighting."

        elif self.service_name == ServiceType.DJ:
            if not self.shift_hour:
                errors["shift_hour"] = "shift_hour is required for DJ."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.service_name)

            # avoid duplicates
            while EventService.objects.filter(slug=self.slug).exists():
                self.slug = f"{slugify(self.service_name)}-{get_random_string(4)}"

        super().save(*args, **kwargs)

    @property
    def image_limit(self):
        return SERVICE_IMAGE_LIMITS.get(self.service_name, 0)


class ServiceGalleryImage(UIDMixin, TimeStampedModel):
    service = models.ForeignKey(
        EventService,
        on_delete=models.CASCADE,
        related_name="gallery_images",
    )

    image = CloudinaryField(
        "image",
        blank=False,
        null=False,
    )

    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Service Gallery Image"
        verbose_name_plural = "Service Gallery Images"
        ordering = ["sort_order", "-created_at"]

    def __str__(self):
        return f"{self.service.slug} - gallery image"