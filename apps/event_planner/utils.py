import cloudinary
import cloudinary.uploader

from django.core.exceptions import ValidationError


MAX_IMAGE_SIZE = 5 * 1024 * 1024


def validate_image_size(image):
    """
    Validate uploaded image maximum size.
    """

    if image.size > MAX_IMAGE_SIZE:
        raise ValidationError(
            "Image size cannot exceed 5MB."
        )

    return image


def upload_brand_logo(image):
    """
    Upload and optimize brand logo using Cloudinary.
    """

    validate_image_size(image)

    result = cloudinary.uploader.upload(
        image,
        folder="eventra/brand_logos",

        # Optimization
        transformation=[
            {
                "width": 500,
                "height": 500,
                "crop": "limit",
            }
        ],

        quality="auto",
        fetch_format="auto",
    )

    return {
        "public_id": result.get("public_id"),
        "url": result.get("secure_url"),
    }