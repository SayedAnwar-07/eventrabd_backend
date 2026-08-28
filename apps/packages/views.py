from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics, permissions
from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError,
)
from rest_framework.exceptions import PermissionDenied

from apps.event_services.models import EventService
from apps.packages.models import (
    ServicePackage,
    PACKAGE_ALLOWED_SERVICE_TYPES,
)
from apps.packages.serializers import ServicePackageSerializer
from apps.membership.models import Membership

BASIC_PACKAGE_LIMIT = 3

class ServicePackageMixin:
    serializer_class = ServicePackageSerializer

    def get_service(self):
        if hasattr(self, "_service"):
            return self._service

        self._service = get_object_or_404(
            EventService.objects.select_related(
                "brand",
                "brand__seller",
                "brand__seller__membership",
            ),
            id=self.kwargs.get("service_id"),
        )

        return self._service

    def get_queryset(self):
        return (
            ServicePackage.objects
            .select_related(
                "service",
                "service__brand",
                "service__brand__seller",
            )
            .filter(
                service=self.get_service(),
            )
            .order_by("created_at")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["service"] = self.get_service()
        return context

    def check_service_owner(self):
        service = self.get_service()

        if service.brand.seller_id != self.request.user.id:
            raise PermissionDenied(
                "You can only manage packages for your own service."
            )

        return service


class ServicePackageListCreateView(
    ServicePackageMixin,
    generics.ListCreateAPIView,
):
    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]

        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        with transaction.atomic():
            service = get_object_or_404(
                EventService.objects
                .select_for_update()
                .select_related(
                    "brand",
                    "brand__seller",
                    "brand__seller__membership",
                ),
                id=self.kwargs.get("service_id"),
            )

            if service.brand.seller_id != self.request.user.id:
                raise PermissionDenied(
                    "You can only manage packages "
                    "for your own service."
                )

            if (
                service.service_name
                not in PACKAGE_ALLOWED_SERVICE_TYPES
            ):
                raise ValidationError({
                    "service": (
                        "Packages can only be created for "
                        "Photography and Videography services."
                    )
                })

            try:
                membership_type = (
                    service.brand
                    .seller
                    .membership
                    .membership_type
                )
            except Membership.DoesNotExist:
                membership_type = (
                    Membership.MembershipType.BASIC
                )

            if (
                membership_type
                == Membership.MembershipType.BASIC
            ):
                package_count = (
                    ServicePackage.objects
                    .filter(service_id=service.id)
                    .count()
                )

                if package_count >= BASIC_PACKAGE_LIMIT:
                    raise ValidationError({
                        "package": (
                            "Your Basic membership allows "
                            "a maximum of 3 packages for "
                            "this service."
                        )
                    })

            serializer.save(
                service=service,
            )


class ServicePackageDetailView(
    ServicePackageMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    lookup_url_kwarg = "package_id"

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]

        return [permissions.IsAuthenticated()]

    def perform_update(self, serializer):
        self.check_service_owner()
        serializer.save()

    def perform_destroy(self, instance):
        self.check_service_owner()
        instance.delete()