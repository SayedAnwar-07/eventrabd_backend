from decimal import Decimal
from rest_framework import serializers
from .models import ServiceOrder

class ServiceOrderSerializer(serializers.ModelSerializer):
    seller_slug = serializers.SerializerMethodField()
    buyer_slug = serializers.SerializerMethodField()
    event_title = serializers.CharField(source='event.title', read_only=True)
    event_logo = serializers.CharField(source='event.logo', read_only=True)
    event_brand_name = serializers.CharField(source='event.brand_name', read_only=True)
    seller_name = serializers.CharField(source='seller.full_name', read_only=True)
    buyer_name = serializers.CharField(source='buyer.full_name', read_only=True)

    discount_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    net_total = serializers.SerializerMethodField()

    class Meta:
        model = ServiceOrder
        fields = [
            'id', 'seller', 'buyer',
            'seller_slug', 'buyer_slug',
            'event', 'event_title', 'event_brand_name', 'event_logo',
            'seller_name', 'buyer_name',
            'event_date', 'event_time', 'location',
            'selected_services', 'seller_agreed', 'status',
            'total_amount', 'discount_price', 'net_total', 'advance_paid',
            'remaining_amount', 'is_fully_paid', 'full_payment_date',
            'created_at', 'updated_at', 'invoice_file'
        ]
        read_only_fields = [
            'id', 'seller', 'buyer', 'created_at', 'updated_at',
            'total_amount', 'net_total', 'remaining_amount'
        ]

    def get_seller_slug(self, obj):
        return obj.seller.get_profile_slug() if obj.seller else None

    def get_buyer_slug(self, obj):
        return obj.buyer.get_profile_slug() if obj.buyer else None

    def get_net_total(self, obj):
        """Net total = total_amount - discount"""
        total = obj.total_amount or 0
        discount = obj.discount_price or 0
        return total - discount


class CreateServiceOrderSerializer(serializers.ModelSerializer):
    selected_services = serializers.ListField(
        child=serializers.CharField(),
        write_only=True
    )

    class Meta:
        model = ServiceOrder
        fields = ['event_date', 'event_time', 'location', 'selected_services']

# ---------- Buyer update serializer: only allow status changes ----------
class BuyerUpdateOrderSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=[('cancelled', 'Cancelled'), ('completed', 'Completed')])

    class Meta:
        model = ServiceOrder
        fields = ['status']

    def validate_status(self, value):
        if value not in ['cancelled', 'completed']:
            raise serializers.ValidationError("Buyer can only set status to 'cancelled' or 'completed'.")
        return value


class UpdateServiceSellerOrderSerializer(serializers.ModelSerializer):
    discount_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.00"), required=False
    )
    advance_paid = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.00"), required=False
    )

    class Meta:
        model = ServiceOrder
        fields = ["discount_price", "advance_paid", "invoice_file", "full_payment_date"]

    def validate(self, data):
        user = self.context["request"].user
        if not getattr(user, "user_type", None) == "seller":
            raise serializers.ValidationError("Only sellers can update these fields.")

        instance = getattr(self, "instance", None)
        total_amount = instance.total_amount if instance else None

        discount = data.get(
            "discount_price", getattr(instance, "discount_price", Decimal("0.00"))
        )
        if total_amount is not None and discount > total_amount:
            raise serializers.ValidationError("Discount cannot exceed total order amount.")

        return data

    def update(self, instance, validated_data):
        discount = validated_data.get("discount_price", instance.discount_price)
        advance = validated_data.get("advance_paid", instance.advance_paid)
        invoice_file = validated_data.get("invoice_file", None)
        full_payment_date = validated_data.get("full_payment_date", instance.full_payment_date)

        if invoice_file is not None:
            instance.invoice_file = invoice_file

        if full_payment_date is not None:
            instance.full_payment_date = full_payment_date

        # recalc
        instance.apply_seller_update(discount_price=discount, advance_paid=advance)
        instance.save()
        return instance
