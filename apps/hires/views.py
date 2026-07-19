from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.hires.models import Hire
from apps.hires.serializers import (
    HireCreateSerializer,
    HireDetailSerializer,
    HireSellerDecisionSerializer,
)


class HireViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Available actions:

    Customer:
    - Create a hire request
    - View own hire requests
    - View own hire details

    Seller:
    - View hire requests received for their services
    - View hire details
    - Accept or reject a pending hire request

    Admin:
    - View all hire requests
    """

    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    # Do not expose PUT, PATCH or DELETE.
    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    def get_queryset(self):
        user = self.request.user

        queryset = (
            Hire.objects
            .select_related(
                "customer",
                "service",
                "service__brand",
                "service__brand__seller",
                "cancelled_by",
            )
            .prefetch_related("booking_slots")
            .order_by("-created_at")
        )

        # Admin can see everything.
        if user.is_staff or user.role == "admin":
            return queryset

        # Customer can only see their own hire requests.
        if user.role == "customer":
            return queryset.filter(customer=user)

        # Seller can only see requests for their own services.
        if user.role == "seller":
            return queryset.filter(
                service__brand__seller=user
            )

        return queryset.none()

    def get_serializer_class(self):
        if self.action == "create":
            return HireCreateSerializer

        if self.action == "decision":
            return HireSellerDecisionSerializer

        return HireDetailSerializer

    @action(
        detail=True,
        methods=["post"],
        url_path="decision",
    )
    def decision(self, request, id=None):
        """
        Seller accepts or rejects a pending hire request.

        POST:
        /api/hires/{id}/decision/
        """

        hire = self.get_object()

        serializer = self.get_serializer(
            instance=hire,
            data=request.data,
        )

        serializer.is_valid(raise_exception=True)
        updated_hire = serializer.save()

        response_serializer = HireDetailSerializer(
            updated_hire,
            context=self.get_serializer_context(),
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK,
        )