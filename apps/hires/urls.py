from django.urls import path

from apps.hires.views import (
    HireAcceptAPIView,
    HireCreateAPIView,
    HireDeleteAPIView,
    HireDetailAPIView,
    HireListAPIView,
    HireRejectAPIView,
)


app_name = "hires"


urlpatterns = [
    path(
        "requests/",
        HireListAPIView.as_view(),
        name="hire-list",
    ),
    path(
        "requests/create/",
        HireCreateAPIView.as_view(),
        name="hire-create",
    ),
    path(
        "requests/<str:id>/accept/",
        HireAcceptAPIView.as_view(),
        name="hire-accept",
    ),
    path(
        "requests/<str:id>/reject/",
        HireRejectAPIView.as_view(),
        name="hire-reject",
    ),
    path(
        "requests/<str:id>/delete/",
        HireDeleteAPIView.as_view(),
        name="hire-delete",
    ),

    # Dynamic details endpoint must remain last.
    path(
        "requests/<str:id>/",
        HireDetailAPIView.as_view(),
        name="hire-detail",
    ),
]