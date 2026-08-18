from django.db.models import Prefetch
from django.shortcuts import get_object_or_404

from apps.event_services.models import (
    EventService,
    ServiceGalleryImage,
)

from apps.event_services.serializers.seller import (
    EventServiceSerializer,
)


# =========================================================
# Shared Event Service Query Mixin
# =========================================================


class EventServiceBaseQueryMixin:
    serializer_class = EventServiceSerializer

    def get_queryset(self):
        return (
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
        )

    def get_object(self):
        brand_slug = self.kwargs.get(
            "brand_slug"
        )

        service_id = self.kwargs.get(
            "service_id"
        )

        service_name = self.kwargs.get(
            "service_name"
        )

        service = get_object_or_404(
            self.get_queryset(),

            brand__slug=brand_slug,

            id=service_id,

            service_name=service_name,
        )

        self.check_object_permissions(
            self.request,
            service,
        )

        return service