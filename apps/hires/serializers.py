import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from decimal import Decimal

from rest_framework import serializers

from apps.event_planner.models import EventBrand
from apps.event_services.models import EventService
from apps.hires.models import Hire, HireBookingSlot, HireStatus
from apps.users.models import User

from django.template.loader import render_to_string
from django.utils.html import strip_tags
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def get_hire_for_email(hire_pk):
    """
    Load the Hire with all required related information.
    """

    return (
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


def get_booking_details(hire):
    """
    Prepare booking information for the HTML templates.
    """

    booking_details = []

    for index, slot in enumerate(
        hire.booking_slots.all(),
        start=1,
    ):
        starts_at = timezone.localtime(slot.starts_at)

        booking_details.append({
            "number": index,
            "date": starts_at.strftime("%d %B %Y"),
            "start_time": starts_at.strftime("%I:%M %p"),
            "venue_name": slot.venue_name or "Not provided",
            "venue_address": slot.venue_address or "Not provided",
            "location_note": slot.location_note or "None",
        })

    return booking_details


def send_html_email(
    *,
    subject,
    template_name,
    context,
    recipient_email,
):
    """
    Render and send an HTML email with a plain-text fallback.
    """

    html_message = render_to_string(
        template_name,
        context,
    )

    plain_message = strip_tags(html_message)

    send_mail(
        subject=subject,
        message=plain_message,
        html_message=html_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient_email],
        fail_silently=False,
    )


def send_hire_notification_email(hire_pk):
    """
    Send a new hire request email to the seller.
    """

    try:
        hire = get_hire_for_email(hire_pk)

        seller = hire.service.brand.seller
        customer = hire.customer
        service = hire.service

        if not seller.email:
            logger.warning(
                "Seller has no email address for hire %s",
                hire_pk,
            )
            return

        subject = (
            f"{settings.EMAIL_SUBJECT_PREFIX} "
            f"New hire request for "
            f"{service.get_service_name_display()}"
        ).strip()

        context = {
            "site_name": settings.SITE_NAME,
            "seller": seller,
            "customer": customer,
            "brand": service.brand,
            "service": service,
            "service_name": service.get_service_name_display(),
            "shift_charge": service.shift_charge,
            "customer_note": (
                hire.customer_note or "No note provided"
            ),
            "booking_details": get_booking_details(hire),
            "dashboard_url": getattr(
                settings,
                "FRONTEND_URL",
                "",
            ),
        }

        send_html_email(
            subject=subject,
            template_name="hireEmail/seller_email.html",
            context=context,
            recipient_email=seller.email,
        )

    except Exception:
        logger.exception(
            "Failed to send hire notification email for hire %s",
            hire_pk,
        )


def send_hire_acceptance_email(hire_pk):
    """
    Notify the customer after the seller accepts the hire.
    """

    try:
        hire = get_hire_for_email(hire_pk)

        customer = hire.customer
        seller = hire.service.brand.seller
        service = hire.service

        if not customer.email:
            logger.warning(
                "Customer has no email address for accepted hire %s",
                hire_pk,
            )
            return

        subject = (
            f"{settings.EMAIL_SUBJECT_PREFIX} "
            f"Hire request accepted"
        ).strip()

        context = {
            "site_name": settings.SITE_NAME,
            "status": "accepted",
            "is_accepted": True,
            "customer": customer,
            "seller": seller,
            "brand": service.brand,
            "service": service,
            "service_name": service.get_service_name_display(),
            "seller_note": (
                hire.seller_note
                or "No additional information was provided."
            ),
            "booking_details": get_booking_details(hire),
            "dashboard_url": getattr(
                settings,
                "FRONTEND_URL",
                "",
            ),
        }

        send_html_email(
            subject=subject,
            template_name="hireEmail/customer_email.html",
            context=context,
            recipient_email=customer.email,
        )

    except Exception:
        logger.exception(
            "Failed to send acceptance email for hire %s",
            hire_pk,
        )


def send_hire_rejection_email(hire_pk):
    """
    Notify the customer after the seller rejects the hire.
    """

    try:
        hire = get_hire_for_email(hire_pk)

        customer = hire.customer
        seller = hire.service.brand.seller
        service = hire.service

        if not customer.email:
            logger.warning(
                "Customer has no email address for rejected hire %s",
                hire_pk,
            )
            return

        subject = (
            f"{settings.EMAIL_SUBJECT_PREFIX} "
            f"Hire request unavailable"
        ).strip()

        context = {
            "site_name": settings.SITE_NAME,
            "status": "rejected",
            "is_accepted": False,
            "customer": customer,
            "seller": seller,
            "brand": service.brand,
            "service": service,
            "service_name": service.get_service_name_display(),
            "seller_note": (
                hire.seller_note
                or "No additional information was provided."
            ),
            "booking_details": get_booking_details(hire),
            "dashboard_url": getattr(
                settings,
                "FRONTEND_URL",
                "",
            ),
        }

        send_html_email(
            subject=subject,
            template_name="hireEmail/customer_email.html",
            context=context,
            recipient_email=customer.email,
        )

    except Exception:
        logger.exception(
            "Failed to send rejection email for hire %s",
            hire_pk,
        )

