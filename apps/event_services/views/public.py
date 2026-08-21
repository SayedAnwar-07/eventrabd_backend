from django.db.models import Prefetch, Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import (
    cache_control,
    never_cache,
)

from rest_framework import (
    generics,
    pagination,
    permissions,
)

from apps.event_planner.constants import DIVISION_VALUES

from apps.event_services.models import (
    EventService,
    ServiceGalleryImage,
)

from apps.event_services.serializers.public import (
    PublicEventServiceCardSerializer,
)

from apps.event_services.serializers.seller import (
    EventServiceSerializer,
)

from apps.event_services.views.mixins import (
    EventServiceBaseQueryMixin,
)


# =========================================================
# Pagination
# =========================================================


class EventServicePagination(
    pagination.PageNumberPagination
):
    page_size = 12

    page_size_query_param = "page_size"

    max_page_size = 50


# =========================================================
# Public all services list
# =========================================================


@method_decorator(
    never_cache,
    name="dispatch",
)
@method_decorator(
    cache_control(
        private=True,
        no_cache=True,
        no_store=True,
        must_revalidate=True,
    ),
    name="dispatch",
)
class PublicEventServiceListView(
    generics.ListAPIView
):
    serializer_class = (
        PublicEventServiceCardSerializer
    )

    permission_classes = [
        permissions.AllowAny,
    ]

    pagination_class = (
        EventServicePagination
    )

    def get_queryset(self):

        queryset = (
            EventService.objects
            .select_related(
                "brand",
                "brand__seller",
            )
            .prefetch_related(
                Prefetch(
                    "gallery_images",
                    queryset=(
                        ServiceGalleryImage.objects
                        .order_by(
                            "sort_order",
                            "-created_at",
                        )
                    ),
                )
            )
            .order_by("-created_at")
        )


        # =================================================
        # Seller filter
        # GET:
        # /services/?seller_id=25
        #
        # Flow:
        # Seller
        #   ↓
        # Brand
        #   ↓
        # Services
        # =================================================

        seller_id = (
            self.request
            .query_params
            .get("seller_id")
        )

        if seller_id:
            queryset = queryset.filter(
                brand__seller_id=seller_id
            )


        # =================================================
        # Brand filter
        # GET:
        # /services/?brand_id=10
        #
        # Flow:
        # Brand
        #   ↓
        # Services
        # =================================================

        brand_id = (
            self.request
            .query_params
            .get("brand_id")
        )

        if brand_id:
            queryset = queryset.filter(
                brand_id=brand_id
            )


        # =================================================
        # Service type filter
        # =================================================

        service_type = (
            self.request
            .query_params
            .get("service_type")
        )

        if service_type:
            service_type = (
                service_type
                .strip()
                .lower()
            )

            queryset = queryset.filter(
                service_name__iexact=service_type
            )


        # =================================================
        # Division filter
        # =================================================

        division = (
            self.request
            .query_params
            .get("division")
        )

        if division:
            division = (
                division
                .strip()
                .lower()
            )

            if division in DIVISION_VALUES:

                if division == "whole_bangladesh":

                    queryset = queryset.filter(
                        brand__division__contains=[
                            "whole_bangladesh"
                        ]
                    )

                else:

                    queryset = queryset.filter(
                        brand__division__contains=[
                            division
                        ]
                    )


        # =================================================
        # General search
        # =================================================

        search = (
            self.request
            .query_params
            .get("search")
        )

        if search:

            search = search.strip()

            search_query = (
                Q(
                    service_name__icontains=search
                )
                |
                Q(
                    description__icontains=search
                )
                |
                Q(
                    brand__brand_name__icontains=search
                )
                |
                Q(
                    brand__display_name__icontains=search
                )
                |
                Q(
                    brand__office_address__icontains=search
                )
                |
                Q(
                    brand__seller__full_name__icontains=search
                )
            )


            normalized_search = (
                search
                .lower()
                .replace(" ", "_")
            )


            if normalized_search in DIVISION_VALUES:

                if normalized_search == "whole_bangladesh":

                    search_query |= Q(
                        brand__division__contains=[
                            "whole_bangladesh"
                        ]
                    )

                else:

                    search_query |= (
                        Q(
                            brand__division__contains=[
                                normalized_search
                            ]
                        )
                        |
                        Q(
                            brand__division__contains=[
                                "whole_bangladesh"
                            ]
                        )
                    )


            queryset = queryset.filter(
                search_query
            )


        return queryset


# =========================================================
# Services for one brand
# =========================================================


@method_decorator(
    never_cache,
    name="dispatch",
)
@method_decorator(
    cache_control(
        private=True,
        no_cache=True,
        no_store=True,
        must_revalidate=True,
    ),
    name="dispatch",
)
class EventServiceListView(
    generics.ListAPIView
):
    serializer_class = EventServiceSerializer

    permission_classes = [
        permissions.AllowAny,
    ]

    pagination_class = (
        EventServicePagination
    )

    def get_queryset(self):
        brand_slug = self.kwargs.get(
            "brand_slug"
        )

        queryset = (
            EventService.objects
            .select_related(
                "brand",
                "brand__seller",
            )
            .prefetch_related(
                Prefetch(
                    "gallery_images",
                    queryset=(
                        ServiceGalleryImage.objects
                        .order_by(
                            "sort_order",
                            "-created_at",
                        )
                    ),
                )
            )
            .filter(
                brand__slug=brand_slug
            )
            .order_by("-created_at")
        )

        service_type = (
            self.request
            .query_params
            .get("service_type")
        )

        search = (
            self.request
            .query_params
            .get("search")
        )

        # -------------------------------------------------
        # Service type filter
        # -------------------------------------------------

        if service_type:
            queryset = queryset.filter(
                service_name__iexact=(
                    service_type
                    .strip()
                    .lower()
                )
            )

        # -------------------------------------------------
        # Search
        # -------------------------------------------------

        if search:
            search = search.strip()

            queryset = queryset.filter(
                Q(
                    service_name__icontains=search
                )
                |
                Q(
                    description__icontains=search
                )
                |
                Q(
                    slug__icontains=search
                )
                |
                Q(
                    brand__brand_name__icontains=search
                )
                |
                Q(
                    brand__display_name__icontains=search
                )
                |
                Q(
                    brand__office_address__icontains=search
                )
            )

        return queryset


# =========================================================
# Public service detail
# =========================================================


class EventServiceDetailView(
    EventServiceBaseQueryMixin,
    generics.RetrieveAPIView,
):
    permission_classes = [
        permissions.AllowAny,
    ]