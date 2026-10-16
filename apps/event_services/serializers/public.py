from decimal import Decimal

from django.core.cache import cache

from rest_framework import serializers

from apps.event_planner.models import EventBrand

from apps.event_services.models import (
    EventService,
    COVER_PHOTO_ONLY_SERVICE_TYPES,
)

from apps.event_services.serializers.common import (
    ServiceGalleryImageSerializer,
)


IMAGE_CACHE_TIMEOUT = 86400


# =========================================================
# Public Seller Serializer
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

    profile_image_url = serializers.SerializerMethodField()


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


    def get_profile_image_url(self, obj):

        seller = obj.seller

        if not seller.profile_image:
            return None


        cache_key = (
            f"seller_profile:{seller.id}"
        )


        url = cache.get(cache_key)


        if url:
            return url


        try:

            url = seller.profile_image.build_url(
                transformation=[
                    {
                        "width":500,
                        "height":500,
                        "crop":"limit",
                    }
                ],
                quality="auto",
                fetch_format="auto",
            )


            cache.set(
                cache_key,
                url,
                IMAGE_CACHE_TIMEOUT,
            )


            return url


        except Exception:
            return None



# =========================================================
# Public Brand Serializer
# =========================================================

class PublicServiceBrandSerializer(
    serializers.ModelSerializer
):

    logo_url = serializers.SerializerMethodField()

    rating = serializers.SerializerMethodField()


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
        ]


        read_only_fields = fields



    def get_logo_url(self,obj):

        if not obj.logo:
            return None


        cache_key = (
            f"brand_logo:{obj.id}"
        )


        url = cache.get(cache_key)


        if url:
            return url



        try:

            url = obj.logo.build_url(
                transformation=[
                    {
                        "width":300,
                        "height":300,
                        "crop":"limit",
                    }
                ],
                quality="auto",
                fetch_format="auto",
            )


            cache.set(
                cache_key,
                url,
                IMAGE_CACHE_TIMEOUT,
            )


            return url


        except Exception:
            return None



    def get_rating(self,obj):

        if not obj.review_count:
            return Decimal("0.00")


        return (
            Decimal(obj.rating_sum)
            /
            Decimal(obj.review_count)
            /
            Decimal("2")
        ).quantize(
            Decimal("0.01")
        )



# =========================================================
# Public Event Service Card
# =========================================================

class PublicEventServiceCardSerializer(
    serializers.ModelSerializer
):


    service_display_name = serializers.CharField(
        source="get_service_name_display",
        read_only=True,
    )


    rating = serializers.DecimalField(
        source="average_rating",
        max_digits=3,
        decimal_places=2,
        read_only=True,
    )


    cover_photo_url = serializers.SerializerMethodField()


    gallery_images = serializers.SerializerMethodField()



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



    def get_cover_photo_url(self,obj):

        if (
            obj.service_name
            not in COVER_PHOTO_ONLY_SERVICE_TYPES
        ):
            return None


        if not obj.cover_photo:
            return None



        cache_key = (
            f"service_cover:{obj.id}"
        )



        url = cache.get(cache_key)


        if url:
            return url



        try:

            url = obj.cover_photo.url


            cache.set(
                cache_key,
                url,
                IMAGE_CACHE_TIMEOUT,
            )


            return url


        except Exception:
            return None




    def get_gallery_images(self,obj):


        if (
            obj.service_name
            in COVER_PHOTO_ONLY_SERVICE_TYPES
        ):
            return []



        images = getattr(
            obj,
            "prefetched_gallery_images",
            []
        )



        return ServiceGalleryImageSerializer(
            images,
            many=True,
        ).data