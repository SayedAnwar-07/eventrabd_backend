import re

import cloudinary.uploader


YOUTUBE_REGEX = re.compile(
    r"^(https?\:\/\/)?(www\.)?(youtube\.com|youtu\.be)\/.+$",
    re.IGNORECASE,
)

GOOGLE_DRIVE_REGEX = re.compile(
    r"^(https?\:\/\/)?(drive\.google\.com)\/.+$",
    re.IGNORECASE,
)


def is_google_drive_or_youtube_url(url: str) -> bool:
    if not url:
        return False
    return bool(YOUTUBE_REGEX.match(url) or GOOGLE_DRIVE_REGEX.match(url))


def safe_destroy_cloudinary_resource(resource) -> None:
    """
    Deletes a Cloudinary resource if it has a public_id.
    Safe for cover_photo and gallery image fields.
    """
    if not resource:
        return

    public_id = getattr(resource, "public_id", None)
    if not public_id:
        return

    try:
        cloudinary.uploader.destroy(public_id)
    except Exception:

        pass