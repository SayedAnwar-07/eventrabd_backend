from django.db.models import Count, Q
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import (
    ListModelMixin,
    RetrieveModelMixin,
)
from rest_framework.permissions import (
    BasePermission,
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from .models import Notification
from .serializers import (
    NotificationCountSerializer,
    NotificationMarkAllReadSerializer,
    NotificationSerializer,
)


class IsCustomer(BasePermission):
    """
    Allow notification API access only to customer users.
    """

    message = "Only customers can access notifications."

    def has_permission(self, request, view):
        user = request.user

        return bool(
            user
            and user.is_authenticated
            and getattr(user, "role", None) == "customer"
        )


class NotificationViewSet(
    ListModelMixin,
    RetrieveModelMixin,
    GenericViewSet,
):
    """
    Customer notification API.

    Customers can:
        - List their notifications.
        - Retrieve one of their notifications.
        - See total and unread counts.
        - Mark one notification as read.
        - Mark all notifications as read.

    Customers cannot:
        - Create notifications.
        - Edit notification content.
        - Delete notifications.
        - Access another customer's notifications.
    """

    serializer_class = NotificationSerializer

    permission_classes = [
        IsAuthenticated,
        IsCustomer,
    ]

    lookup_field = "id"

    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    def get_base_queryset(self):
        """
        Return only notifications belonging to
        the authenticated customer.
        """

        return (
            Notification.objects.select_related(
                "invoice",
            )
            .filter(
                recipient=self.request.user,
            )
            .order_by("-created_at")
        )

    def get_queryset(self):
        queryset = self.get_base_queryset()

        is_read = self.request.query_params.get(
            "is_read"
        )

        if is_read is not None:
            normalized_value = is_read.strip().lower()

            if normalized_value == "true":
                queryset = queryset.filter(
                    is_read=True,
                )

            elif normalized_value == "false":
                queryset = queryset.filter(
                    is_read=False,
                )

        return queryset

    @action(
        detail=False,
        methods=["get"],
        url_path="count",
    )
    def count(self, request):
        """
        Return total and unread notification counts.

        Response:
        {
            "total_count": 10,
            "unread_count": 4
        }
        """

        queryset = self.get_base_queryset()

        count_data = queryset.aggregate(
            total_count=Count("id"),
            unread_count=Count(
                "id",
                filter=Q(is_read=False),
            ),
        )

        serializer = NotificationCountSerializer(
            count_data
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="mark-read",
    )
    def mark_read(self, request, id=None):
        """
        Mark one customer notification as read.
        """

        notification = self.get_object()

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()

            notification.save(
                update_fields=[
                    "is_read",
                    "read_at",
                    "updated_at",
                ]
            )

        serializer = self.get_serializer(
            notification
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="mark-all-read",
    )
    def mark_all_read(self, request):
        """
        Mark all unread notifications belonging to
        the authenticated customer as read.
        """

        now = timezone.now()

        updated_count = (
            self.get_base_queryset()
            .filter(
                is_read=False,
            )
            .update(
                is_read=True,
                read_at=now,
                updated_at=now,
            )
        )

        response_data = {
            "updated_count": updated_count,
            "unread_count": 0,
        }

        serializer = (
            NotificationMarkAllReadSerializer(
                response_data
            )
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )