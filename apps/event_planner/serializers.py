from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.event_planner.utils import validate_image_size
from apps.users.models import User
from .models import EventBrand
from apps.event_services.models import EventService,ServiceGalleryImage, COVER_PHOTO_ONLY_SERVICE_TYPES


class SellerInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "username",
            "email",
            "profile_image_url",
            "contact_number",
            "office_address",
        ]
        read_only_fields = fields


class BrandGalleryImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ServiceGalleryImage
        fields = [
            "id",
            "image_url",
            "sort_order",
            "created_at",
        ]

    def get_image_url(self, obj):
        try:
            return obj.image.url if obj.image else None
        except Exception:
            return None


class BrandServiceSerializer(serializers.ModelSerializer):
    cover_photo_url = serializers.SerializerMethodField()
    gallery_images = serializers.SerializerMethodField()
    image_limit = serializers.SerializerMethodField()

    class Meta:
        model = EventService
        fields = [
            "id",
            "service_name",
            "slug",
            "cover_photo_url",
            "drive_link",
            "shift_charge",
            "description",
            "shift_hour",
            "sound_system_payment",
            "lighting_payment",
            "gallery_images",
            "image_limit",
            "created_at",
            "updated_at",
        ]

    def get_cover_photo_url(self, obj):
        if obj.service_name not in COVER_PHOTO_ONLY_SERVICE_TYPES:
            return None

        try:
            return obj.cover_photo.url if obj.cover_photo else None
        except Exception:
            return None

    def get_gallery_images(self, obj):
        if obj.service_name in COVER_PHOTO_ONLY_SERVICE_TYPES:
            return []

        return BrandGalleryImageSerializer(
            obj.gallery_images.all().order_by("sort_order", "-created_at"),
            many=True,
        ).data

    def get_image_limit(self, obj):
        return obj.image_limit


class EventBrandSerializer(serializers.ModelSerializer):
    seller_info = SellerInfoSerializer(
        source="seller",
        read_only=True,
    )

    services = BrandServiceSerializer(
        many=True,
        read_only=True,
    )

    is_owner = serializers.SerializerMethodField()

    logo_url = serializers.SerializerMethodField()


    class Meta:
        model = EventBrand

        fields = [
            "id",
            "brand_name",
            "slug",
            "logo",
            "logo_url",
            "whatsapp_number",
            "service_area",
            "short_description",
            "seller_info",
            "services",
            "is_owner",
            "created_at",
            "updated_at",
        ]



    def get_logo_url(self, obj):

        if not obj.logo:
            return None

        try:
            return obj.logo.build_url(
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



    def validate_logo(self, value):

        if value:
            validate_image_size(value)

        return value



    def get_is_owner(self, obj):

        request = self.context.get("request")

        if not request or request.user.is_anonymous:
            return False

        return obj.seller_id == request.user.id



    def validate_brand_name(self, value):

        if self.instance and self.instance.brand_name != value:

            last_changed = self.instance.brand_name_last_changed

            if last_changed:

                diff = timezone.now() - last_changed

                if diff < timedelta(days=60):

                    remaining = 60 - diff.days

                    raise serializers.ValidationError(
                        f"You can change brand name after {remaining} more day(s)."
                    )


        qs = EventBrand.objects.filter(
            brand_name__iexact=value
        )


        if self.instance:
            qs = qs.exclude(
                pk=self.instance.pk
            )


        if qs.exists():

            raise serializers.ValidationError(
                "This brand name is already taken."
            )
        return value

    def validate(self, attrs):

        request = self.context.get("request")

        if (
            not self.instance
            and request
            and request.user.is_authenticated
        ):

            if EventBrand.objects.filter(
                seller=request.user
            ).exists():

                raise serializers.ValidationError(
                    {
                        "non_field_errors": "You already have a brand."
                    }
                )
        return attrs

    def create(self, validated_data):

        request = self.context["request"]

        validated_data["seller"] = request.user

        return super().create(validated_data)


class BrandListServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventService
        fields = [
            "id",
            "service_name",
        ]
        
        
class EventBrandListSerializer(serializers.ModelSerializer):
    seller_name = serializers.CharField(
        source="seller.full_name",
        read_only=True,
    )

    seller_profile = serializers.CharField(
        source="seller.profile_image_url",
        read_only=True,
    )

    services = BrandListServiceSerializer(
        many=True,
        read_only=True,
    )

    total_services = serializers.SerializerMethodField()

    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = EventBrand
        fields = [
            "id",
            "brand_name",
            "logo_url",
            "slug",
            "service_area",
            "short_description",
            "seller_name",
            "seller_profile",
            "total_services",
            "services",
        ]

    def get_logo_url(self, obj):
        if not obj.logo:
            return None

        try:
            return obj.logo.url
        except Exception:
            return None

    def get_total_services(self, obj):
        return obj.services.count()