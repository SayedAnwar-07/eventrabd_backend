import cloudinary.models

from decimal import Decimal

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import TimeStampedModel, UIDMixin
from apps.event_planner.constants import DIVISION_CHOICES
from apps.event_planner.utils import validate_image_size
from apps.users.models import User


class EventBrand(UIDMixin, TimeStampedModel):
    seller = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="event_brand",
        limit_choices_to={"role": "seller"},
    )

    display_name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        help_text="Unique public-facing display name in Bangla or English.",
    )

    brand_name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique public name for this event-service brand.",
    )

    logo = cloudinary.models.CloudinaryField(
        "brand_logo",
        blank=True,
        null=True,
    )

    slug = models.SlugField(
        max_length=255,
        unique=True,
        db_index=True,
        blank=True,
    )

    portfolio_link = models.URLField(
        blank=True,
        null=True,
        help_text="Optional Google Drive or YouTube portfolio URL.",
    )

    brand_name_last_changed = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the last brand_name change.",
    )

    whatsapp_number = models.CharField(
        max_length=30,
    )

    division = ArrayField(
        base_field=models.CharField(
            max_length=30,
            choices=DIVISION_CHOICES,
        ),
        default=list,
        blank=True,
        help_text="Divisions where this brand operates.",
    )
    
    office_address = models.TextField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Optional office or business address.",
    )

    short_description = models.TextField(
        max_length=500,
        blank=True,
        null=True,
    )

    rating_sum = models.PositiveBigIntegerField(
        default=0,
        editable=False,
    )

    review_count = models.PositiveBigIntegerField(
        default=0,
        editable=False,
    )

    class Meta:
        verbose_name = "Event Brand"
        verbose_name_plural = "Event Brands"
        ordering = ["-created_at"]

        indexes = [
            GinIndex(
                fields=["division"],
                name="eventbrand_divisions_gin",
            ),
        ]

    def __str__(self):
        return f"{self.brand_name} ({self.seller.full_name})"

    def save(self, *args, **kwargs):
        old_slug = None
        brand_name_changed = False

        if self.pk:
            try:
                previous = EventBrand.objects.get(pk=self.pk)
            except EventBrand.DoesNotExist:
                previous = None

            if previous and previous.brand_name != self.brand_name:
                brand_name_changed = True
                old_slug = previous.slug
                self.brand_name_last_changed = timezone.now()

        if not self.slug or brand_name_changed:
            base_slug = slugify(self.brand_name)
            slug = base_slug
            counter = 1

            while (
                EventBrand.objects
                .exclude(pk=self.pk)
                .filter(slug=slug)
                .exists()
            ):
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

        if old_slug and old_slug != self.slug:
            EventBrandSlugHistory.objects.get_or_create(
                brand=self,
                old_slug=old_slug,
            )

    def clean(self):
        super().clean()

        if hasattr(self.logo, "size"):
            validate_image_size(self.logo)

        if self.division:
            if len(self.division) != len(set(self.division)):
                raise ValidationError(
                    {
                        "division": "Duplicate divisions are not allowed."
                    }
                )

            if (
                "whole_bangladesh" in self.division
                and len(self.division) > 1
            ):
                raise ValidationError(
                    {
                        "division": (
                            "Whole Bangladesh cannot be selected "
                            "together with individual divisions."
                        )
                    }
                )

    @property
    def rating_count(self):
        return self.review_count

    @property
    def average_rating(self):
        if not self.review_count:
            return Decimal("0.00")

        return (
            Decimal(self.rating_sum)
            / Decimal(self.review_count)
            / Decimal("2")
        ).quantize(
            Decimal("0.01")
        )


class EventBrandSlugHistory(models.Model):
    brand = models.ForeignKey(
        EventBrand,
        on_delete=models.CASCADE,
        related_name="slug_history",
    )

    old_slug = models.SlugField(
        max_length=255,
        db_index=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]

        unique_together = [
            ("brand", "old_slug"),
        ]

    def __str__(self):
        return f"{self.old_slug} → {self.brand.slug}"