from django.db.models import Prefetch
from rest_framework import generics, permissions, status, pagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.event_services.models import EventService, ServiceGalleryImage
from apps.event_services.permissions import IsSellerBrandOwnerOrReadOnly
from apps.event_services.serializers import EventServiceSerializer
from apps.event_services.utils import safe_destroy_cloudinary_resource

from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control, never_cache


class EventServiceBaseQueryMixin:
    def get_queryset(self):
        queryset = (
            EventService.objects.select_related("brand", "brand__seller")
            .prefetch_related(
                Prefetch(
                    "gallery_images",
                    queryset=ServiceGalleryImage.objects.order_by("sort_order", "-created_at"),
                )
            )
            .all()
        )

        request = self.request
        brand_slug = request.query_params.get("brand_slug")
        service_name = request.query_params.get("service_name")

        if brand_slug:
            queryset = queryset.filter(brand__slug=brand_slug)

        if service_name:
            queryset = queryset.filter(service_name=service_name)

        return queryset


class EventServicePagination(pagination.PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 50


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
        queryset = (
            EventService.objects
            .select_related("brand")
            .prefetch_related("gallery_images")
            .order_by("-created_at")
        )

        service_type = self.request.query_params.get("service_type")
        search = self.request.query_params.get("search")
        brand_slug = self.request.query_params.get("brand_slug")

        if brand_slug:
            queryset = queryset.filter(brand__slug=brand_slug)

        if service_type:
            queryset = queryset.filter(service_name__iexact=service_type.strip())

        if search:
            search = search.strip()
            queryset = queryset.filter(
                Q(service_name__icontains=search) |
                Q(description__icontains=search) |
                Q(slug__icontains=search) |
                Q(brand__brand_name__icontains=search) |
                Q(brand__service_area__icontains=search)
            )

        return queryset


@method_decorator(never_cache, name="dispatch")
@method_decorator(
    cache_control(private=True, no_cache=True, no_store=True, must_revalidate=True),
    name="dispatch",
)
class EventBrandAllServiceListView(generics.ListAPIView):
    serializer_class = EventServiceSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = EventServicePagination

    def get_queryset(self):
        brand_slug = self.kwargs.get("brand_slug")

        queryset = (
            EventService.objects
            .select_related("brand")
            .prefetch_related("gallery_images")
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
                Q(service_name__icontains=search) |
                Q(description__icontains=search) |
                Q(slug__icontains=search) |
                Q(brand__brand_name__icontains=search) |
                Q(brand__service_area__icontains=search)
            )

        return queryset


# PUBLIC: GET single service
class EventServiceDetailView(EventServiceBaseQueryMixin, generics.RetrieveAPIView):
    serializer_class = EventServiceSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"


# PRIVATE: POST create service
class EventServiceCreateView(generics.CreateAPIView):
    queryset = EventService.objects.select_related("brand", "brand__seller").all()
    serializer_class = EventServiceSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerBrandOwnerOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]


# PRIVATE: PATCH/PUT update service
class EventServiceUpdateView(EventServiceBaseQueryMixin, generics.UpdateAPIView):
    serializer_class = EventServiceSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerBrandOwnerOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    lookup_field = "slug"


# PRIVATE: DELETE service
class EventServiceDeleteView(EventServiceBaseQueryMixin, generics.DestroyAPIView):
    serializer_class = EventServiceSerializer
    permission_classes = [permissions.IsAuthenticated, IsSellerBrandOwnerOrReadOnly]
    lookup_field = "slug"

    def perform_destroy(self, instance):
        if instance.cover_photo:
            safe_destroy_cloudinary_resource(instance.cover_photo)

        for image in instance.gallery_images.all():
            safe_destroy_cloudinary_resource(image.image)

        instance.delete()


# PRIVATE: DELETE one gallery image
class EventServiceGalleryImageDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSellerBrandOwnerOrReadOnly]

    def delete(self, request, slug, image_id):
        try:
            service = EventService.objects.select_related("brand", "brand__seller").get(slug=slug)
        except EventService.DoesNotExist:
            return Response(
                {"detail": "Service not found."},
                status=status.HTTP_404_NOT_FOUND,
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

        return Response(
            {"detail": "Gallery image deleted successfully."},
            status=status.HTTP_204_NO_CONTENT,
        )