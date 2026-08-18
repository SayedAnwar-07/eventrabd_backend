from rest_framework import serializers

from apps.event_services.models import (
    ServiceGalleryImage,
)


class ServiceGalleryImageSerializer(
    serializers.ModelSerializer
):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ServiceGalleryImage

        fields = [
            "id",
            "image_url",
            "sort_order",
            "created_at",
        ]

        read_only_fields = fields

    def get_image_url(self, obj):
        if not obj.image:
            return None

        try:
            return obj.image.url
        except Exception:
            return None