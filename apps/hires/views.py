from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.hires.models import Hire, HireStatus
from apps.hires.serializers import (
    HireCreateSerializer,
    HireDetailSerializer,
    HireSellerDecisionSerializer,
)


def get_accessible_hires(user):
    """
    Return only hire requests the authenticated user may access.
    """

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

    if user.is_staff or user.role == "admin":
        return queryset

    if user.role == "customer":
        return queryset.filter(customer=user)

    if user.role == "seller":
        return queryset.filter(
            service__brand__seller=user,
        )

    return queryset.none()


class HireQuerysetMixin:
    lookup_field = "id"
    lookup_url_kwarg = "id"

    def get_queryset(self):
        return get_accessible_hires(self.request.user)


class HireListAPIView(
    HireQuerysetMixin,
    generics.ListAPIView,
):
    """
    GET /hire/requests/

    Customer:
    - Returns their own hire requests.

    Seller:
    - Returns requests received for their services.

    Admin:
    - Returns every hire request.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = HireDetailSerializer


class HireCreateAPIView(generics.CreateAPIView):
    """
    POST /hire/requests/create/

    Customer creates a new hire request.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = HireCreateSerializer


class HireDetailAPIView(
    HireQuerysetMixin,
    generics.RetrieveAPIView,
):
    """
    GET /hire/requests/{id}/
    """

    permission_classes = [IsAuthenticated]
    serializer_class = HireDetailSerializer


class BaseHireDecisionAPIView(
    HireQuerysetMixin,
    generics.GenericAPIView,
):
    """
    Shared seller accept/reject functionality.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = HireSellerDecisionSerializer
    decision_value = None

    def post(self, request, *args, **kwargs):
        hire = self.get_object()

        payload = {
            "decision": self.decision_value,
            "seller_note": request.data.get("seller_note", ""),
        }

        serializer = self.get_serializer(
            instance=hire,
            data=payload,
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


class HireAcceptAPIView(BaseHireDecisionAPIView):
    """
    POST /hire/requests/{id}/accept/
    """

    decision_value = "accept"


class HireRejectAPIView(BaseHireDecisionAPIView):
    """
    POST /hire/requests/{id}/reject/
    """

    decision_value = "reject"


class HireDeleteAPIView(
    HireQuerysetMixin,
    generics.DestroyAPIView,
):
    """
    DELETE /hire/requests/{id}/delete/

    Only the customer who created the request may delete it,
    and only after seller rejection.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = HireDetailSerializer

    def destroy(self, request, *args, **kwargs):
        user = request.user

        if user.role != "customer":
            raise PermissionDenied(
                "Only customers can delete hire requests."
            )

        hire = self.get_object()

        if hire.customer_id != user.id:
            raise PermissionDenied(
                "You cannot delete another customer's hire request."
            )

        if hire.status != HireStatus.REJECTED:
            raise ValidationError({
                "status": (
                    "Only hire requests rejected by the seller "
                    "can be deleted."
                )
            })

        self.perform_destroy(hire)

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )