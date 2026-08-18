from .customer import (
    CustomerReportCreateView,
    CustomerReportDetailView,
    CustomerReportListView,
)

from .admin import (
    AdminReportDeleteView,
    AdminReportDetailView,
    AdminReportListView,
    AdminReportStatusUpdateView,
)


__all__ = [
    "CustomerReportCreateView",
    "CustomerReportDetailView",
    "CustomerReportListView",

    "AdminReportDeleteView",
    "AdminReportDetailView",
    "AdminReportListView",
    "AdminReportStatusUpdateView",
]