from django.urls import path

from apps.event_services.views import (
    EventServiceCreateView,
    EventServiceDeleteView,
    EventServiceDetailView,
    EventServiceGalleryImageDeleteView,
    EventServiceListView,
    EventBrandAllServiceListView,
    EventServiceUpdateView,
)

urlpatterns = [
    # Private seller-only (put FIRST)
    path("services/create/", EventServiceCreateView.as_view(), name="event-service-create"),

    # Public
    path("services/", EventServiceListView.as_view(), name="event-service-list"),
    path("brands/<slug:brand_slug>/services/",EventBrandAllServiceListView.as_view(), name="event-brand-all-service-list",),
    path("services/<slug:slug>/", EventServiceDetailView.as_view(), name="event-service-detail"),

    # Others
    path("services/<slug:slug>/update/", EventServiceUpdateView.as_view(), name="event-service-update"),
    path("services/<slug:slug>/delete/", EventServiceDeleteView.as_view(), name="event-service-delete"),
    path("services/<slug:slug>/gallery/<str:image_id>/delete/", EventServiceGalleryImageDeleteView.as_view()),
]