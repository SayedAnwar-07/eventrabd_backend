import logging
from decimal import Decimal
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from rest_framework import serializers

from apps.event_planner.models import EventBrand
from apps.event_services.models import EventService
from apps.hires.models import (
    EventType,
    Hire,
    HireBookingItem,
    HireBookingSlot,
    HireStatus,
)

from apps.notifications.models import (
    Notification,
    NotificationType,
)

from apps.packages.models import ServicePackage
from apps.users.models import User


logger = logging.getLogger(__name__)

MAX_BOOKING_SLOTS = 5


# =========================================================
# Email helpers
# =========================================================

def get_hire_for_email(hire_pk):
    return (
        Hire.objects
        .select_related(
            "customer",
            "service",
            "package",
            "service__brand",
            "service__brand__seller",
            "cancelled_by",
        )
        .prefetch_related(
            "booking_slots",
            "booking_items",
            "booking_items__package",
            "booking_items__booking_slots",
        )
        .get(pk=hire_pk)
    )


def get_booking_details(hire):
    booking_details = []

    for index, slot in enumerate(
        hire.booking_slots.all(),
        start=1,
    ):
        if slot.starts_at:
            starts_at = timezone.localtime(slot.starts_at)

            date = starts_at.strftime("%d %B %Y")
            start_time = starts_at.strftime("%I:%M %p")
        else:
            date = "Not provided"
            start_time = "Not provided"

        booking_details.append({
            "number": index,
            "booking_title": (
                slot.booking_item.booking_title
                if slot.booking_item_id
                else hire.booking_title
            ),
            "event_type": (
                slot.get_event_type_display()
                if slot.event_type
                else "Not provided"
            ),
            "date": date,
            "start_time": start_time,
            "venue_name": (
                slot.venue_name or "Not provided"
            ),
            "venue_address": (
                slot.venue_address or "Not provided"
            ),
        })

    return booking_details


def send_html_email(
    *,
    subject,
    template_name,
    context,
    recipient_email,
):
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
    try:
        hire = get_hire_for_email(hire_pk)

        seller = hire.service.brand.seller
        customer = hire.customer
        service = hire.service

        if not seller.email:
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
            "service_name": hire.booking_title,
            "shift_charge": hire.total_booking_price,
            "customer_note": (
                hire.customer_note
                or "No note provided"
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
    try:
        hire = get_hire_for_email(hire_pk)

        customer = hire.customer
        seller = hire.service.brand.seller
        service = hire.service

        if not customer.email:
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
            "service_name": hire.booking_title,
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
    try:
        hire = get_hire_for_email(hire_pk)

        customer = hire.customer
        seller = hire.service.brand.seller
        service = hire.service

        if not customer.email:
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
            "service_name": hire.booking_title,
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


# =========================================================
# Summary serializers
# =========================================================

class HirePackageSummarySerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = ServicePackage

        fields = [
            "id",
            "package_title",
            "package_price",
        ]

        read_only_fields = fields


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
            "division",
            "office_address",
        ]

        read_only_fields = fields


class EventServiceSummarySerializer(
    serializers.ModelSerializer
):
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


# =========================================================
# Booking slot
# =========================================================

