from django.db import transaction
from django.db.models import F

from rest_framework.generics import (
    DestroyAPIView,
    ListAPIView,
    RetrieveAPIView,
    UpdateAPIView,
)

from apps.event_services.models import EventService
from apps.event_services.utils import (
    safe_destroy_cloudinary_resource,
)

from apps.reports.models import ServiceReport
from apps.reports.permissions import IsAdmin
from apps.reports.serializers import (
    AdminReportStatusUpdateSerializer,
    ServiceReportDetailSerializer,
)


# =========================================================
# Admin report list
# =========================================================


class AdminReportListView(
    ListAPIView
):
    serializer_class = (
        ServiceReportDetailSerializer
    )

    permission_classes = [
        IsAdmin,
    ]

    def get_queryset(self):
        return (
            ServiceReport.objects
            .select_related(
                "reporter",
                "hire",
                "service",
                "service__brand",
            )
            .all()
            .order_by("-created_at")
        )


# =========================================================
# Admin report detail
# =========================================================


class AdminReportDetailView(
    RetrieveAPIView
):
    serializer_class = (
        ServiceReportDetailSerializer
    )

    permission_classes = [
        IsAdmin,
    ]

    lookup_field = "id"
    lookup_url_kwarg = "report_id"

    queryset = (
        ServiceReport.objects
        .select_related(
            "reporter",
            "hire",
            "service",
            "service__brand",
        )
    )


# =========================================================
# Admin report status update
# =========================================================


class AdminReportStatusUpdateView(
    UpdateAPIView
):
    serializer_class = (
        AdminReportStatusUpdateSerializer
    )

    permission_classes = [
        IsAdmin,
    ]

    lookup_field = "id"
    lookup_url_kwarg = "report_id"

    http_method_names = [
        "patch",
    ]

    queryset = (
        ServiceReport.objects.all()
    )


# =========================================================
# Admin report delete
# =========================================================


class AdminReportDeleteView(
    DestroyAPIView
):
    permission_classes = [
        IsAdmin,
    ]

    lookup_field = "id"
    lookup_url_kwarg = "report_id"

    queryset = (
        ServiceReport.objects
        .select_related(
            "service",
        )
    )

    @transaction.atomic
    def perform_destroy(self, instance):
        service_id = instance.service_id

        image_resource = (
            instance.image
            if instance.image
            else None
        )

        # Delete report
        instance.delete()

        # Decrease report count
        EventService.objects.filter(
            pk=service_id,
            report_count__gt=0,
        ).update(
            report_count=(
                F("report_count") - 1
            )
        )

        # Delete Cloudinary image only after
        # successful DB transaction
        if image_resource:
            transaction.on_commit(
                lambda image=image_resource: (
                    safe_destroy_cloudinary_resource(
                        image
                    )
                )
            )