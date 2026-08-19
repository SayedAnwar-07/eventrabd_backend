from decimal import Decimal

from rest_framework import serializers

from apps.event_planner.models import EventBrand

from apps.event_services.models import (
    EventService,
    COVER_PHOTO_ONLY_SERVICE_TYPES,
)

from apps.event_services.serializers.common import (
    ServiceGalleryImageSerializer,
)


# =========================================================
# Public seller
# =========================================================


class PublicServiceSellerSerializer(
    serializers.ModelSerializer
):
    id = serializers.CharField(
        source="seller.id",
        read_only=True,
    )

    full_name = serializers.CharField(
        source="seller.full_name",
        read_only=True,
    )

    contact_number = serializers.CharField(
        source="seller.contact_number",
        read_only=True,
    )

    profile_image_url = (
        serializers.SerializerMethodField()
    )

    class Meta:
        model = EventBrand

        fields = [
            "id",
            "full_name",
            "profile_image_url",
            "whatsapp_number",
            "contact_number",
        ]

        read_only_fields = fields

    def get_profile_image_url(
        self,
        obj,
    ):
        seller = obj.seller

        if not seller.profile_image:
            return None

        try:
            return seller.profile_image.build_url(
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

        except Exception:
            return None


# =========================================================
# Public brand
# =========================================================


class PublicServiceBrandSerializer(
    serializers.ModelSerializer
):
    logo_url = (
        serializers.SerializerMethodField()
    )

    rating = (
        serializers.SerializerMethodField()
    )

    is_owner = (
        serializers.SerializerMethodField()
    )

    class Meta:
        model = EventBrand

        fields = [
            "id",
            "display_name",
            "brand_name",
            "slug",
            "logo_url",
            "division",
            "office_address",
            "rating",
            "review_count",
            "is_owner",
        ]

        read_only_fields = fields

    # =====================================================
    # Owner
    # =====================================================

    def get_is_owner(
        self,
        obj,
    ):
        request = self.context.get(
            "request"
        )

        if (
            not request
            or not request.user.is_authenticated
        ):
            return False

        return (
            getattr(
                request.user,
                "role",
                None,
            )
            == "seller"
            and obj.seller_id == request.user.id
        )

    # =====================================================
    # Logo
    # =====================================================

    def get_logo_url(
        self,
        obj,
    ):
        if not obj.logo:
            return None

        try:
            return obj.logo.build_url(
                transformation=[
                    {
                        "width": 300,
                        "height": 300,
                        "crop": "limit",
                    }
                ],
                quality="auto",
                fetch_format="auto",
            )

        except Exception:
            return None

    # =====================================================
    # Brand rating
    # =====================================================

    def get_rating(
        self,
        obj,
    ):
        if not obj.review_count:
            return Decimal("0.00")

        return (
            Decimal(obj.rating_sum)
            / Decimal(obj.review_count)
            / Decimal("2")
        ).quantize(
            Decimal("0.01")
        )

# =========================================================
# Public service card
# =========================================================


class PublicEventServiceCardSerializer(
    serializers.ModelSerializer
):
    service_display_name = (
        serializers.CharField(
            source="get_service_name_display",
            read_only=True,
        )
    )

    rating = serializers.DecimalField(
        source="average_rating",
        max_digits=3,
        decimal_places=2,
        read_only=True,
    )

    cover_photo_url = (
        serializers.SerializerMethodField()
    )

    gallery_images = (
        serializers.SerializerMethodField()
    )

    seller = PublicServiceSellerSerializer(
        source="brand",
        read_only=True,
    )

    brand = PublicServiceBrandSerializer(
        read_only=True,
    )

    class Meta:
        model = EventService

        fields = [
            "id",
            "service_name",
            "service_display_name",
            "slug",

            "shift_charge",
            "shift_hour",

            "rating",
            "review_count",

            "cover_photo_url",
            "gallery_images",

            "seller",
            "brand",
        ]

        read_only_fields = fields

    # =====================================================
    # Cover photo
    # =====================================================

    def get_cover_photo_url(
        self,
        obj,
    ):
        if (
            obj.service_name
            not in COVER_PHOTO_ONLY_SERVICE_TYPES
        ):
            return None

        try:
            return (
                obj.cover_photo.url
                if obj.cover_photo
                else None
            )

        except Exception:
            return None

    # =====================================================
    # Gallery
    # =====================================================

    def get_gallery_images(
        self,
        obj,
    ):
        if (
            obj.service_name
            in COVER_PHOTO_ONLY_SERVICE_TYPES
        ):
            return []

        return ServiceGalleryImageSerializer(
            obj.gallery_images.all(),
            many=True,
        ).data