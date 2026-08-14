from django.urls import path

from apps.packages.views import (
    ServicePackageListCreateView,
    ServicePackageDetailView,
)


urlpatterns = [
    path(
        "services/<str:service_id>/packages/",
        ServicePackageListCreateView.as_view(),
        name="service-package-list-create",
    ),

    path(
        "services/<str:service_id>/packages/<str:package_id>/",
        ServicePackageDetailView.as_view(),
        name="service-package-detail",
    ),
]