class HireBookingSlotSerializer(
    serializers.ModelSerializer
):
    event_type = serializers.CharField(
        read_only=True,
    )

    starts_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
    )

    venue_name = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=255,
    )

    venue_address = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
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
            "event_type",
            "starts_at",
            "venue_name",
            "venue_address",
            "google_map_link",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "event_type",
            "created_at",
        ]

    def validate(self, attrs):
        starts_at = attrs.get("starts_at")
        google_map_link = attrs.get("google_map_link")

        if starts_at and starts_at < timezone.now():
            raise serializers.ValidationError({
                "starts_at": (
                    "Booking date and time cannot be in the past."
                )
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


# =========================================================
# Booking item detail
# =========================================================

class HireBookingItemDetailSerializer(
    serializers.ModelSerializer
):
    package = HirePackageSummarySerializer(
        read_only=True,
    )

    booking_title = serializers.CharField(
        read_only=True,
    )

    unit_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    total_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    is_package = serializers.BooleanField(
        read_only=True,
    )

    booking_slots = HireBookingSlotSerializer(
        many=True,
        read_only=True,
    )

    event_types = serializers.SerializerMethodField()

    class Meta:
        model = HireBookingItem

        fields = [
            "id",
            "package",
            "quantity",
            "booking_title",
            "unit_price",
            "total_price",
            "is_package",
            "event_types",
            "booking_slots",
            "created_at",
        ]

        read_only_fields = fields

    def get_event_types(self, obj):
        return [
            slot.event_type
            for slot in obj.booking_slots.all()
            if slot.event_type
        ]


# =========================================================
# Hire detail
# =========================================================

class HireDetailSerializer(
    serializers.ModelSerializer
):
    customer = UserSummarySerializer(
        read_only=True,
    )

    seller = UserSummarySerializer(
        source="service.brand.seller",
        read_only=True,
    )

    brand = BrandSummarySerializer(
        source="service.brand",
        read_only=True,
    )

    service = EventServiceSummarySerializer(
        read_only=True,
    )

    # Legacy field, useful for old hires.
    package = HirePackageSummarySerializer(
        read_only=True,
    )

    booking_items = HireBookingItemDetailSerializer(
        many=True,
        read_only=True,
    )

    booking_slots = HireBookingSlotSerializer(
        many=True,
        read_only=True,
    )

    booking_title = serializers.CharField(
        read_only=True,
    )

    booking_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    total_booking_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    is_package_hire = serializers.BooleanField(
        read_only=True,
    )

    is_accept = serializers.BooleanField(
        read_only=True,
    )

    can_create_invoice = serializers.BooleanField(
        read_only=True,
    )

    invoice = serializers.SerializerMethodField()

    service_summary = serializers.SerializerMethodField()

    class Meta:
        model = Hire

        fields = [
            "id",
            "customer",
            "seller",
            "brand",
            "service",

            # Old compatibility fields
            "package",
            "quantity",
            "event_type",

            # New multiple booking system
            "booking_items",

            "booking_title",
            "booking_price",
            "total_booking_price",
            "is_package_hire",
            "service_summary",

            "status",
            "is_accept",
            "can_create_invoice",
            "invoice",

            "customer_whatsapp_number",
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

    def get_service_summary(self, obj):
        items = list(obj.booking_items.all())

        shift_hour = obj.service.shift_hour or 0

        # New booking-item system.
        if items:
            total_quantity = sum(
                item.quantity
                for item in items
            )

            total_amount = sum(
                (
                    item.total_price
                    for item in items
                ),
                Decimal("0.00"),
            )

            unit_price = (
                items[0].unit_price
                if len(items) == 1
                else None
            )

            return {
                "title": obj.booking_title,
                "booking_option_count": len(items),
                "quantity": total_quantity,
                "slot_count": len(
                    obj.booking_slots.all()
                ),
                "shift_hour_per_slot": shift_hour,
                "total_shift_hours": (
                    shift_hour * total_quantity
                ),
                "shift_charge_per_slot": (
                    f"{unit_price:.2f}"
                    if unit_price is not None
                    else None
                ),
                "total_amount": (
                    f"{total_amount:.2f}"
                ),
            }

        # Old hire compatibility.
        shift_charge = (
            obj.booking_price
            or Decimal("0.00")
        )

        return {
            "title": obj.booking_title,
            "booking_option_count": 1,
            "quantity": obj.quantity,
            "slot_count": len(
                obj.booking_slots.all()
            ),
            "shift_hour_per_slot": shift_hour,
            "total_shift_hours": (
                shift_hour * obj.quantity
            ),
            "shift_charge_per_slot": (
                f"{shift_charge:.2f}"
            ),
            "total_amount": (
                f"{obj.total_booking_price:.2f}"
            ),
        }

    def get_invoice(self, obj):
        if not hasattr(obj, "invoice"):
            return None

        invoice = obj.invoice

        return {
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "payment_status": invoice.payment_status,
            "customer_agreed": invoice.customer_agreed,
            "total": invoice.total,
            "due_payment": invoice.due_payment,
            "due_payment_last_date": (
                invoice.due_payment_last_date
            ),
            "created_at": invoice.created_at,
            "updated_at": invoice.updated_at,
        }


# =========================================================
# Booking item create
# =========================================================

class HireBookingItemCreateSerializer(
    serializers.Serializer
):
    package = serializers.SlugRelatedField(
        slug_field="id",
        queryset=ServicePackage.objects.select_related(
            "service",
        ),
        required=False,
        allow_null=True,
    )

    quantity = serializers.IntegerField(
        min_value=1,
        max_value=MAX_BOOKING_SLOTS,
        default=1,
    )

    event_types = serializers.ListField(
        child=serializers.ChoiceField(
            choices=EventType.choices,
        ),
        allow_empty=False,
    )

    booking_slots = HireBookingSlotSerializer(
        many=True,
        allow_empty=False,
    )

    def validate(self, attrs):
        quantity = attrs.get("quantity", 1)

        event_types = attrs.get(
            "event_types",
            [],
        )

        booking_slots = attrs.get(
            "booking_slots",
            [],
        )

        if len(event_types) != quantity:
            raise serializers.ValidationError({
                "event_types": (
                    f"Quantity is {quantity}, so exactly "
                    f"{quantity} event type(s) are required."
                )
            })

        if len(booking_slots) != quantity:
            raise serializers.ValidationError({
                "booking_slots": (
                    f"Quantity is {quantity}, so exactly "
                    f"{quantity} booking slot(s) are required."
                )
            })

        # Same event cannot repeat inside same item.
        if len(event_types) != len(set(event_types)):
            raise serializers.ValidationError({
                "event_types": (
                    "The same event type cannot be selected "
                    "more than once for the same booking option."
                )
            })

        return attrs


# =========================================================
# Hire create
# =========================================================

class HireCreateSerializer(
    serializers.ModelSerializer
):
    service = serializers.SlugRelatedField(
        slug_field="id",
        queryset=EventService.objects.select_related(
            "brand",
            "brand__seller",
        ),
    )

    booking_items = HireBookingItemCreateSerializer(
        many=True,
        allow_empty=False,
        write_only=True,
    )

    class Meta:
        model = Hire

        fields = [
            "id",
            "service",
            "booking_items",
            "customer_note",
            "customer_whatsapp_number",
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

        if (
            not request
            or not request.user.is_authenticated
        ):
            raise serializers.ValidationError(
                "Authentication is required."
            )

        customer = request.user

        service = attrs.get("service")

        booking_items = attrs.get(
            "booking_items",
            [],
        )

        if customer.role != "customer":
            raise serializers.ValidationError(
                "Only customers can hire a service."
            )

        if not customer.is_active:
            raise serializers.ValidationError(
                "Your account is inactive."
            )

        try:
            seller = service.brand.seller
        except ObjectDoesNotExist:
            raise serializers.ValidationError(
                "This service does not belong "
                "to a valid seller."
            )

        if not seller.is_active:
            raise serializers.ValidationError(
                "This seller account is currently inactive."
            )

        if customer.pk == seller.pk:
            raise serializers.ValidationError(
                "You cannot hire your own service."
            )

        if not booking_items:
            raise serializers.ValidationError({
                "booking_items": (
                    "At least one booking option is required."
                )
            })

        # Total events across all packages/service.
        total_quantity = sum(
            item.get("quantity", 1)
            for item in booking_items
        )

        if total_quantity > MAX_BOOKING_SLOTS:
            raise serializers.ValidationError({
                "booking_items": (
                    f"You can create a maximum of "
                    f"{MAX_BOOKING_SLOTS} bookings."
                )
            })

        # /*
        # Rule:
        # One option => quantity may increase.
        # Multiple different options => every quantity must be 1.
        # */
        if len(booking_items) > 1:
            for index, item in enumerate(
                booking_items
            ):
                if item.get("quantity", 1) != 1:
                    raise serializers.ValidationError({
                        "booking_items": {
                            str(index): {
                                "quantity": (
                                    "Quantity must be 1 when "
                                    "multiple booking options "
                                    "are selected."
                                )
                            }
                        }
                    })

        seen_packages = set()
        normal_service_count = 0

        all_starts_at = set()

        for index, item in enumerate(
            booking_items
        ):
            package = item.get("package")

            if package:
                if package.service_id != service.id:
                    raise serializers.ValidationError({
                        "booking_items": {
                            str(index): {
                                "package": (
                                    "This package does not "
                                    "belong to the selected service."
                                )
                            }
                        }
                    })

                package_id = str(package.id)

                if package_id in seen_packages:
                    raise serializers.ValidationError({
                        "booking_items": {
                            str(index): {
                                "package": (
                                    "The same package cannot "
                                    "be added twice. Increase "
                                    "its quantity instead."
                                )
                            }
                        }
                    })

                seen_packages.add(package_id)

            else:
                normal_service_count += 1

                if normal_service_count > 1:
                    raise serializers.ValidationError({
                        "booking_items": {
                            str(index): {
                                "package": (
                                    "Normal service can only "
                                    "be added once."
                                )
                            }
                        }
                    })

            booking_slots = item.get(
                "booking_slots",
                [],
            )

            for slot_index, slot in enumerate(
                booking_slots
            ):
                starts_at = slot.get(
                    "starts_at"
                )

                if not starts_at:
                    continue

                if starts_at in all_starts_at:
                    raise serializers.ValidationError({
                        "booking_items": {
                            str(index): {
                                "booking_slots": {
                                    str(slot_index): {
                                        "starts_at": (
                                            "This booking date "
                                            "and time is duplicated."
                                        )
                                    }
                                }
                            }
                        }
                    })

                all_starts_at.add(starts_at)

        # Only first slot of whole Hire is required.
        first_item = booking_items[0]

        first_slot = first_item[
            "booking_slots"
        ][0]

        first_slot_errors = {}

        if not first_slot.get("starts_at"):
            first_slot_errors["starts_at"] = (
                "Start date and time is required "
                "for the first booking."
            )

        if not first_slot.get("venue_name"):
            first_slot_errors["venue_name"] = (
                "Venue name is required "
                "for the first booking."
            )

        if not first_slot.get("venue_address"):
            first_slot_errors["venue_address"] = (
                "Venue address is required "
                "for the first booking."
            )

        if first_slot_errors:
            raise serializers.ValidationError({
                "booking_items": {
                    "0": {
                        "booking_slots": {
                            "0": first_slot_errors,
                        }
                    }
                }
            })

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        booking_items_data = validated_data.pop(
            "booking_items"
        )

        customer = self.context["request"].user

        first_item_data = booking_items_data[0]

        first_event_type = (
            first_item_data["event_types"][0]
        )

        # /*
        #  * Keep old fields compatible.
        #  *
        #  * One option:
        #  * old package/quantity fields are populated.
        #  *
        #  * Multiple options:
        #  * booking_items becomes source of truth.
        #  */
        if len(booking_items_data) == 1:
            legacy_package = (
                first_item_data.get("package")
            )

            legacy_quantity = (
                first_item_data.get(
                    "quantity",
                    1,
                )
            )

            package_title_snapshot = (
                legacy_package.package_title
                if legacy_package
                else None
            )

            package_price_snapshot = (
                legacy_package.package_price
                if legacy_package
                else None
            )

        else:
            legacy_package = None
            legacy_quantity = 1
            package_title_snapshot = None
            package_price_snapshot = None

        hire = Hire.objects.create(
            customer=customer,
            status=HireStatus.PENDING,
            event_type=first_event_type,
            package=legacy_package,
            quantity=legacy_quantity,
            package_title_snapshot=(
                package_title_snapshot
            ),
            package_price_snapshot=(
                package_price_snapshot
            ),
            **validated_data,
        )

        for item_data in booking_items_data:
            package = item_data.get("package")

            quantity = item_data.get(
                "quantity",
                1,
            )

            event_types = item_data[
                "event_types"
            ]

            booking_slots_data = item_data[
                "booking_slots"
            ]

            booking_item = (
                HireBookingItem.objects.create(
                    hire=hire,
                    package=package,
                    quantity=quantity,
                )
            )

            for event_type, slot_data in zip(
                event_types,
                booking_slots_data,
            ):
                HireBookingSlot.objects.create(
                    hire=hire,
                    booking_item=booking_item,
                    event_type=event_type,
                    **slot_data,
                )
        # Seller in-app notification
        seller = hire.service.brand.seller

        Notification.objects.get_or_create(
            recipient=seller,
            hire=hire,
            notification_type=NotificationType.HIRE_CREATED,
            defaults={
                "title": "New hire request",
                "message": (
                    f"{customer.full_name} sent you a new hire request "
                    f"for {hire.booking_title}."
                ),
                "data": {
                    "hire_id": str(hire.id),
                },
            },
        )

        # Existing email notification
        transaction.on_commit(
            lambda hire_pk=hire.pk: (
                send_hire_notification_email(
                    hire_pk
                )
            )
        )

        return hire


# =========================================================
# Seller accept / reject
# =========================================================

class HireSellerDecisionSerializer(
    serializers.Serializer
):
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

        if (
            not request
            or not request.user.is_authenticated
        ):
            raise serializers.ValidationError(
                "Authentication is required."
            )

        seller = request.user

        if seller.role != "seller":
            raise serializers.ValidationError(
                "Only sellers can accept or reject "
                "hire requests."
            )

        try:
            owner_id = (
                hire.service.brand.seller_id
            )
        except ObjectDoesNotExist:
            raise serializers.ValidationError(
                "This hire's service does not "
                "belong to a valid seller."
            )

        if seller.pk != owner_id:
            raise serializers.ValidationError(
                "You cannot manage another seller's "
                "hire request."
            )

        if hire.status != HireStatus.PENDING:
            raise serializers.ValidationError({
                "decision": (
                    f"This hire request is already "
                    f"{hire.status}."
                )
            })

        return attrs

    @transaction.atomic
    def update(
        self,
        instance,
        validated_data,
    ):
        seller = self.context[
            "request"
        ].user

        decision = validated_data[
            "decision"
        ]

        seller_note = validated_data.get(
            "seller_note"
        )

        if decision == "accept":
            instance.accept(
                seller=seller,
                note=seller_note,
            )

            transaction.on_commit(
                lambda hire_pk=instance.pk: (
                    send_hire_acceptance_email(
                        hire_pk
                    )
                )
            )

        else:
            instance.reject(
                seller=seller,
                note=seller_note,
            )

            transaction.on_commit(
                lambda hire_pk=instance.pk: (
                    send_hire_rejection_email(
                        hire_pk
                    )
                )
            )

        return instance