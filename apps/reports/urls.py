from django.urls import path

from apps.reports.views import (
    AdminReportDeleteView,
    AdminReportDetailView,
    AdminReportListView,
    AdminReportStatusUpdateView,
    CustomerReportCreateView,
    CustomerReportDetailView,
    CustomerReportListView,
)


urlpatterns = [
    # =====================================================
    # Admin
    # Keep admin routes before dynamic customer detail route
    # =====================================================

    path(
        "admin/",
        AdminReportListView.as_view(),
        name="admin-report-list",
    ),

    path(
        "admin/<str:report_id>/",
        AdminReportDetailView.as_view(),
        name="admin-report-detail",
    ),

    path(
        "admin/<str:report_id>/status/",
        AdminReportStatusUpdateView.as_view(),
        name="admin-report-status-update",
    ),

    path(
        "admin/<str:report_id>/delete/",
        AdminReportDeleteView.as_view(),
        name="admin-report-delete",
    ),

    # =====================================================
    # Customer
    # =====================================================

    path(
        "",
        CustomerReportListView.as_view(),
        name="customer-report-list",
    ),

    path(
        "create/",
        CustomerReportCreateView.as_view(),
        name="customer-report-create",
    ),

    path(
        "<str:report_id>/",
        CustomerReportDetailView.as_view(),
        name="customer-report-detail",
    ),
]