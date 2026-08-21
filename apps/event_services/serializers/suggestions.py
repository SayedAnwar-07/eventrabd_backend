from rest_framework import serializers

from apps.users.models import User
from apps.event_planner.models import EventBrand


class SellerSuggestionSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = User

        fields = [
            "id",
            "full_name",
        ]


class BrandSuggestionSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = EventBrand

        fields = [
            "id",
            "display_name",
        ]