from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UIDMixin


class Membership(UIDMixin, TimeStampedModel):
    class MembershipType(models.TextChoices):
        BASIC = "basic", "Basic"
        PRO = "pro", "Pro"
        PLUS = "plus", "Plus"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="membership",
    )

    membership_type = models.CharField(
        max_length=10,
        choices=MembershipType.choices,
        default=MembershipType.BASIC,
        db_index=True,
    )

    def __str__(self):
        return (
            f"{self.user} - "
            f"{self.get_membership_type_display()}"
        )