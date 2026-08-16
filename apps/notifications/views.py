from django.db.models import Count, Q

from rest_framework import serializers, status
from rest_framework.generics import (
    ListAPIView,
    RetrieveAPIView,
)
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import (
    BasePermission,
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import (
    NotificationCountSerializer,
    NotificationMarkAllReadSerializer,
    NotificationSerializer,
)


# =========================================================
# Permission
# =========================================================


class IsNotificationUser(BasePermission):
    """
    Notification access is available to:
        - customer
        - seller
    """

    message = (
        "Only customers and sellers can access notifications."
    )

    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and getattr(user, "role", None)
            in {
                "customer",
                "seller",
            }
        )


# =========================================================
# Pagination
# =========================================================


class NotificationCursorPagination(
    CursorPagination
):
    page_size = 20
    ordering = "-created_at"
    cursor_query_param = "cursor"


# =========================================================
# Base mixin
# =========================================================


class NotificationQueryMixin:
    """
    Shared recipient filtering.

    Every endpoint only works with notifications
    belonging to the authenticated user.
    """

    def get_base_queryset(self):
        return Notification.objects.for_recipient(
            self.request.user
        )


# =========================================================
# List notifications
# =========================================================


class NotificationListView(
    NotificationQueryMixin,
    ListAPIView,
):
    """
    GET /notifications/

    Optional:

        ?is_read=true
        ?is_read=false
    """

    serializer_class = NotificationSerializer

    permission_classes = [
        IsAuthenticated,
        IsNotificationUser,
    ]

    pagination_class = (
        NotificationCursorPagination
    )

    def get_queryset(self):
        queryset = self.get_base_queryset()

        is_read = (
            self.request
            .query_params
            .get("is_read")
        )

        if is_read is not None:
            normalized_value = (
                is_read
                .strip()
                .lower()
            )

            if normalized_value == "true":
                queryset = queryset.filter(
                    is_read=True,
                )

            elif normalized_value == "false":
                queryset = queryset.filter(
                    is_read=False,
                )

            else:
                raise serializers.ValidationError({
                    "is_read": (
                        "is_read must be either "
                        "'true' or 'false'."
                    )
                })

        return (
            NotificationSerializer
            .setup_eager_loading(
                queryset
            )
        )


# =========================================================
# Retrieve notification
# =========================================================


class NotificationDetailView(
    NotificationQueryMixin,
    RetrieveAPIView,
):
    """
    GET /notifications/<id>/
    """

    serializer_class = NotificationSerializer

    permission_classes = [
        IsAuthenticated,
        IsNotificationUser,
    ]

    lookup_field = "id"

    def get_queryset(self):
        queryset = self.get_base_queryset()

        return (
            NotificationSerializer
            .setup_eager_loading(
                queryset
            )
        )


# =========================================================
# Count notifications
# =========================================================


class NotificationCountView(
    NotificationQueryMixin,
    APIView,
):
    """
    GET /notifications/count/

    Uses one aggregate query.
    """

    permission_classes = [
        IsAuthenticated,
        IsNotificationUser,
    ]

    def get(self, request):
        queryset = (
            self.get_base_queryset()
            .order_by()
        )

        data = queryset.aggregate(
            total_count=Count(
                "id",
            ),
            unread_count=Count(
                "id",
                filter=Q(
                    is_read=False,
                ),
            ),
        )

        serializer = (
            NotificationCountSerializer(
                data
            )
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


# =========================================================
# Mark one notification read
# =========================================================


class NotificationMarkReadView(
    NotificationQueryMixin,
    APIView,
):
    """
    POST /notifications/<id>/mark-read/
    """

    permission_classes = [
        IsAuthenticated,
        IsNotificationUser,
    ]

    def post(
        self,
        request,
        id,
    ):
        notification = (
            self.get_base_queryset()
            .filter(
                id=id,
            )
            .first()
        )

        if notification is None:
            return Response(
                {
                    "detail": (
                        "Notification not found."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        notification.mark_as_read()

        queryset = (
            Notification.objects
            .filter(
                pk=notification.pk
            )
        )

        notification = (
            NotificationSerializer
            .setup_eager_loading(
                queryset
            )
            .first()
        )

        serializer = (
            NotificationSerializer(
                notification,
                context={
                    "request": request,
                },
            )
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


# =========================================================
# Mark all notifications read
# =========================================================


class NotificationMarkAllReadView(
    NotificationQueryMixin,
    APIView,
):
    """
    POST /notifications/mark-all-read/

    Performs one UPDATE query.
    """

    permission_classes = [
        IsAuthenticated,
        IsNotificationUser,
    ]

    def post(self, request):
        queryset = (
            self.get_base_queryset()
            .order_by()
        )

        updated_count = (
            queryset
            .unread()
            .mark_all_read()
        )

        data = {
            "updated_count": (
                updated_count
            ),
            "unread_count": 0,
        }

        serializer = (
            NotificationMarkAllReadSerializer(
                data
            )
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )