from django.urls import path

from .views import (
    NotificationCountView,
    NotificationDetailView,
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
)


app_name = "notifications"


urlpatterns = [
    path(
        "",
        NotificationListView.as_view(),
        name="notification-list",
    ),

    path(
        "count/",
        NotificationCountView.as_view(),
        name="notification-count",
    ),

    path(
        "mark-all-read/",
        NotificationMarkAllReadView.as_view(),
        name="notification-mark-all-read",
    ),

    path(
        "<str:id>/",
        NotificationDetailView.as_view(),
        name="notification-detail",
    ),

    path(
        "<str:id>/mark-read/",
        NotificationMarkReadView.as_view(),
        name="notification-mark-read",
    ),
]