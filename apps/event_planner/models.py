# models.py
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import TimeStampedModel, UIDMixin
from apps.users.models import User


class EventBrand(UIDMixin, TimeStampedModel):
    seller = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="event_brand",
        limit_choices_to={"role": "seller"},
    )

    brand_name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique public name for this event-service brand.",
    )

    slug = models.SlugField(
        max_length=255,
        unique=True,
        db_index=True,
        blank=True,
    )

    # Tracks when brand_name was last changed — used for 60-day lock
    brand_name_last_changed = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the last brand_name change.",
    )

    whatsapp_number = models.CharField(max_length=30)

    service_area = models.CharField(
        max_length=255,
        help_text="City / region this brand primarily operates in.",
    )

    short_description = models.TextField(
        max_length=500,
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Event Brand"
        verbose_name_plural = "Event Brands"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.brand_name} ({self.seller.full_name})"

    def save(self, *args, **kwargs):
        # --- Detect brand_name change on existing instances ---
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

        # --- Generate a new slug when blank OR when brand_name changed ---
        if not self.slug or brand_name_changed:
            base_slug = slugify(self.brand_name)
            slug = base_slug
            counter = 1
            while EventBrand.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        super().save(*args, **kwargs)

        # --- Record old slug in history so old URLs can redirect ---
        if old_slug and old_slug != self.slug:
            EventBrandSlugHistory.objects.get_or_create(
                brand=self,
                old_slug=old_slug,
            )


class EventBrandSlugHistory(models.Model):
    brand = models.ForeignKey(
        EventBrand,
        on_delete=models.CASCADE,
        related_name="slug_history",
    )
    old_slug = models.SlugField(max_length=255, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        # Prevent duplicate history entries for the same (brand, old_slug)
        unique_together = [("brand", "old_slug")]

    def __str__(self):
        return f"{self.old_slug} → {self.brand.slug}"