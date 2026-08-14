from rest_framework import serializers

from apps.packages.models import (
    ServicePackage,
    PACKAGE_ALLOWED_SERVICE_TYPES,
)


class ServicePackageSerializer(serializers.ModelSerializer):
    service_id = serializers.CharField(
        source="service.id",
        read_only=True,
    )

    service_name = serializers.CharField(
        source="service.service_name",
        read_only=True,
    )

    service_display_name = serializers.CharField(
        source="service.get_service_name_display",
        read_only=True,
    )

    class Meta:
        model = ServicePackage
        fields = [
            "id",
            "service_id",
            "service_name",
            "service_display_name",
            "package_title",
            "package_price",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "service_id",
            "service_name",
            "service_display_name",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        service = self.context.get("service")

        if self.instance:
            service = self.instance.service

        if not service:
            raise serializers.ValidationError({
                "service": "Service is required."
            })

        if (
            service.service_name
            not in PACKAGE_ALLOWED_SERVICE_TYPES
        ):
            raise serializers.ValidationError({
                "service": (
                    "Packages are only allowed for "
                    "Photography and Videography services."
                )
            })

        return attrs