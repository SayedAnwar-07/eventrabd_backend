from django.db import transaction
from rest_framework import serializers

from apps.event_planner.models import EventBrand
from apps.event_services.models import (
    EventService,
    ServiceGalleryImage,
    ServiceType,
    SERVICE_IMAGE_LIMITS,
)
from apps.event_services.utils import (
    is_google_drive_or_youtube_url,
    safe_destroy_cloudinary_resource,
)


class EventBrandMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventBrand
        fields = ["id", "brand_name", "slug", "service_area"]


class ServiceGalleryImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ServiceGalleryImage
        fields = ["id", "image_url", "sort_order", "created_at"]

    def get_image_url(self, obj):
        try:
            return obj.image.url
        except Exception:
            return None


class EventServiceSerializer(serializers.ModelSerializer):
    brand = EventBrandMiniSerializer(read_only=True)
    brand_id = serializers.PrimaryKeyRelatedField(
        queryset=EventBrand.objects.all(),
        write_only=True,
        source="brand",
        required=True,
    )

    cover_photo_url = serializers.SerializerMethodField()
    gallery_images = ServiceGalleryImageSerializer(many=True, read_only=True)
    image_limit = serializers.SerializerMethodField()

    add_gallery_images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False,
        allow_empty=False,
    )

    remove_gallery_image_ids = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        required=False,
        allow_empty=False,
    )

    cover_photo = serializers.ImageField(
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = EventService
        fields = [
            "id",
            "brand",
            "brand_id",
            "service_name",
            "slug",
            "cover_photo",
            "cover_photo_url",
            "drive_link",
            "shift_charge",
            "description",
            "shift_hour",
            "sound_system_payment",
            "lighting_payment",
            "gallery_images",
            "image_limit",
            "add_gallery_images",
            "remove_gallery_image_ids",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]

    def get_cover_photo_url(self, obj):
        try:
            return obj.cover_photo.url if obj.cover_photo else None
        except Exception:
            return None

    def get_image_limit(self, obj):
        return obj.image_limit

    def validate_brand(self, brand):
        request = self.context["request"]
        if request.method in ["POST", "PATCH", "PUT", "DELETE"]:
            if brand.seller_id != request.user.id:
                raise serializers.ValidationError(
                    "You can only create services for your own brand."
                )
        return brand

    def validate_drive_link(self, value):
        if value and not is_google_drive_or_youtube_url(value):
            raise serializers.ValidationError(
                "Only Google Drive or YouTube URL is allowed."
            )
        return value

    def validate(self, attrs):
        service_name = attrs.get("service_name")
        brand = attrs.get("brand")

        if self.instance:
            service_name = service_name or self.instance.service_name
            brand = brand or self.instance.brand

        if not service_name:
            raise serializers.ValidationError({"service_name": "This field is required."})

        drive_link = attrs.get("drive_link", getattr(self.instance, "drive_link", None))
        shift_hour = attrs.get("shift_hour", getattr(self.instance, "shift_hour", None))
        sound_system_payment = attrs.get(
            "sound_system_payment",
            getattr(self.instance, "sound_system_payment", None),
        )
        lighting_payment = attrs.get(
            "lighting_payment",
            getattr(self.instance, "lighting_payment", None),
        )

        errors = {}

        if service_name == ServiceType.PHOTOGRAPHY:
            if not shift_hour:
                errors["shift_hour"] = "shift_hour is required for Photography."

        elif service_name == ServiceType.VIDEOGRAPHY:
            if not shift_hour:
                errors["shift_hour"] = "shift_hour is required for Videography."
            if not drive_link:
                errors["drive_link"] = "drive_link is required for Videography."

        elif service_name == ServiceType.SOUND_LIGHTING:
            if sound_system_payment is None:
                errors["sound_system_payment"] = "sound_system_payment is required."
            if lighting_payment is None:
                errors["lighting_payment"] = "lighting_payment is required."

        elif service_name == ServiceType.DJ:
            if not shift_hour:
                errors["shift_hour"] = "shift_hour is required for DJ."

        # one service per type per brand
        if brand and service_name:
            qs = EventService.objects.filter(brand=brand, service_name=service_name)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                errors["service_name"] = "This brand already has this service type."

        # gallery image limit validation
        add_gallery_images = attrs.get("add_gallery_images", [])
        remove_gallery_image_ids = attrs.get("remove_gallery_image_ids", [])

        max_allowed = SERVICE_IMAGE_LIMITS.get(service_name, 0)

        current_count = 0
        if self.instance:
            current_count = self.instance.gallery_images.count()

            if remove_gallery_image_ids:
                current_count -= self.instance.gallery_images.filter(
                    id__in=remove_gallery_image_ids
                ).count()

        final_count = current_count + len(add_gallery_images)

        if final_count > max_allowed:
            errors["add_gallery_images"] = (
                f"Maximum {max_allowed} gallery images allowed for "
                f"{dict(ServiceType.choices).get(service_name)}."
            )

        if max_allowed == 0 and add_gallery_images:
            errors["add_gallery_images"] = (
                f"{dict(ServiceType.choices).get(service_name)} does not support gallery images."
            )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        add_gallery_images = validated_data.pop("add_gallery_images", [])
        validated_data.pop("remove_gallery_image_ids", None)

        service = EventService.objects.create(**validated_data)

        for idx, image_file in enumerate(add_gallery_images, start=1):
            ServiceGalleryImage.objects.create(
                service=service,
                image=image_file,
                sort_order=idx,
            )

        return service

    @transaction.atomic
    def update(self, instance, validated_data):
        add_gallery_images = validated_data.pop("add_gallery_images", [])
        remove_gallery_image_ids = validated_data.pop("remove_gallery_image_ids", [])

        new_cover_photo = validated_data.pop("cover_photo", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if new_cover_photo is not None:
            if instance.cover_photo:
                safe_destroy_cloudinary_resource(instance.cover_photo)
            instance.cover_photo = new_cover_photo

        instance.save()

        if remove_gallery_image_ids:
            images_to_delete = instance.gallery_images.filter(id__in=remove_gallery_image_ids)
            for image in images_to_delete:
                safe_destroy_cloudinary_resource(image.image)
                image.delete()

        if add_gallery_images:
            last_order = (
                instance.gallery_images.order_by("-sort_order")
                .values_list("sort_order", flat=True)
                .first()
                or 0
            )

            for offset, image_file in enumerate(add_gallery_images, start=1):
                ServiceGalleryImage.objects.create(
                    service=instance,
                    image=image_file,
                    sort_order=last_order + offset,
                )

        return instance