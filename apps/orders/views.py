from rest_framework import generics, permissions
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import ServiceOrder
from .serializers import (
    ServiceOrderSerializer,
    CreateServiceOrderSerializer,
    BuyerUpdateOrderSerializer,
    UpdateServiceSellerOrderSerializer,
)
from apps.events.models import Event, EventServiceDetail
from .utils import get_user_by_slug_or_404
from decimal import Decimal 
from django.utils import timezone  



# Create Order
class CreateServiceOrderView(generics.CreateAPIView):
    queryset = ServiceOrder.objects.all()
    serializer_class = CreateServiceOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        buyer_slug = kwargs.get("buyer_slug")
        buyer = get_user_by_slug_or_404(buyer_slug, role="customer")

        if request.user != buyer:
            return Response({"error": "Only customer can create and order forms."}, status=403)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get event object
        event_id = request.data.get("event_id")
        event = get_object_or_404(Event, id=event_id)

        # Process selected services
        selected_services = serializer.validated_data.get("selected_services", [])
        total_amount = 0
        service_details = []

        for service_type in selected_services:  
            try:
                service_detail = EventServiceDetail.objects.get(
                    event=event,
                    service__service_type=service_type, 
                    is_available=True
                )
                total_amount += service_detail.price
                service_details.append({
                    "id": service_detail.service.id,
                    "name": service_detail.service.get_service_type_display(),
                    "price": float(service_detail.price),
                })
            except EventServiceDetail.DoesNotExist:
                continue


        order = ServiceOrder.objects.create(
            seller=event.seller,
            buyer=buyer,
            event=event,
            buyer_name=buyer.full_name,
            event_date=serializer.validated_data["event_date"],
            event_time=serializer.validated_data["event_time"],
            location=serializer.validated_data["location"],
            selected_services=service_details,
            total_amount=total_amount,
        )

        return Response(ServiceOrderSerializer(order).data, status=201)


# Update Order
class UpdateServiceOrderView(generics.UpdateAPIView):
    queryset = ServiceOrder.objects.all()
    serializer_class = BuyerUpdateOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"

    def get_object(self):
        buyer_slug = self.kwargs["buyer_slug"]
        order_id = self.kwargs["id"]
        buyer = get_user_by_slug_or_404(buyer_slug, role="customer")
        order = get_object_or_404(ServiceOrder, id=order_id, buyer=buyer)

        if order.buyer != self.request.user:
            self.permission_denied(self.request, message="Only buyer can update this order.")

        if order.status not in ["pending", "accepted"]:
            self.permission_denied(self.request, message="Order cannot be updated after completion or cancellation.")
        return order

    def update(self, request, *args, **kwargs):
        order = self.get_object()
        serializer = self.get_serializer(order, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data.get("status")

        if new_status == "cancelled":
            order.status = "cancelled"
            order.save()
            return Response(ServiceOrderSerializer(order).data, status=200)

        if new_status == "completed":
            order.status = "completed"
            net_total = (order.total_amount - (order.discount_price or Decimal("0.00")))
            if net_total <= Decimal("0.00") or (order.advance_paid >= net_total):
                order.is_fully_paid = True
                if not order.full_payment_date:
                    order.full_payment_date = timezone.now().date()
            order.save()
            return Response(ServiceOrderSerializer(order).data, status=200)

        return Response({"error": "Invalid status update."}, status=400)

# Delete / Cancel Order
class DeleteServiceOrderView(generics.DestroyAPIView):
    queryset = ServiceOrder.objects.all()
    serializer_class = ServiceOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"

    def get_object(self):
        buyer_slug = self.kwargs["buyer_slug"]
        order_id = self.kwargs["id"]
        buyer = get_user_by_slug_or_404(buyer_slug, role="customer")
        order = get_object_or_404(ServiceOrder, id=order_id, buyer=buyer)

        if order.buyer != self.request.user and order.seller != self.request.user:
            self.permission_denied(self.request, message="Not allowed to access this order.")
        return order

    def destroy(self, request, *args, **kwargs):
        order = self.get_object()
        if order.buyer == request.user and order.status == "pending":
            order.status = "cancelled"
            order.save()
            return Response({"success": "Order cancelled"}, status=200)

        if order.seller == request.user:
            return super().destroy(request, *args, **kwargs)

        return Response({"error": "You cannot delete this order."}, status=403)


# Buyer Orders List
class OrdersListView(generics.ListAPIView):
    serializer_class = ServiceOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        buyer_slug = self.kwargs.get("buyer_slug")
        buyer = get_user_by_slug_or_404(buyer_slug, role="customer")
        return ServiceOrder.objects.filter(buyer=buyer).order_by("-created_at")


# Seller Orders List
class SellerOrderListView(generics.ListAPIView):
    serializer_class = ServiceOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        seller_slug = self.kwargs.get("seller_slug")
        seller = get_user_by_slug_or_404(seller_slug, role="seller")
        return ServiceOrder.objects.filter(seller=seller).order_by("-created_at")


# Accept Order (Seller)
class AcceptOrderView(generics.UpdateAPIView):
    queryset = ServiceOrder.objects.all()
    serializer_class = ServiceOrderSerializer 
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"

    def update(self, request, *args, **kwargs):
        seller_slug = self.kwargs.get("seller_slug")
        order_id = self.kwargs["id"]
        seller = get_user_by_slug_or_404(seller_slug, role="seller")
        order = get_object_or_404(ServiceOrder, id=order_id, seller=seller)

        if order.seller != request.user:
            return Response({"error": "Only the seller can accept this order"}, status=403)

        order.seller_agreed = True
        order.status = 'accepted'
        order.save()

        return Response(ServiceOrderSerializer(order).data)


# Seller Update Order 
class SellerUpdateServiceOrderView(generics.UpdateAPIView):
    queryset = ServiceOrder.objects.all()
    serializer_class = UpdateServiceSellerOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"

    def get_object(self):
        seller_slug = self.kwargs["seller_slug"]
        order_id = self.kwargs["id"]
        seller = get_user_by_slug_or_404(seller_slug, role="seller")
        order = get_object_or_404(ServiceOrder, id=order_id, seller=seller)

        if order.seller != self.request.user:
            self.permission_denied(self.request, message="Only seller can update this order.")
        if order.status == "cancelled":
            self.permission_denied(self.request, message="Cannot update a cancelled order.")
        return order

    def update(self, request, *args, **kwargs):
        order = self.get_object()
        serializer = self.get_serializer(order, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        # serializer.update will call instance.apply_seller_update()
        serializer.save()
        return Response(ServiceOrderSerializer(order).data, status=200)