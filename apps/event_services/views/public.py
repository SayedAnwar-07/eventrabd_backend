import logging
from time import perf_counter

from django.db import connection

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

logger = logging.getLogger(__name__)

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
# Shared public gallery prefetch
# =========================================================


def service_gallery_prefetch():
    """
    Load only fields required by
    ServiceGalleryImageSerializer.

    Using to_attr prevents serializer code from having
    to access the related manager for the normal list path.
    """

    return Prefetch(
        "gallery_images",
        queryset=(
            ServiceGalleryImage.objects
            .only(
                "id",
                "service_id",
                "image",
                "sort_order",
                "created_at",
            )
            .order_by(
                "sort_order",
                "-created_at",
            )
        ),
        to_attr="prefetched_gallery_images",
    )


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
    def list(self, request, *args, **kwargs):
        total_start = perf_counter()

        db_query_count = 0
        db_query_time = 0.0

        # -----------------------------------------------------
        # Measure DB connection
        # -----------------------------------------------------

        connection_start = perf_counter()

        connection.ensure_connection()

        connection_time = (
            perf_counter() - connection_start
        )

        # -----------------------------------------------------
        # Measure every SQL query
        # -----------------------------------------------------

        def query_timer(
            execute,
            sql,
            params,
            many,
            context,
        ):
            nonlocal db_query_count
            nonlocal db_query_time

            query_start = perf_counter()

            try:
                return execute(
                    sql,
                    params,
                    many,
                    context,
                )
            finally:
                elapsed = (
                    perf_counter() - query_start
                )

                db_query_count += 1
                db_query_time += elapsed

        with connection.execute_wrapper(
            query_timer
        ):
            # ---------------------------------------------
            # Build queryset
            # ---------------------------------------------

            queryset_start = perf_counter()

            queryset = self.filter_queryset(
                self.get_queryset()
            )

            queryset_build_time = (
                perf_counter()
                - queryset_start
            )

            # ---------------------------------------------
            # Pagination
            #
            # This evaluates pagination COUNT query.
            # ---------------------------------------------

            pagination_start = perf_counter()

            page = self.paginate_queryset(
                queryset
            )

            pagination_time = (
                perf_counter()
                - pagination_start
            )

            # ---------------------------------------------
            # Serialization
            #
            # Queryset + select_related + prefetch_related
            # are evaluated around here.
            # ---------------------------------------------

            serialization_start = (
                perf_counter()
            )

            if page is not None:
                serializer = self.get_serializer(
                    page,
                    many=True,
                )

                data = serializer.data

                serialization_time = (
                    perf_counter()
                    - serialization_start
                )

                response = (
                    self.get_paginated_response(
                        data
                    )
                )

            else:
                serializer = self.get_serializer(
                    queryset,
                    many=True,
                )

                data = serializer.data

                serialization_time = (
                    perf_counter()
                    - serialization_start
                )

                response = Response(data)

        total_time = (
            perf_counter() - total_start
        )

        # -----------------------------------------------------
        # Render logs
        # -----------------------------------------------------

        logger.warning(
            (
                "\n"
                "========== SERVICES PERFORMANCE ==========\n"
                "Path: %s\n"
                "DB connection: %.3f s\n"
                "DB queries: %s\n"
                "DB query time: %.3f s\n"
                "Queryset build: %.3f s\n"
                "Pagination: %.3f s\n"
                "Serialization: %.3f s\n"
                "Total view time: %.3f s\n"
                "=========================================="
            ),
            request.get_full_path(),
            connection_time,
            db_query_count,
            db_query_time,
            queryset_build_time,
            pagination_time,
            serialization_time,
            total_time,
        )

        # -----------------------------------------------------
        # Optional DevTools timing information
        # -----------------------------------------------------

        response["Server-Timing"] = (
            f'dbconnect;dur={connection_time * 1000:.1f}, '
            f'db;dur={db_query_time * 1000:.1f}, '
            f'paginate;dur={pagination_time * 1000:.1f}, '
            f'serialize;dur={serialization_time * 1000:.1f}, '
            f'view;dur={total_time * 1000:.1f}'
        )

        return response
    
    # -----------
    def get_queryset(self):
        queryset = (
            EventService.objects

            # ForeignKey / OneToOne
            .select_related(
                "brand",
                "brand__seller",
            )

            # Reverse ForeignKey
            .prefetch_related(
                service_gallery_prefetch()
            )

            .order_by(
                "-created_at"
            )
        )

        # =================================================
        # Seller filter
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

            # Exact lookup because our choice values
            # and normalized input are already lowercase.
            queryset = queryset.filter(
                service_name=service_type
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
                        Q(
                            brand__division__contains=[
                                division
                            ]
                        )
                        |
                        Q(
                            brand__division__contains=[
                                "whole_bangladesh"
                            ]
                        )
                    )

                    # IMPORTANT:
                    # No .distinct() needed here.
                    #
                    # EventService -> EventBrand is a
                    # single-valued FK relationship.

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

            if (
                normalized_search
                in DIVISION_VALUES
            ):
                if (
                    normalized_search
                    == "whole_bangladesh"
                ):
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
    serializer_class = (
        EventServiceSerializer
    )

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
                service_gallery_prefetch()
            )
            .filter(
                brand__slug=brand_slug
            )
            .order_by(
                "-created_at"
            )
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
        # Service type
        # -------------------------------------------------

        if service_type:
            service_type = (
                service_type
                .strip()
                .lower()
            )

            queryset = queryset.filter(
                service_name=service_type
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