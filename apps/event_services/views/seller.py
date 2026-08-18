from django.shortcuts import (
    get_object_or_404,
)

from rest_framework import (
    generics,
    permissions,
    status,
)

from rest_framework.parsers import (
    FormParser,
    JSONParser,
    MultiPartParser,
)

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.event_planner.models import (
    EventBrand,
)

from apps.event_services.models import (
    EventService,
)

from apps.event_services.permissions import (
    IsSellerBrandOwnerOrReadOnly,
)

from apps.event_services.serializers.seller import (
    EventServiceSerializer,
)

from apps.event_services.utils import (
    safe_destroy_cloudinary_resource,
)

from apps.event_services.views.mixins import (
    EventServiceBaseQueryMixin,
)


# =========================================================
# Seller create service
# =========================================================


class EventServiceCreateView(
    generics.CreateAPIView
):
    serializer_class = EventServiceSerializer

    permission_classes = [
        permissions.IsAuthenticated,
        IsSellerBrandOwnerOrReadOnly,
    ]

    parser_classes = [
        MultiPartParser,
        FormParser,
        JSONParser,
    ]

    def get_queryset(self):
        return (
            EventService.objects
            .select_related(
                "brand",
                "brand__seller",
            )
            .all()
        )

    # =====================================================
    # Get brand
    # =====================================================

    def get_brand(self):
        return get_object_or_404(
            EventBrand.objects
            .select_related(
                "seller"
            ),
            slug=self.kwargs.get(
                "brand_slug"
            ),
        )

    # =====================================================
    # Create
    # =====================================================

    def create(
        self,
        request,
        *args,
        **kwargs,
    ):
        brand = self.get_brand()

        # -------------------------------------------------
        # Brand ownership
        # -------------------------------------------------

        if brand.seller_id != request.user.id:
            return Response(
                {
                    "detail": (
                        "You can only create services "
                        "for your own brand."
                    )
                },
                status=(
                    status.HTTP_403_FORBIDDEN
                ),
            )

        # -------------------------------------------------
        # Service type
        # -------------------------------------------------

        service_name = request.data.get(
            "service_name"
        )

        if not service_name:
            return Response(
                {
                    "detail": (
                        "Service type is required."
                    ),
                    "service_name": [
                        (
                            "Please select a "
                            "service type."
                        )
                    ],
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        # -------------------------------------------------
        # Duplicate service check
        # -------------------------------------------------

        service_exists = (
            EventService.objects.filter(
                brand=brand,
                service_name=service_name,
            )
            .exists()
        )

        if service_exists:
            return Response(
                {
                    "detail": (
                        "Your brand already has this "
                        "service. Please update the "
                        "existing service instead."
                    ),
                    "service_name": [
                        (
                            "Your brand already has "
                            "this service type."
                        )
                    ],
                    "code": (
                        "service_already_exists"
                    ),
                },
                status=(
                    status.HTTP_409_CONFLICT
                ),
            )

        # -------------------------------------------------
        # Add brand automatically
        # -------------------------------------------------

        data = request.data.copy()

        data["brand_id"] = str(
            brand.id
        )

        # -------------------------------------------------
        # Validate
        # -------------------------------------------------

        serializer = self.get_serializer(
            data=data
        )

        serializer.is_valid(
            raise_exception=True
        )

        self.perform_create(
            serializer
        )

        headers = (
            self.get_success_headers(
                serializer.data
            )
        )

        return Response(
            serializer.data,
            status=(
                status.HTTP_201_CREATED
            ),
            headers=headers,
        )


# =========================================================
# Seller update service
# =========================================================


class EventServiceUpdateView(
    EventServiceBaseQueryMixin,
    generics.UpdateAPIView,
):
    permission_classes = [
        permissions.IsAuthenticated,
        IsSellerBrandOwnerOrReadOnly,
    ]

    parser_classes = [
        MultiPartParser,
        FormParser,
        JSONParser,
    ]


# =========================================================
# Seller delete service
# =========================================================


class EventServiceDeleteView(
    EventServiceBaseQueryMixin,
    generics.DestroyAPIView,
):
    permission_classes = [
        permissions.IsAuthenticated,
        IsSellerBrandOwnerOrReadOnly,
    ]

    def perform_destroy(
        self,
        instance,
    ):
        # -------------------------------------------------
        # Delete cover photo
        # -------------------------------------------------

        if instance.cover_photo:
            safe_destroy_cloudinary_resource(
                instance.cover_photo
            )

        # -------------------------------------------------
        # Delete gallery images
        # -------------------------------------------------

        for image in (
            instance.gallery_images.all()
        ):
            safe_destroy_cloudinary_resource(
                image.image
            )

        # -------------------------------------------------
        # Delete service
        # -------------------------------------------------

        instance.delete()


# =========================================================
# Seller gallery image delete
# =========================================================


class EventServiceGalleryImageDeleteView(
    APIView
):
    permission_classes = [
        permissions.IsAuthenticated,
        IsSellerBrandOwnerOrReadOnly,
    ]

    def delete(
        self,
        request,
        brand_slug,
        service_id,
        service_name,
        image_id,
    ):
        # -------------------------------------------------
        # Get service
        # -------------------------------------------------

        service = get_object_or_404(
            EventService.objects
            .select_related(
                "brand",
                "brand__seller",
            )
            .prefetch_related(
                "gallery_images"
            ),

            brand__slug=brand_slug,

            id=service_id,

            service_name=service_name,
        )

        # -------------------------------------------------
        # Object permission
        # -------------------------------------------------

        self.check_object_permissions(
            request,
            service,
        )

        # -------------------------------------------------
        # Get gallery image
        # -------------------------------------------------

        image = (
            service.gallery_images
            .filter(
                id=image_id
            )
            .first()
        )

        if not image:
            return Response(
                {
                    "detail": (
                        "Gallery image not found."
                    )
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        # -------------------------------------------------
        # Delete Cloudinary image
        # -------------------------------------------------

        safe_destroy_cloudinary_resource(
            image.image
        )

        # -------------------------------------------------
        # Delete DB record
        # -------------------------------------------------

        image.delete()

        return Response(
            status=(
                status.HTTP_204_NO_CONTENT
            )
        )