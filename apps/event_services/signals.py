
from django.db.models.signals import (
    pre_save,
    post_save,
    post_delete,
)
from django.dispatch import receiver

from apps.users.models import User
from apps.event_planner.models import EventBrand

from apps.event_services.models import (
    EventService,
    ServiceGalleryImage,
)
from django.db import transaction

from apps.event_services.cache_utils import (
    invalidate_public_services_cache,
)


# =====================================================
# SELLER PROFILE CHANGE DETECTION
# =====================================================

@receiver(
    pre_save,
    sender=User,
    dispatch_uid="track_public_seller_profile_changes",
)
def track_seller_profile_changes(
    sender,
    instance,
    **kwargs,
):

    if not instance.pk:
        instance._public_profile_changed = False
        return

    old_data = (
        User.objects
        .filter(pk=instance.pk)
        .values(
            "full_name",
            "profile_image",
            "contact_number",
        )
        .first()
    )

    if not old_data:
        instance._public_profile_changed = False
        return

    current_image = getattr(
        instance.profile_image,
        "name",
        instance.profile_image,
    )

    instance._public_profile_changed = (
        old_data["full_name"] != instance.full_name
        or old_data["profile_image"] != current_image
        or old_data["contact_number"] != instance.contact_number
    )


@receiver(
    post_save,
    sender=User,
    dispatch_uid="invalidate_services_after_seller_profile_update",
)
def invalidate_after_seller_profile_update(
    sender,
    instance,
    **kwargs,
):

    if getattr(
        instance,
        "_public_profile_changed",
        False,
    ):

        transaction.on_commit(
            invalidate_public_services_cache
        )

    instance._public_profile_changed = False


# =====================================================
# BRAND CHANGE
# =====================================================

@receiver(
    post_save,
    sender=EventBrand,
    dispatch_uid="invalidate_services_after_brand_update",
)
@receiver(
    post_delete,
    sender=EventBrand,
    dispatch_uid="invalidate_services_after_brand_delete",
)
def invalidate_after_brand_change(
    sender,
    instance,
    **kwargs,
):

    invalidate_public_services_cache()


# =====================================================
# SERVICE CHANGE
# =====================================================

@receiver(
    post_save,
    sender=EventService,
    dispatch_uid="invalidate_services_after_service_update",
)
@receiver(
    post_delete,
    sender=EventService,
    dispatch_uid="invalidate_services_after_service_delete",
)
def invalidate_after_service_change(
    sender,
    instance,
    **kwargs,
):

    invalidate_public_services_cache()


# =====================================================
# GALLERY IMAGE CHANGE
# =====================================================

@receiver(
    post_save,
    sender=ServiceGalleryImage,
    dispatch_uid="invalidate_services_after_gallery_update",
)
@receiver(
    post_delete,
    sender=ServiceGalleryImage,
    dispatch_uid="invalidate_services_after_gallery_delete",
)
def invalidate_after_gallery_change(
    sender,
    instance,
    **kwargs,
):

    invalidate_public_services_cache()
