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