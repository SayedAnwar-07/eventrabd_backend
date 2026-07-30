from django.http import Http404

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.mixins import (
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from .models import Invoice
from .serializers import (
    InvoiceCreateSerializer,
    InvoiceCustomerDecisionSerializer,
    InvoiceDetailSerializer,
    InvoiceUpdateSerializer,
)


class InvoiceViewSet(
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    GenericViewSet,
):
    """
    Seller:
        - Create an invoice for an accepted hire.
        - List and retrieve their invoices.
        - Update before the due date and before
          customer decision.

    Customer:
        - List and retrieve invoices for their hires.
        - Agree or disagree with their invoice.

    Admin:
        - List and retrieve all invoices.
    """

    permission_classes = [
        IsAuthenticated,
    ]

    lookup_field = "id"

    http_method_names = [
        "get",
        "post",
        "patch",
        "head",
        "options",
    ]

    def get_queryset(self):
        user = self.request.user

        queryset = (
            Invoice.objects
            .select_related(
                "hire",
                "hire__customer",
                "hire__service",
                "hire__service__brand",
                "hire__service__brand__seller",
            )
            .order_by("-created_at")
        )

        if user.is_staff or user.is_superuser:
            return queryset

        if getattr(user, "role", None) == "seller":
            return queryset.filter(
                hire__service__brand__seller=user,
            )

        if getattr(user, "role", None) == "customer":
            return queryset.filter(
                hire__customer=user,
            )

        return queryset.none()

    def get_object(self):
        try:
            return super().get_object()

        except Http404 as error:
            raise NotFound(
                detail=(
                    "Invoice was not found or you do "
                    "not have permission to access it."
                )
            ) from error

    def get_serializer_class(self):
        if self.action == "create":
            return InvoiceCreateSerializer

        if self.action == "customer_decision":
            return (
                InvoiceCustomerDecisionSerializer
            )

        if self.action in {
            "update",
            "partial_update",
        }:
            return InvoiceUpdateSerializer

        return InvoiceDetailSerializer

    @action(
        detail=True,
        methods=["post"],
        url_path="customer-decision",
    )
    def customer_decision(
        self,
        request,
        *args,
        **kwargs,
    ):
        invoice = self.get_object()

        serializer = self.get_serializer(
            invoice,
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )