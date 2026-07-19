import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from rest_framework import serializers

from apps.event_planner.models import EventBrand
from apps.event_services.models import EventService
from apps.hires.models import Hire, HireBookingSlot, HireStatus
from apps.users.models import User


logger = logging.getLogger(__name__)


def send_hire_notification_email(hire_pk):
    """
    Send an email to the seller after the Hire and booking slots
    have been successfully committed to the database.
    """

    try:
        hire = (
            Hire.objects
            .select_related(
                "customer",
                "service",
                "service__brand",
                "service__brand__seller",
            )
            .prefetch_related("booking_slots")
            .get(pk=hire_pk)
        )

        seller = hire.service.brand.seller
        customer = hire.customer
        service = hire.service

        booking_details = []

        for index, slot in enumerate(hire.booking_slots.all(), start=1):
            starts_at = timezone.localtime(slot.starts_at)
            ends_at = timezone.localtime(slot.ends_at)

            booking_details.append(
                f"""
Booking {index}
Date: {starts_at.strftime("%d %B %Y")}
Start time: {starts_at.strftime("%I:%M %p")}
End time: {ends_at.strftime("%I:%M %p")}
Venue: {slot.venue_name or "Not provided"}
Address: {slot.venue_address}
Location note: {slot.location_note or "None"}
""".strip()
            )

        booking_text = "\n\n".join(booking_details)

        subject = (
            f"{settings.EMAIL_SUBJECT_PREFIX} "
            f"New hire request for "
            f"{service.get_service_name_display()}"
        )

        message = f"""
Hello {seller.full_name},

You have received a new hire request on {settings.SITE_NAME}.

Customer information
--------------------
Name: {customer.full_name}
Email: {customer.email}
Contact number: {customer.contact_number or "Not provided"}

Service information
-------------------
Brand: {service.brand.brand_name}
Service: {service.get_service_name_display()}
Shift charge: {service.shift_charge}

Booking information
-------------------
{booking_text}

Customer note
-------------
{hire.customer_note or "No note provided"}

Please log in to your account to accept or reject this hire request.

Regards,
{settings.SITE_NAME}
""".strip()

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[seller.email],
            fail_silently=False,
        )

    except Exception:
        logger.exception(
            "Failed to send hire notification email for hire %s",
            hire_pk,
        )


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "contact_number",
        ]
        read_only_fields = fields


class BrandSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = EventBrand
        fields = [
            "id",
            "brand_name",
            "logo",
            "whatsapp_number",
            "service_area",
        ]
        read_only_fields = fields


class EventServiceSummarySerializer(serializers.ModelSerializer):
    service_display_name = serializers.CharField(
        source="get_service_name_display",
        read_only=True,
    )

    class Meta:
        model = EventService
        fields = [
            "id",
            "service_name",
            "service_display_name",
            "shift_charge",
            "shift_hour",
        ]
        read_only_fields = fields


class HireBookingSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = HireBookingSlot
        fields = [
            "id",
            "starts_at",
            "ends_at",
            "venue_name",
            "venue_address",
            "location_note",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]

    def validate(self, attrs):
        starts_at = attrs.get("starts_at")
        ends_at = attrs.get("ends_at")

        if starts_at and starts_at < timezone.now():
            raise serializers.ValidationError({
                "starts_at": "Booking date and time cannot be in the past."
            })

        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError({
                "ends_at": "End time must be later than start time."
            })

        return attrs


