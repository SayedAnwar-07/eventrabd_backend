from django.urls import path

from apps.event_services.views.admin import (
    AdminServiceDetailView,
    AdminServiceListView,
)
from apps.event_services.views.public import (
    EventServiceDetailView,
    EventServiceListView,
    PublicEventServiceListView,
)
from apps.event_services.views.seller import (
    EventServiceCreateView,
    EventServiceDeleteView,
    EventServiceGalleryImageDeleteView,
    EventServiceUpdateView,
)

from apps.event_services.views.suggestions import (
    SellerSuggestionView,
    BrandSuggestionView,
)

urlpatterns = [
    # Public
    path(
        "services/",
        PublicEventServiceListView.as_view(),
        name="public-services",
    ),
    path(
        "brands/<slug:brand_slug>/services/",
        EventServiceListView.as_view(),
        name="brand-services",
    ),
    path(
        "brands/<slug:brand_slug>/services/<str:service_id>/<str:service_name>/",
        EventServiceDetailView.as_view(),
        name="event-service-detail",
    ),
    
    path(
        "seller-suggestions/",
        SellerSuggestionView.as_view(),
        name="seller-suggestions",
    ),

    path(
        "brand-suggestions/",
        BrandSuggestionView.as_view(),
        name="brand-suggestions",
    ),

    # Seller
    path(
        "brands/<slug:brand_slug>/services/create/",
        EventServiceCreateView.as_view(),
        name="event-service-create",
    ),
    path(
        "brands/<slug:brand_slug>/services/<str:service_id>/<str:service_name>/update/",
        EventServiceUpdateView.as_view(),
        name="event-service-update",
    ),
    path(
        "brands/<slug:brand_slug>/services/<str:service_id>/<str:service_name>/delete/",
        EventServiceDeleteView.as_view(),
        name="event-service-delete",
    ),
    path(
        "brands/<slug:brand_slug>/services/<str:service_id>/<str:service_name>/gallery/<str:image_id>/delete/",
        EventServiceGalleryImageDeleteView.as_view(),
        name="event-service-gallery-image-delete",
    ),

    # Admin
    path(
        "admin/services/",
        AdminServiceListView.as_view(),
        name="admin-service-list",
    ),

    path(
        "admin/services/<str:service_id>/",
        AdminServiceDetailView.as_view(),
        name="admin-service-detail",
    ),
]