class UserSummarySerializer(serializers.ModelSerializer):
    profile_image_url = serializers.SerializerMethodField()

    class Meta:
        model = User

        fields = [
            "id",
            "full_name",
            "profile_image_url",
            "email",
            "contact_number",
        ]

        read_only_fields = fields

    def get_profile_image_url(self, obj):
        if not obj.profile_image:
            return None

        try:
            return obj.profile_image.build_url(
                transformation=[
                    {
                        "width": 500,
                        "height": 500,
                        "crop": "limit",
                    }
                ],
                quality="auto",
                fetch_format="auto",
            )

        except Exception:
            return None


class BrandSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = EventBrand
        fields = [
            "id",
            "display_name",
            "brand_name",
            "logo",
            "whatsapp_number",
            "district",
            "division",
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
    customer_whatsapp_number = serializers.CharField(
        source="whatsapp_number",
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=20,
    )
    google_map_link = serializers.URLField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=500,
    )
    class Meta:
        model = HireBookingSlot
        fields = [
            "id",
            "starts_at",
            "customer_whatsapp_number",
            "venue_name",
            "venue_address",
            "location_note",
            "google_map_link",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]

    def validate(self, attrs):
        starts_at = attrs.get("starts_at")
        google_map_link = attrs.get("google_map_link")

        if starts_at and starts_at < timezone.now():
            raise serializers.ValidationError({
                "starts_at": "Booking date and time cannot be in the past."
            })

        if google_map_link:
            parsed_url = urlparse(google_map_link)

            allowed_hosts = {
                "maps.app.goo.gl",
                "maps.google.com",
                "www.google.com",
            }

            if (
                parsed_url.scheme != "https"
                or parsed_url.netloc not in allowed_hosts
                or (
                    parsed_url.netloc == "www.google.com"
                    and not parsed_url.path.startswith("/maps")
                )
            ):
                raise serializers.ValidationError({
                    "google_map_link": (
                        "Only Google Maps shared links are supported."
                    )
                })

        return attrs


class HireDetailSerializer(serializers.ModelSerializer):
    customer = UserSummarySerializer(read_only=True)
    invoice = serializers.SerializerMethodField()
    service_summary = serializers.SerializerMethodField()

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
            "service_summary",
            "status",
            "is_accept",
            "can_create_invoice",
            "invoice",
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

        read_only_fields = [
            "id",
            "status",
            "customer_note",
            "seller_note",
            "accepted_at",
            "rejected_at",
            "cancelled_at",
            "completed_at",
            "created_at",
            "updated_at",
        ]
        
    def get_service_summary(self, obj):
        slot_count = len(obj.booking_slots.all())

        shift_charge = obj.service.shift_charge or Decimal("0.00")
        shift_hour = obj.service.shift_hour or 0

        total_amount = shift_charge * slot_count
        total_shift_hours = shift_hour * slot_count

        return {
            "slot_count": slot_count,
            "shift_hour_per_slot": shift_hour,
            "total_shift_hours": total_shift_hours,
            "shift_charge_per_slot": f"{shift_charge:.2f}",
            "total_amount": f"{total_amount:.2f}",
        }
        
    def get_invoice(self, obj):
        if not hasattr(obj, "invoice"):
            return None

        invoice = obj.invoice

        return {
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "payment_status": invoice.payment_status,
            "total": invoice.total,
            "due_payment": invoice.due_payment,
            "due_payment_last_date": (
                invoice.due_payment_last_date
            ),
        }


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

        # FIX: brand or seller may not exist for a malformed/incomplete
        # service record; accessing them directly raised an unhandled
        # ObjectDoesNotExist (500) instead of a clean validation error.
        try:
            seller = service.brand.seller
        except ObjectDoesNotExist:
            raise serializers.ValidationError(
                "This service does not belong to a valid seller."
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

        try:
            owner_id = hire.service.brand.seller_id
        except ObjectDoesNotExist:
            raise serializers.ValidationError(
                "This hire's service does not belong to a valid seller."
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

    @transaction.atomic
    def update(self, instance, validated_data):
        seller = self.context["request"].user
        decision = validated_data["decision"]
        seller_note = validated_data.get("seller_note")

        if decision == "accept":
            instance.accept(
                seller=seller,
                note=seller_note,
            )

            transaction.on_commit(
                lambda hire_pk=instance.pk: (
                    send_hire_acceptance_email(hire_pk)
                )
            )

        else:
            instance.reject(
                seller=seller,
                note=seller_note,
            )

            transaction.on_commit(
                lambda hire_pk=instance.pk: (
                    send_hire_rejection_email(hire_pk)
                )
            )

        return instance