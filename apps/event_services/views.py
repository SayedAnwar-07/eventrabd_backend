from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control, never_cache

from rest_framework import generics, permissions, status, pagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.event_planner.models import EventBrand
from apps.event_services.models import EventService, ServiceGalleryImage
from apps.event_services.permissions import IsSellerBrandOwnerOrReadOnly
from apps.event_services.serializers import EventServiceSerializer
from apps.event_services.utils import safe_destroy_cloudinary_resource
from rest_framework.generics import RetrieveUpdateAPIView

class EventServicePagination(pagination.PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 50


class EventServiceBaseQueryMixin:
    serializer_class = EventServiceSerializer

    def get_queryset(self):
        return (
            EventService.objects
            .select_related("brand", "brand__seller")
            .prefetch_related(
                Prefetch(
                    "gallery_images",
                    queryset=ServiceGalleryImage.objects.order_by(
                        "sort_order",
                        "-created_at",
                    ),
                )
            )
        )

    def get_object(self):
        brand_slug = self.kwargs.get("brand_slug")
        service_id = self.kwargs.get("service_id")
        service_name = self.kwargs.get("service_name")

        service = get_object_or_404(
            self.get_queryset(),
            brand__slug=brand_slug,
            id=service_id,
            service_name=service_name,
        )

        self.check_object_permissions(self.request, service)

        return service

@method_decorator(never_cache, name="dispatch")
@method_decorator(
    cache_control(private=True, no_cache=True, no_store=True, must_revalidate=True),
    name="dispatch",
)
class EventServiceListView(generics.ListAPIView):
    serializer_class = EventServiceSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = EventServicePagination

    def get_queryset(self):
        brand_slug = self.kwargs.get("brand_slug")

        queryset = (
            EventService.objects
            .select_related("brand", "brand__seller")
            .prefetch_related(
                Prefetch(
                    "gallery_images",
                    queryset=ServiceGalleryImage.objects.order_by(
                        "sort_order", "-created_at"
                    ),
                )
            )
            .filter(brand__slug=brand_slug)
            .order_by("-created_at")
        )

        service_type = self.request.query_params.get("service_type")
        search = self.request.query_params.get("search")

        if service_type:
            queryset = queryset.filter(service_name__iexact=service_type.strip())

        if search:
            search = search.strip()
            queryset = queryset.filter(
                Q(service_name__icontains=search)
                | Q(description__icontains=search)
                | Q(slug__icontains=search)
                | Q(brand__brand_name__icontains=search)
                | Q(brand__service_area__icontains=search)
            )

        return queryset


class EventServiceDetailView(EventServiceBaseQueryMixin, generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]


class EventServiceCreateView(generics.CreateAPIView):
    serializer_class = EventServiceSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerBrandOwnerOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return EventService.objects.select_related("brand", "brand__seller").all()

    def get_brand(self):
        return get_object_or_404(
            EventBrand.objects.select_related("seller"),
            slug=self.kwargs.get("brand_slug"),
        )

    def create(self, request, *args, **kwargs):
        brand = self.get_brand()

        if brand.seller_id != request.user.id:
            return Response(
                {
                    "detail": "You can only create services for your own brand."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        service_name = request.data.get("service_name")

        if not service_name:
            return Response(
                {
                    "detail": "Service type is required.",
                    "service_name": ["Please select a service type."],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        service_exists = EventService.objects.filter(
            brand=brand,
            service_name=service_name,
        ).exists()

        if service_exists:
            return Response(
                {
                    "detail": "our brand already has this service. Please update the existing service instead.",
                    "service_name": [
                        "Your brand already has this service type."
                    ],
                    "code": "service_already_exists",
                },
                status=status.HTTP_409_CONFLICT,
            )

        data = request.data.copy()
        data["brand_id"] = str(brand.id)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class EventServiceUpdateView(EventServiceBaseQueryMixin, generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsSellerBrandOwnerOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]


class EventServiceDeleteView(EventServiceBaseQueryMixin, generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated, IsSellerBrandOwnerOrReadOnly]

    def perform_destroy(self, instance):
        if instance.cover_photo:
            safe_destroy_cloudinary_resource(instance.cover_photo)

        for image in instance.gallery_images.all():
            safe_destroy_cloudinary_resource(image.image)

        instance.delete()

class EventServiceGalleryImageDeleteView(APIView):
    permission_classes = [
        permissions.IsAuthenticated,
        IsSellerBrandOwnerOrReadOnly,
    ]

    def delete(self, request, brand_slug, service_id, service_name, image_id):
        service = get_object_or_404(
            EventService.objects
            .select_related("brand", "brand__seller")
            .prefetch_related("gallery_images"),
            brand__slug=brand_slug,
            id=service_id,
            service_name=service_name,
        )

        self.check_object_permissions(request, service)

        image = service.gallery_images.filter(id=image_id).first()

        if not image:
            return Response(
                {"detail": "Gallery image not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        safe_destroy_cloudinary_resource(image.image)
        image.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)