from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from cloudinary.models import CloudinaryField

from apps.core.models import TimeStampedModel, UIDMixin
from apps.event_planner.models import EventBrand


class ServiceType(models.TextChoices):
    PHOTOGRAPHY = "photography", "Photography"
    VIDEOGRAPHY = "videography", "Videography"
    STAGE_DESIGNER = "stage_designer", "Stage Designer"
    SOUND_LIGHTING = "sound_lighting", "Sound System and Lighting"
    EVENT_HALL = "event_hall", "Event Hall"


SERVICE_IMAGE_LIMITS = {
    ServiceType.PHOTOGRAPHY: 5,
    ServiceType.STAGE_DESIGNER: 5,
    ServiceType.EVENT_HALL: 5,
    ServiceType.VIDEOGRAPHY: 0,
    ServiceType.SOUND_LIGHTING: 0,
}

GALLERY_ONLY_SERVICE_TYPES = {
    ServiceType.PHOTOGRAPHY,
    ServiceType.STAGE_DESIGNER,
    ServiceType.EVENT_HALL,
}


COVER_PHOTO_ONLY_SERVICE_TYPES = {
    ServiceType.VIDEOGRAPHY,
    ServiceType.SOUND_LIGHTING,
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
        help_text="Used for Photography and Videography services."
    )
    
    rating_sum = models.PositiveBigIntegerField(
        default=0,
        editable=False,
    )

    review_count = models.PositiveBigIntegerField(
        default=0,
        editable=False,
    )
    
    report_count = models.PositiveBigIntegerField(
        default=0,
        editable=False,
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

        elif self.service_name == ServiceType.STAGE_DESIGNER:
            pass

        elif self.service_name == ServiceType.SOUND_LIGHTING:
            pass

        elif self.service_name == ServiceType.EVENT_HALL:
            pass

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.service_name)

        super().save(*args, **kwargs)

    @property
    def image_limit(self):
        return SERVICE_IMAGE_LIMITS.get(self.service_name, 0)
    
    @property
    def rating_count(self):
        """
        Every review requires a rating,
        so rating_count == review_count.
        """

        return self.review_count


    @property
    def average_rating(self):
        """
        Public star rating.

        Internal:
            rating_sum = sum of 2-10 rating values

        Public:
            average = rating_sum / review_count / 2
        """

        if not self.review_count:
            return Decimal("0.00")

        return (
            Decimal(self.rating_sum)
            / Decimal(self.review_count)
            / Decimal("2")
        ).quantize(
            Decimal("0.01")
        )


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