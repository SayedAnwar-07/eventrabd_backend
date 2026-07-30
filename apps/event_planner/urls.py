from django.urls import path
from .views import (
    EventBrandListView,
    EventBrandCreateView,
    EventBrandDetailView,
    EventBrandUpdateView,
    EventBrandDeleteView,
    AllEventBrandView,
)

urlpatterns = [
    path("brands/", EventBrandListView.as_view(), name="brand-list"),
    path("brands/create/", EventBrandCreateView.as_view(), name="brand-create"),

    path("my-brand/", AllEventBrandView.as_view(), name="my-brand"),

    path("brands/<slug:slug>/", EventBrandDetailView.as_view(), name="brand-detail"),
    path("brands/<slug:slug>/update/", EventBrandUpdateView.as_view(), name="brand-update"),
    path("brands/<slug:slug>/delete/", EventBrandDeleteView.as_view(), name="brand-delete"),
]