from django.urls import path

from apps.event_services.views import (
    EventServiceCreateView,
    EventServiceDeleteView,
    EventServiceDetailView,
    EventServiceGalleryImageDeleteView,
    EventServiceListView,
    EventServiceUpdateView,
)

urlpatterns = [
    # List all services of one brand
    path(
        "brands/<slug:brand_slug>/services/",
        EventServiceListView.as_view(),
        name="brand-services",
    ),

    # Create service for this brand
    path(
        "brands/<slug:brand_slug>/services/create/",
        EventServiceCreateView.as_view(),
        name="event-service-create",
    ),

    # Get one service
    path(
        "brands/<slug:brand_slug>/services/<str:service_id>/<str:service_name>/",
        EventServiceDetailView.as_view(),
        name="event-service-detail",
    ),

    # Update one service
    path(
        "brands/<slug:brand_slug>/services/<str:service_id>/<str:service_name>/update/",
        EventServiceUpdateView.as_view(),
        name="event-service-update",
    ),

    # Delete one service
    path(
        "brands/<slug:brand_slug>/services/<str:service_id>/<str:service_name>/delete/",
        EventServiceDeleteView.as_view(),
        name="event-service-delete",
    ),
    # Delete gallery image
    path(
        "brands/<slug:brand_slug>/services/<str:service_id>/<str:service_name>/gallery/<str:image_id>/delete/",
        EventServiceGalleryImageDeleteView.as_view(),
        name="event-service-gallery-image-delete",
    ),
]