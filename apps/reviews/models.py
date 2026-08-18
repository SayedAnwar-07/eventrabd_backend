from decimal import Decimal

from cloudinary.models import CloudinaryField

from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError,
)
from django.db import models

from PIL import Image, UnidentifiedImageError

from apps.core.models import TimeStampedModel, UIDMixin
from apps.hires.models import Hire, HireStatus


MAX_REVIEW_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB

ALLOWED_REVIEW_IMAGE_FORMATS = {
    "JPEG",
    "PNG",
    "WEBP",
}


class ReviewRating(models.IntegerChoices):
    ONE_STAR = 2, "1.0"
    ONE_HALF_STAR = 3, "1.5"
    TWO_STAR = 4, "2.0"
    TWO_HALF_STAR = 5, "2.5"
    THREE_STAR = 6, "3.0"
    THREE_HALF_STAR = 7, "3.5"
    FOUR_STAR = 8, "4.0"
    FOUR_HALF_STAR = 9, "4.5"
    FIVE_STAR = 10, "5.0"


def validate_review_image(value):
    """
    Validate newly uploaded review images.

    Rules:
    - Maximum 5 MB
    - JPEG, PNG or WEBP only

    Existing Cloudinary resources are skipped because
    they were already validated during upload.
    """

    if not value:
        return

    if not hasattr(value, "read"):
        return

    size = getattr(value, "size", None)

    if size is not None and size > MAX_REVIEW_IMAGE_SIZE:
        raise ValidationError(
            "Review image cannot be larger than 5 MB."
        )

    original_position = None

    try:
        if hasattr(value, "tell"):
            original_position = value.tell()

        image = Image.open(value)

        image_format = image.format

        image.verify()

    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as error:
        raise ValidationError(
            "Upload a valid JPEG, PNG, or WEBP image."
        ) from error

    finally:
        if hasattr(value, "seek"):
            try:
                value.seek(
                    original_position
                    if original_position is not None
                    else 0
                )
            except (OSError, ValueError):
                pass

    if image_format not in ALLOWED_REVIEW_IMAGE_FORMATS:
        raise ValidationError(
            "Only JPEG, PNG, or WEBP images are allowed."
        )


class Review(UIDMixin, TimeStampedModel):
    """
    A review submitted for one completed hire.

    Relationship path:

        review.hire
        review.hire.customer
        review.hire.service
        review.hire.service.brand

    Since one Hire belongs to exactly one customer and one service,
    customer/service/brand are not duplicated in this model.
    """

    hire = models.OneToOneField(
        Hire,
        on_delete=models.PROTECT,
        related_name="review",
        help_text=(
            "The completed hire this review belongs to."
        ),
    )

    rating = models.PositiveSmallIntegerField(
        choices=ReviewRating.choices,
        help_text=(
            "Internal half-star representation: "
            "2 = 1 star and 10 = 5 stars."
        ),
    )

    comment = models.TextField(
        blank=True,
        default="",
    )

    image = CloudinaryField(
        "review_image",
        blank=True,
        null=True,
        validators=[
            validate_review_image,
        ],
    )

    class Meta:
        verbose_name = "Review"
        verbose_name_plural = "Reviews"

        ordering = [
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=["-created_at"],
                name="review_created_desc_idx",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    rating__gte=2,
                    rating__lte=10,
                ),
                name="review_rating_between_2_and_10",
            ),
        ]

    def __str__(self):
        return (
            f"{self.hire.customer.full_name} - "
            f"{self.hire.service.get_service_name_display()} - "
            f"{self.stars} stars"
        )

    @property
    def customer(self):
        return self.hire.customer

    @property
    def service(self):
        return self.hire.service

    @property
    def brand(self):
        return self.hire.service.brand

    @property
    def stars(self):
        """
        Convert the internal integer representation
        to the public star value.

        Example:
            9 -> Decimal("4.5")
        """

        return Decimal(self.rating) / Decimal("2")

    def clean(self):
        super().clean()

        if not self.hire_id:
            return

        errors = {}

        if self.hire.status != HireStatus.COMPLETED:
            errors["hire"] = (
                "This hire must be completed before "
                "a review can be submitted."
            )

        try:
            invoice = self.hire.invoice

        except ObjectDoesNotExist:
            invoice = None

            errors["hire"] = (
                "This hire does not have an invoice."
            )

        if (
            invoice is not None
            and invoice.customer_agreed is not True
        ):
            errors["hire"] = (
                "The customer must agree to the invoice "
                "before submitting a review."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()

        return super().save(
            *args,
            **kwargs,
        )