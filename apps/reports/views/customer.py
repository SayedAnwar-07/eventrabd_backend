from rest_framework.generics import (
    CreateAPIView,
    ListAPIView,
    RetrieveAPIView,
)

from apps.reports.models import ServiceReport
from apps.reports.permissions import IsCustomer
from apps.reports.serializers import (
    ServiceReportCreateSerializer,
    ServiceReportDetailSerializer,
)


class CustomerReportListView(ListAPIView):
    serializer_class = (
        ServiceReportDetailSerializer
    )

    permission_classes = [
        IsCustomer,
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
            .filter(
                reporter=self.request.user
            )
            .order_by("-created_at")
        )


class CustomerReportDetailView(
    RetrieveAPIView
):
    serializer_class = (
        ServiceReportDetailSerializer
    )

    permission_classes = [
        IsCustomer,
    ]

    lookup_field = "id"
    lookup_url_kwarg = "report_id"

    def get_queryset(self):
        return (
            ServiceReport.objects
            .select_related(
                "reporter",
                "hire",
                "service",
                "service__brand",
            )
            .filter(
                reporter=self.request.user
            )
        )


class CustomerReportCreateView(
    CreateAPIView
):
    serializer_class = (
        ServiceReportCreateSerializer
    )

    permission_classes = [
        IsCustomer,
    ]