class HireDetailSerializer(serializers.ModelSerializer):
    customer = UserSummarySerializer(read_only=True)

    seller = UserSummarySerializer(
        source="service.brand.seller",
        read_only=True,
    )

    brand = BrandSummarySerializer(
        source="service.brand",
        read_only=True,
    )

    service = EventServiceSummarySerializer(read_only=True)

    booking_slots = HireBookingSlotSerializer(
        many=True,
        read_only=True,
    )

    is_accept = serializers.BooleanField(read_only=True)
    can_create_invoice = serializers.BooleanField(read_only=True)

    class Meta:
        model = Hire
        fields = [
            "id",
            "customer",
            "seller",
            "brand",
            "service",
            "status",
            "is_accept",
            "can_create_invoice",
            "customer_note",
            "seller_note",
            "accepted_at",
            "rejected_at",
            "cancelled_at",
            "completed_at",
            "booking_slots",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


class HireCreateSerializer(serializers.ModelSerializer):
    service = serializers.SlugRelatedField(
        slug_field="id",
        queryset=EventService.objects.select_related(
            "brand",
            "brand__seller",
        ),
    )

    booking_slots = HireBookingSlotSerializer(
        many=True,
        allow_empty=False,
        write_only=True,
    )

    class Meta:
        model = Hire
        fields = [
            "id",
            "service",
            "customer_note",
            "booking_slots",
            "status",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "status",
            "created_at",
        ]

    def validate(self, attrs):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(
                "Authentication is required."
            )

        customer = request.user
        service = attrs.get("service")
        booking_slots = attrs.get("booking_slots", [])

        if customer.role != "customer":
            raise serializers.ValidationError(
                "Only customers can hire a service."
            )

        if not customer.is_active:
            raise serializers.ValidationError(
                "Your account is inactive."
            )

        if not service.brand.seller.is_active:
            raise serializers.ValidationError(
                "This seller account is currently inactive."
            )

        if customer.pk == service.brand.seller_id:
            raise serializers.ValidationError(
                "You cannot hire your own service."
            )

        if not booking_slots:
            raise serializers.ValidationError({
                "booking_slots": "At least one booking slot is required."
            })

        unique_slots = set()

        for slot in booking_slots:
            slot_key = (
                slot["starts_at"],
                slot["ends_at"],
            )

            if slot_key in unique_slots:
                raise serializers.ValidationError({
                    "booking_slots": (
                        "The same booking date and time was submitted more than once."
                    )
                })

            unique_slots.add(slot_key)

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        booking_slots_data = validated_data.pop("booking_slots")
        customer = self.context["request"].user

        hire = Hire.objects.create(
            customer=customer,
            status=HireStatus.PENDING,
            **validated_data,
        )

        for slot_data in booking_slots_data:
            HireBookingSlot.objects.create(
                hire=hire,
                **slot_data,
            )

        transaction.on_commit(
            lambda hire_pk=hire.pk: send_hire_notification_email(hire_pk)
        )

        return hire

    def to_representation(self, instance):
        return HireDetailSerializer(
            instance,
            context=self.context,
        ).data


class HireSellerDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=[
            ("accept", "Accept"),
            ("reject", "Reject"),
        ]
    )

    seller_note = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=1000,
    )

    def validate(self, attrs):
        request = self.context.get("request")
        hire = self.instance

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(
                "Authentication is required."
            )

        seller = request.user

        if seller.role != "seller":
            raise serializers.ValidationError(
                "Only sellers can accept or reject hire requests."
            )

        if seller.pk != hire.service.brand.seller_id:
            raise serializers.ValidationError(
                "You cannot manage another seller's hire request."
            )

        if hire.status != HireStatus.PENDING:
            raise serializers.ValidationError({
                "decision": (
                    f"This hire request is already {hire.status}."
                )
            })

        return attrs

    def update(self, instance, validated_data):
        seller = self.context["request"].user
        decision = validated_data["decision"]
        seller_note = validated_data.get("seller_note")

        if decision == "accept":
            instance.accept(
                seller=seller,
                note=seller_note,
            )
        else:
            instance.reject(
                seller=seller,
                note=seller_note,
            )

        return instance

    def create(self, validated_data):
        raise serializers.ValidationError(
            "This serializer cannot create a hire request."
        )

    def to_representation(self, instance):
        return HireDetailSerializer(
            instance,
            context=self.context,
        ).data