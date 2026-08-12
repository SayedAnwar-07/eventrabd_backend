import unicodedata
from django.db import IntegrityError

from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from apps.event_services.utils import is_google_drive_or_youtube_url

from apps.event_planner.utils import validate_image_size
from apps.users.models import User
from .models import EventBrand
from apps.event_services.models import EventService, ServiceGalleryImage, COVER_PHOTO_ONLY_SERVICE_TYPES
from apps.event_planner.constants import DIVISION_CHOICES, DIVISION_DISTRICTS
import re
from django.utils.text import slugify


class SellerInfoSerializer(serializers.ModelSerializer):
    profile_image_url = serializers.SerializerMethodField()

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


    def get_profile_image_url(self, obj):
        if not obj.profile_image:
            return None

        try:
            return obj.profile_image.build_url(
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
    rating = serializers.DecimalField(
        source="average_rating",
        max_digits=3,
        decimal_places=2,
        read_only=True,
    )

    rating_count = serializers.IntegerField(
        read_only=True,
    )

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
            "rating",
            "rating_count",
            "review_count",
            "shift_hour",
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

    division = serializers.ChoiceField(choices=DIVISION_CHOICES)
    district = serializers.CharField()
    display_name = serializers.CharField(max_length=255) 
    
    rating = serializers.DecimalField(
        source="average_rating",
        max_digits=3,
        decimal_places=2,
        read_only=True,
    )

    rating_count = serializers.IntegerField(
        read_only=True,
    )

    class Meta:
        model = EventBrand

        fields = [
            "id",
            "display_name",
            "brand_name",
            "slug",
            "logo",
            "logo_url",
            "portfolio_link",
            "whatsapp_number",
            "division",
            "district",
            "short_description",
            "rating",
            "rating_count",
            "review_count",
            "seller_info",
            "services",
            "is_owner",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]
        extra_kwargs = {
            "logo": {"write_only": True},
            "brand_name": {"validators": []}, 
        }

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
    
    def validate_portfolio_link(self, value):
        if value and not is_google_drive_or_youtube_url(value):
            raise serializers.ValidationError(
                "Only Google Drive or YouTube URL is allowed."
            )

        return value

    def get_is_owner(self, obj):
        request = self.context.get("request")

        if not request or request.user.is_anonymous:
            return False

        return obj.seller_id == request.user.id

    def validate_brand_name(self, value):
        # Only allow English letters, numbers, spaces, and basic
        # punctuation (- & . ' ,) — no Bangla or other scripts
        if not re.match(r"^[A-Za-z0-9\s\-\&\.\',]+$", value):
            raise serializers.ValidationError(
                "Brand name must be in English only. Other languages are not allowed."
            )

        if self.instance and self.instance.brand_name != value:
            last_changed = self.instance.brand_name_last_changed

            if last_changed:
                diff = timezone.now() - last_changed

                if diff < timedelta(days=60):
                    remaining = 60 - diff.days

                    raise serializers.ValidationError(
                        f"You can change brand name after {remaining} more day(s)."
                    )

        qs = EventBrand.objects.filter(brand_name__iexact=value)

        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError("This brand username is already taken.")

        # Also block names that would collide once slugified,
        # e.g. "Drissayoner Golpo" vs "Drissayoner-Golpo" —
        # different strings, same resulting slug.
        new_slug = slugify(value)

        slug_qs = EventBrand.objects.filter(slug=new_slug)

        if self.instance:
            slug_qs = slug_qs.exclude(pk=self.instance.pk)

        if slug_qs.exists():
            raise serializers.ValidationError("This brand username is already taken.")

        return value
    
    def validate_display_name(self, value):
        # Unicode normalize (NFC) so visually-identical Bangla text
        # with different combining-character sequences match as duplicates
        value = unicodedata.normalize("NFC", value.strip())
        value = " ".join(value.split())

        if not value:
            raise serializers.ValidationError("Display name cannot be empty.")

        qs = EventBrand.objects.filter(display_name__iexact=value)

        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "This name already exists, try a new one."
            )

        return value

    def validate_district(self, value):
        # Case-insensitive match against the canonical district name so that
        # "dhaka" / "DHAKA" / "Dhaka" all resolve the same way.
        for districts in DIVISION_DISTRICTS.values():
            for district in districts:
                if district.lower() == value.strip().lower():
                    return district

        raise serializers.ValidationError(f"{value} is not a recognized district.")

    def validate(self, attrs):
        request = self.context.get("request")

        if not self.instance and request and request.user.is_authenticated:
            if EventBrand.objects.filter(seller=request.user).exists():
                raise serializers.ValidationError(
                    {"non_field_errors": "You already have a brand."}
                )

        division = attrs.get("division", getattr(self.instance, "division", None))
        district = attrs.get("district", getattr(self.instance, "district", None))

        if division and district:
            valid_districts = DIVISION_DISTRICTS.get(division, [])
            if district not in valid_districts:
                raise serializers.ValidationError(
                    {
                        "district": f"{district} is not a district of {division.title()} division."
                    }
                )

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["seller"] = request.user

        try:
            return super().create(validated_data)
        except IntegrityError:
            raise serializers.ValidationError(
                {"display_name": "This name already exists, try a new one."}
            )


class BrandListServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventService
        fields = [
            "id",
            "service_name",
        ]


class EventBrandListSerializer(serializers.ModelSerializer):
    seller_info = SellerInfoSerializer(
        source="seller",
        read_only=True,
    )

    services = BrandListServiceSerializer(
        many=True,
        read_only=True,
    )

    total_services = serializers.SerializerMethodField()

    logo_url = serializers.SerializerMethodField()

    is_owner = serializers.SerializerMethodField()
    
    rating = serializers.DecimalField(
        source="average_rating",
        max_digits=3,
        decimal_places=2,
        read_only=True,
    )

    rating_count = serializers.IntegerField(
        read_only=True,
    )

    class Meta:
        model = EventBrand
        fields = [
            "id",
            "display_name",
            "brand_name",
            "slug",
            "logo_url",
            "whatsapp_number",
            "division",
            "district",
            "short_description",
            "rating",
            "rating_count",
            "review_count",
            "seller_info",
            "services",
            "total_services",
            "is_owner",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_logo_url(self, obj):
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

    def get_total_services(self, obj):
        return obj.services.count()

    def get_is_owner(self, obj):
        request = self.context.get("request")

        if not request or request.user.is_anonymous:
            return False

        return obj.seller_id == request.user.id