from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import ScopedRateThrottle

from .models import EventBrand, EventBrandSlugHistory
from .serializers import EventBrandSerializer, EventBrandListSerializer


def _get_brand_by_slug(slug):
    """
    Returns (brand, redirected_slug | None)

    - If slug matches current brand slug:
        returns (brand, None)
    - If slug matches old slug history:
        returns (brand, current_slug)
    - If nothing matches:
        raises NotFound
    """
    try:
        brand = EventBrand.objects.select_related("seller").prefetch_related("services").get(slug=slug)
        return brand, None
    except EventBrand.DoesNotExist:
        history = (
            EventBrandSlugHistory.objects
            .select_related("brand__seller")
            .prefetch_related("brand__services")
            .filter(old_slug=slug)
            .first()
        )
        if history:
            return history.brand, history.brand.slug

        raise NotFound("Brand not found.")


class EventBrandListView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_brand"

    def get(self, request):
        brands = (
            EventBrand.objects
            .select_related("seller")
            .prefetch_related("services")
            .all()
        )
        serializer = EventBrandListSerializer(
            brands,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class EventBrandCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != "seller":
            raise PermissionDenied("Only sellers can create a brand.")

        serializer = EventBrandSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        brand = serializer.save()

        return Response(
            EventBrandSerializer(brand, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class EventBrandDetailView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_brand"

    def get(self, request, slug):
        brand, new_slug = _get_brand_by_slug(slug)

        if new_slug:
            return Response(
                {
                    "detail": "Brand slug has changed.",
                    "old_slug": slug,
                    "new_slug": new_slug,
                    "redirect_url": request.build_absolute_uri(
                        f"/event-planner/brands/{new_slug}/"
                    ),
                },
                status=status.HTTP_308_PERMANENT_REDIRECT,
                headers={
                    "Location": request.build_absolute_uri(
                        f"/event-planner/brands/{new_slug}/"
                    )
                },
            )

        serializer = EventBrandSerializer(brand, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    
class EventBrandPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 50


class AllEventBrandView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        brands = (
            EventBrand.objects
            .select_related("seller")
            .prefetch_related("services")
            .all()
        )

        paginator = EventBrandPagination()
        page = paginator.paginate_queryset(brands, request)

        serializer = EventBrandListSerializer(
            page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data)


class EventBrandUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, slug):
        brand, new_slug = _get_brand_by_slug(slug)

        # old slug used -> do not update, ask client to use current slug
        if new_slug:
            return Response(
                {
                    "detail": "Brand slug has changed. Please use the current slug.",
                    "old_slug": slug,
                    "new_slug": new_slug,
                    "redirect_url": request.build_absolute_uri(
                        f"/event-planner/brands/{new_slug}/update/"
                    ),
                },
                status=status.HTTP_308_PERMANENT_REDIRECT,
                headers={
                    "Location": request.build_absolute_uri(
                        f"/event-planner/brands/{new_slug}/update/"
                    )
                },
            )

        if brand.seller != request.user:
            raise PermissionDenied("You cannot edit this brand.")

        serializer = EventBrandSerializer(
            brand,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        brand = serializer.save()

        return Response(
            EventBrandSerializer(brand, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class EventBrandDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, slug):
        brand, new_slug = _get_brand_by_slug(slug)

        if new_slug:
            return Response(
                {
                    "success": False,
                    "message": "Brand slug has changed. Please use the current slug.",
                    "old_slug": slug,
                    "new_slug": new_slug,
                    "redirect_url": request.build_absolute_uri(
                        f"/event-planner/brands/{new_slug}/delete/"
                    ),
                },
                status=status.HTTP_308_PERMANENT_REDIRECT,
                headers={
                    "Location": request.build_absolute_uri(
                        f"/event-planner/brands/{new_slug}/delete/"
                    )
                },
            )

        if brand.seller_id != request.user.id:
            return Response(
                {
                    "success": False,
                    "message": "You cannot delete this brand.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        brand_name = brand.brand_name
        brand_slug = brand.slug
        brand.delete()

        return Response(
            {
                "success": True,
                "message": f"{brand_name} deleted successfully.",
                "deleted_slug": brand_slug,
            },
            status=status.HTTP_200_OK,
        )