from django.shortcuts import get_object_or_404

from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework import status

from apps.event_services.models import EventService
from apps.packages.models import (
    ServicePackage,
    PACKAGE_ALLOWED_SERVICE_TYPES,
)
from apps.packages.serializers import ServicePackageSerializer


class ServicePackageMixin:
    serializer_class = ServicePackageSerializer

    def get_service(self):
        if hasattr(self, "_service"):
            return self._service

        self._service = get_object_or_404(
            EventService.objects.select_related(
                "brand",
                "brand__seller",
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
        service = self.check_service_owner()

        if (
            service.service_name
            not in PACKAGE_ALLOWED_SERVICE_TYPES
        ):
            from rest_framework.exceptions import ValidationError

            raise ValidationError({
                "service": (
                    "Packages can only be created for "
                    "Photography and Videography services."
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