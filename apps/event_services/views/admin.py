from rest_framework.generics import (
    ListAPIView,
    RetrieveAPIView,
)

from apps.event_services.models import (
    EventService,
)

from apps.event_services.serializers.admin import (
    AdminServiceSerializer,
)

from apps.reports.permissions import (
    IsAdmin,
)


# =========================================================
# Admin service list
# =========================================================


class AdminServiceListView(
    ListAPIView
):
    serializer_class = (
        AdminServiceSerializer
    )

    permission_classes = [
        IsAdmin,
    ]

    def get_queryset(self):
        return (
            EventService.objects
            .select_related(
                "brand",
                "brand__seller",
            )
            .order_by("-created_at")
        )


# =========================================================
# Admin service detail
# =========================================================


class AdminServiceDetailView(
    RetrieveAPIView
):
    serializer_class = (
        AdminServiceSerializer
    )

    permission_classes = [
        IsAdmin,
    ]

    lookup_field = "id"

    lookup_url_kwarg = (
        "service_id"
    )

    queryset = (
        EventService.objects
        .select_related(
            "brand",
            "brand__seller",
        )
    )