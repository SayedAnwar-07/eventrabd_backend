from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.hires.models import (
    Hire,
    HireBookingSlot,
    HireStatus,
)
from apps.notifications.services import (
    create_invoice_created_notification,
    create_invoice_updated_notification,
)

from .emails import send_invoice_created_email
from .models import (
    Invoice,
    InvoiceSlotShift,
    MAX_TERM_LENGTH,
    MAX_TERMS_CONDITIONS,
    ZERO_AMOUNT,
)


# =========================================================
# Helper functions
# =========================================================


def convert_model_validation_error(error):
    """
    Convert Django model ValidationError into
    DRF ValidationError.
    """

    if hasattr(error, "message_dict"):
        return serializers.ValidationError(
            error.message_dict
        )

    if hasattr(error, "messages"):
        return serializers.ValidationError({
            "detail": error.messages,
        })

    return serializers.ValidationError({
        "detail": str(error),
    })


def get_hire_slot_count(hire):
    """
    Ensure the Hire has booking slots and that every
    selected booking slot has a booking date/time.

    One Hire can have only one Invoice, so incomplete
    booking slots must not be skipped.
    """

    total_slot_count = hire.booking_slots.count()

    if total_slot_count < 1:
        raise serializers.ValidationError({
            "hire": (
                "This hire has no booking slots."
            )
        })

    incomplete_slot_count = (
        hire.booking_slots
        .filter(starts_at__isnull=True)
        .count()
    )

    if incomplete_slot_count > 0:
        raise serializers.ValidationError({
            "hire": (
                "An invoice cannot be created until "
                "all selected booking events have a "
                "booking date and time. "
                f"{incomplete_slot_count} booking slot(s) "
                "are still incomplete."
            )
        })

    return total_slot_count


def validate_slot_shifts(
    hire,
    slot_shifts,
):
    """
    Ensure every booking slot of this Hire receives
    exactly one shift-count entry.
    """

    hire_slot_ids = set(
        hire.booking_slots.values_list(
            "id",
            flat=True,
        )
    )

    seen_slot_ids = set()

    for item in slot_shifts:
        booking_slot = item["booking_slot"]

        if booking_slot.hire_id != hire.id:
            raise serializers.ValidationError({
                "slot_shifts": (
                    "One of the booking slots does not "
                    "belong to this hire request."
                )
            })

        if booking_slot.starts_at is None:
            raise serializers.ValidationError({
                "slot_shifts": (
                    "A shift count cannot be assigned "
                    "to an event that does not have a "
                    "booking date and time."
                )
            })

        if booking_slot.id in seen_slot_ids:
            raise serializers.ValidationError({
                "slot_shifts": (
                    "Each booking slot can only be "
                    "assigned a shift count once."
                )
            })

        seen_slot_ids.add(
            booking_slot.id
        )

    missing_slot_ids = (
        hire_slot_ids - seen_slot_ids
    )

    if missing_slot_ids:
        raise serializers.ValidationError({
            "slot_shifts": (
                "A shift count must be provided for "
                "every booking slot. "
                f"Missing shift count for "
                f"{len(missing_slot_ids)} "
                "booking slot(s)."
            )
        })

    return slot_shifts


def get_booking_slot_unit_price(
    hire,
    booking_slot,
):
    """
    Get the correct unit price for a booking slot.

    New Hire:
        booking slot
        -> booking item
        -> package snapshot/service price

    Legacy Hire:
        fallback to hire.booking_price
    """

    if booking_slot.booking_item_id:
        return (
            booking_slot.booking_item.unit_price
            or ZERO_AMOUNT
        )

    return (
        hire.booking_price
        or ZERO_AMOUNT
    )


def calculate_service_price_from_slot_shifts(
    hire,
    slot_shifts,
):
    """
    Calculate invoice service price using the unit
    price of each booking option.

    Example:

        Package A:
            10,000 × 2 shifts = 20,000

        Package B:
            15,000 × 1 shift = 15,000

        service_price = 35,000
    """

    total_service_price = ZERO_AMOUNT

    for item in slot_shifts:
        booking_slot = item[
            "booking_slot"
        ]

        shift_count = item[
            "shift_count"
        ]

        unit_price = (
            get_booking_slot_unit_price(
                hire=hire,
                booking_slot=booking_slot,
            )
        )

        if unit_price <= ZERO_AMOUNT:
            raise serializers.ValidationError({
                "service_price": (
                    "Service price cannot be calculated "
                    "because one of the selected booking "
                    "options does not have a valid price."
                )
            })

        total_service_price += (
            unit_price * shift_count
        )

    return total_service_price


def apply_slot_shifts(
    invoice,
    slot_shifts,
):
    """
    Replace InvoiceSlotShift rows with the submitted
    validated slot-shift configuration.
    """

    invoice.slot_shifts.all().delete()

    for item in slot_shifts:
        InvoiceSlotShift.objects.create(
            invoice=invoice,
            booking_slot=item[
                "booking_slot"
            ],
            shift_count=item[
                "shift_count"
            ],
        )


def validate_invoice_financial_data(
    attrs,
    instance=None,
):
    """
    Validate calculated invoice financial values.

    Formula:

        Service Price
        + Additional Charge
        - Discount
        = Total
        - Advance Payment
        = Due Payment
    """

    if instance is not None:
        service_price = attrs.get(
            "service_price",
            instance.service_price,
        )

        additional_charge = attrs.get(
            "additional_charge",
            instance.additional_charge,
        )

        additional_charge_reason = attrs.get(
            "additional_charge_reason",
            instance.additional_charge_reason,
        )

        discount_price = attrs.get(
            "discount_price",
            instance.discount_price,
        )

        advance_payment = attrs.get(
            "advance_payment",
            instance.advance_payment,
        )

        issue_date = (
            instance.issue_date
        )

        due_payment_last_date = attrs.get(
            "due_payment_last_date",
            instance.due_payment_last_date,
        )

    else:
        service_price = attrs.get(
            "service_price",
            ZERO_AMOUNT,
        )

        additional_charge = attrs.get(
            "additional_charge",
            ZERO_AMOUNT,
        )

        additional_charge_reason = attrs.get(
            "additional_charge_reason",
        )

        discount_price = attrs.get(
            "discount_price",
            ZERO_AMOUNT,
        )

        advance_payment = attrs.get(
            "advance_payment",
            ZERO_AMOUNT,
        )

        issue_date = (
            timezone.localdate()
        )

        due_payment_last_date = attrs.get(
            "due_payment_last_date"
        )

    service_price = (
        service_price or ZERO_AMOUNT
    )

    additional_charge = (
        additional_charge or ZERO_AMOUNT
    )

    discount_price = (
        discount_price or ZERO_AMOUNT
    )

    advance_payment = (
        advance_payment or ZERO_AMOUNT
    )

    errors = {}

    if service_price <= ZERO_AMOUNT:
        errors["service_price"] = (
            "Service price must be greater than zero."
        )

    if additional_charge < ZERO_AMOUNT:
        errors["additional_charge"] = (
            "Additional charge cannot be negative."
        )

    if (
        additional_charge > ZERO_AMOUNT
        and not (
            additional_charge_reason
            and additional_charge_reason.strip()
        )
    ):
        errors["additional_charge_reason"] = (
            "Please provide a reason for "
            "the additional charge."
        )

    if discount_price < ZERO_AMOUNT:
        errors["discount_price"] = (
            "Discount price cannot be negative."
        )

    amount_before_discount = (
        service_price
        + additional_charge
    )

    if (
        discount_price
        > amount_before_discount
    ):
        errors["discount_price"] = (
            "Discount cannot be greater than "
            "the total amount before discount."
        )

    calculated_total = (
        amount_before_discount
        - discount_price
    )

    if advance_payment < ZERO_AMOUNT:
        errors["advance_payment"] = (
            "Advance payment cannot be negative."
        )

    if advance_payment > calculated_total:
        errors["advance_payment"] = (
            "Advance payment cannot be greater "
            "than the total amount."
        )

    if (
        issue_date
        and due_payment_last_date
        and due_payment_last_date
        < issue_date
    ):
        errors["due_payment_last_date"] = (
            "Due payment date cannot be earlier "
            "than the invoice date."
        )

    if errors:
        raise serializers.ValidationError(
            errors
        )

    return attrs


# =========================================================
# Per-slot shift input
# =========================================================


class InvoiceSlotShiftInputSerializer(
    serializers.Serializer
):
    """
    Shift count for one Hire booking slot.
    """

    booking_slot = (
        serializers.PrimaryKeyRelatedField(
            queryset=(
                HireBookingSlot.objects
                .select_related(
                    "hire",
                    "hire__service",
                    "booking_item",
                    "booking_item__package",
                )
            ),
            error_messages={
                "does_not_exist": (
                    "The selected booking slot "
                    "does not exist."
                ),
                "incorrect_type": (
                    "Invalid booking slot ID."
                ),
            },
        )
    )

    shift_count = (
        serializers.IntegerField(
            min_value=1,
            error_messages={
                "invalid": (
                    "Shift count must be a "
                    "valid whole number."
                ),
                "min_value": (
                    "Shift count must be at least 1."
                ),
            },
        )
    )


# =========================================================
# Invoice detail serializer
# =========================================================


class InvoiceDetailSerializer(
    serializers.ModelSerializer
):
    hire = (
        serializers.SerializerMethodField()
    )

    customer = (
        serializers.SerializerMethodField()
    )

    seller = (
        serializers.SerializerMethodField()
    )

    brand = (
        serializers.SerializerMethodField()
    )

    service = (
        serializers.SerializerMethodField()
    )

    service_summary = (
        serializers.SerializerMethodField()
    )

    sub_total = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    total = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    due_payment = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    is_paid = serializers.BooleanField(
        read_only=True,
    )

    is_partially_paid = (
        serializers.BooleanField(
            read_only=True,
        )
    )

    is_overdue = (
        serializers.BooleanField(
            read_only=True,
        )
    )

    payment_status = (
        serializers.CharField(
            read_only=True,
        )
    )

    customer_agreed = (
        serializers.BooleanField(
            read_only=True,
            allow_null=True,
        )
    )

    can_edit = (
        serializers.SerializerMethodField()
    )

    can_customer_decide = (
        serializers.SerializerMethodField()
    )

    class Meta:
        model = Invoice

        fields = [
            "id",
            "invoice_number",
            "hire",
            "customer",
            "seller",
            "brand",
            "service",
            "service_summary",
            "issue_date",
            "shift_count",
            "due_payment_last_date",
            "service_price",
            "additional_charge",
            "additional_charge_reason",
            "discount_price",
            "advance_payment",
            "sub_total",
            "total",
            "due_payment",
            "is_paid",
            "is_partially_paid",
            "is_overdue",
            "payment_status",
            "seller_note",
            "terms_conditions",
            "customer_agreed",
            "can_edit",
            "can_customer_decide",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields

    def get_hire(self, obj):
        return {
            "id": str(obj.hire_id),
            "status": obj.hire.status,
        }

    def get_customer(self, obj):
        return {
            "id": str(
                obj.hire.customer_id
            ),
            "full_name": (
                obj.customer_name_snapshot
            ),
            "email": (
                obj.customer_email_snapshot
            ),
            "whatsapp_number": (
                obj.customer_whatsapp_snapshot
            ),
        }

    def get_seller(self, obj):
        seller = (
            obj.hire
            .service
            .brand
            .seller
        )

        return {
            "id": str(seller.id),
            "full_name": (
                obj.seller_name_snapshot
            ),
            "contact_number": (
                obj.seller_contact_snapshot
            ),
        }

    def get_brand(self, obj):
        brand = (
            obj.hire.service.brand
        )

        return {
            "id": str(brand.id),
            "brand_name": (
                obj.brand_name_snapshot
            ),
            "display_name": (
                obj.display_name_snapshot
            ),
        }

    def get_service(self, obj):
        service = (
            obj.hire.service
        )

        return {
            "id": str(service.id),
            "service_name": (
                obj.service_name_snapshot
            ),
        }

    def get_service_summary(
        self,
        obj,
    ):
        service = (
            obj.hire.service
        )

        shift_hour = (
            service.shift_hour or 0
        )

        slot_shifts = (
            obj.slot_shifts
            .select_related(
                "booking_slot",
                "booking_slot__booking_item",
                (
                    "booking_slot__"
                    "booking_item__package"
                ),
            )
            .order_by(
                "booking_slot__starts_at"
            )
        )

        breakdown = []
        unit_prices = set()

        for slot_shift in slot_shifts:
            booking_slot = (
                slot_shift.booking_slot
            )

            unit_price = (
                get_booking_slot_unit_price(
                    hire=obj.hire,
                    booking_slot=booking_slot,
                )
            )

            unit_prices.add(
                unit_price
            )

            if booking_slot.starts_at:
                starts_at = (
                    timezone.localtime(
                        booking_slot.starts_at
                    )
                )

                date = starts_at.strftime(
                    "%d %B %Y"
                )

            else:
                date = "Not provided"

            slot_amount = (
                unit_price
                * slot_shift.shift_count
            )

            breakdown.append({
                "booking_slot_id": str(
                    slot_shift.booking_slot_id
                ),
                "booking_item_id": (
                    str(
                        booking_slot.booking_item_id
                    )
                    if booking_slot.booking_item_id
                    else None
                ),
                "booking_title": (
                    booking_slot
                    .booking_item
                    .booking_title
                    if booking_slot.booking_item_id
                    else obj.hire.booking_title
                ),
                "event_type": (
                    booking_slot.event_type
                ),
                "date": date,
                "shift_count": (
                    slot_shift.shift_count
                ),
                "shift_hours": (
                    shift_hour
                    * slot_shift.shift_count
                ),
                "unit_price": (
                    f"{unit_price:.2f}"
                ),
                "amount": (
                    f"{slot_amount:.2f}"
                ),
            })

        booked_slot_count = (
            obj.hire
            .booking_slots
            .filter(
                starts_at__isnull=False
            )
            .count()
        )

        single_unit_price = (
            next(iter(unit_prices))
            if len(unit_prices) == 1
            else None
        )

        return {
            "slot_count": (
                booked_slot_count
            ),
            "shift_count": (
                obj.shift_count
            ),
            "shift_hour_per_slot": (
                shift_hour
            ),
            "total_shift_hours": (
                shift_hour
                * obj.shift_count
            ),
            "shift_charge_per_slot": (
                f"{single_unit_price:.2f}"
                if single_unit_price
                is not None
                else None
            ),
            "total_amount": (
                f"{obj.service_price:.2f}"
            ),
            "breakdown": breakdown,
        }

    def get_can_edit(
        self,
        obj,
    ):
        request = (
            self.context.get("request")
        )

        if not request:
            return False

        user = request.user

        if not user.is_authenticated:
            return False

        if (
            getattr(
                user,
                "role",
                None,
            )
            != "seller"
        ):
            return False

        seller_id = (
            obj.hire
            .service
            .brand
            .seller_id
        )

        if seller_id != user.id:
            return False

        if obj.customer_agreed is not None:
            return False

        return (
            timezone.localdate()
            <= obj.due_payment_last_date
        )

    def get_can_customer_decide(
        self,
        obj,
    ):
        request = (
            self.context.get("request")
        )

        if not request:
            return False

        user = request.user

        if not user.is_authenticated:
            return False

        if (
            getattr(
                user,
                "role",
                None,
            )
            != "customer"
        ):
            return False

        if (
            obj.hire.customer_id
            != user.id
        ):
            return False

        return (
            obj.customer_agreed is None
        )


# =========================================================
# Seller invoice create serializer
# =========================================================


class InvoiceCreateSerializer(
    serializers.ModelSerializer
):
    hire = (
        serializers.PrimaryKeyRelatedField(
            queryset=Hire.objects.none(),
            error_messages={
                "required": (
                    "A hire request is required."
                ),
                "does_not_exist": (
                    "The selected hire request "
                    "does not exist or is not "
                    "available for invoice creation."
                ),
                "incorrect_type": (
                    "Invalid hire request ID."
                ),
            },
        )
    )

    service_price = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
            read_only=True,
        )
    )

    slot_shifts = (
        InvoiceSlotShiftInputSerializer(
            many=True,
            allow_empty=False,
            write_only=True,
            error_messages={
                "required": (
                    "A shift count is required "
                    "for every booking slot."
                ),
                "empty": (
                    "A shift count is required "
                    "for every booking slot."
                ),
            },
        )
    )

    discount_price = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
            min_value=ZERO_AMOUNT,
            default=ZERO_AMOUNT,
            error_messages={
                "invalid": (
                    "Discount price must be "
                    "a valid amount."
                ),
                "min_value": (
                    "Discount price cannot "
                    "be negative."
                ),
                "max_digits": (
                    "Discount price is too large."
                ),
                "max_decimal_places": (
                    "Discount price can have "
                    "a maximum of 2 decimal places."
                ),
            },
        )
    )

    advance_payment = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
            min_value=ZERO_AMOUNT,
            default=ZERO_AMOUNT,
            error_messages={
                "invalid": (
                    "Advance payment must be "
                    "a valid amount."
                ),
                "min_value": (
                    "Advance payment cannot "
                    "be negative."
                ),
                "max_digits": (
                    "Advance payment amount "
                    "is too large."
                ),
                "max_decimal_places": (
                    "Advance payment can have "
                    "a maximum of 2 decimal places."
                ),
            },
        )
    )

    terms_conditions = (
        serializers.ListField(
            child=serializers.CharField(
                max_length=MAX_TERM_LENGTH,
                allow_blank=False,
                trim_whitespace=True,
                error_messages={
                    "blank": (
                        "Terms and conditions cannot "
                        "contain an empty item."
                    ),
                    "max_length": (
                        "Each term can contain a "
                        f"maximum of "
                        f"{MAX_TERM_LENGTH} characters."
                    ),
                },
            ),
            required=False,
            allow_empty=True,
            max_length=MAX_TERMS_CONDITIONS,
            error_messages={
                "not_a_list": (
                    "Terms and conditions must "
                    "be provided as a list."
                ),
                "max_length": (
                    f"A maximum of "
                    f"{MAX_TERMS_CONDITIONS} "
                    "terms and conditions is allowed."
                ),
            },
        )
    )

    class Meta:
        model = Invoice

        fields = [
            "hire",
            "slot_shifts",
            "due_payment_last_date",
            "service_price",
            "additional_charge",
            "additional_charge_reason",
            "discount_price",
            "advance_payment",
            "seller_note",
            "terms_conditions",
        ]

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        request = (
            self.context.get("request")
        )

        if not request:
            return

        user = request.user

        if (
            user.is_authenticated
            and getattr(
                user,
                "role",
                None,
            )
            == "seller"
        ):
            self.fields[
                "hire"
            ].queryset = (
                Hire.objects
                .select_related(
                    "customer",
                    "service",
                    "service__brand",
                    "service__brand__seller",
                )
                .filter(
                    status=(
                        HireStatus.ACCEPTED
                    ),
                    service__brand__seller=(
                        user
                    ),
                    invoice__isnull=True,
                )
            )

    def validate_hire(
        self,
        hire,
    ):
        request = (
            self.context.get("request")
        )

        if not request:
            raise PermissionDenied(
                "Authentication is required."
            )

        user = request.user

        if not user.is_authenticated:
            raise PermissionDenied(
                "Authentication is required."
            )

        if (
            getattr(
                user,
                "role",
                None,
            )
            != "seller"
        ):
            raise PermissionDenied(
                "Only sellers can create invoices."
            )

        seller_id = (
            hire.service
            .brand
            .seller_id
        )

        if seller_id != user.id:
            raise PermissionDenied(
                "You cannot create an invoice "
                "for another seller's hire."
            )

        if (
            hire.status
            != HireStatus.ACCEPTED
        ):
            raise serializers.ValidationError(
                "An invoice can only be created "
                "for an accepted hire request."
            )

        if Invoice.objects.filter(
            hire=hire
        ).exists():
            raise serializers.ValidationError(
                "An invoice already exists "
                "for this hire request."
            )

        return hire

    def validate_due_payment_last_date(
        self,
        value,
    ):
        if value < timezone.localdate():
            raise serializers.ValidationError(
                "Due payment date cannot "
                "be in the past."
            )

        return value

    def validate(
        self,
        attrs,
    ):
        hire = attrs.get("hire")

        if hire is None:
            raise serializers.ValidationError({
                "hire": (
                    "A hire request is required."
                )
            })

        get_hire_slot_count(
            hire
        )

        slot_shifts = validate_slot_shifts(
            hire=hire,
            slot_shifts=attrs.get(
                "slot_shifts",
                [],
            ),
        )

        attrs["slot_shifts"] = (
            slot_shifts
        )

        attrs["service_price"] = (
            calculate_service_price_from_slot_shifts(
                hire=hire,
                slot_shifts=slot_shifts,
            )
        )

        return (
            validate_invoice_financial_data(
                attrs
            )
        )

    def create(
        self,
        validated_data,
    ):
        request = (
            self.context["request"]
        )

        seller = request.user

        submitted_hire = (
            validated_data.pop("hire")
        )

        slot_shifts_data = (
            validated_data.pop(
                "slot_shifts"
            )
        )

        try:
            with transaction.atomic():
                hire = (
                    Hire.objects
                    .select_for_update()
                    .select_related(
                        "customer",
                        "service",
                        "service__brand",
                        (
                            "service__brand__"
                            "seller"
                        ),
                    )
                    .get(
                        pk=submitted_hire.pk
                    )
                )

                if (
                    hire.status
                    != HireStatus.ACCEPTED
                ):
                    raise (
                        serializers.ValidationError({
                            "hire": (
                                "The hire request is "
                                "no longer accepted, "
                                "so an invoice cannot "
                                "be created."
                            )
                        })
                    )

                seller_id = (
                    hire.service
                    .brand
                    .seller_id
                )

                if seller_id != seller.id:
                    raise PermissionDenied(
                        "You cannot create an invoice "
                        "for this hire request."
                    )

                if Invoice.objects.filter(
                    hire=hire
                ).exists():
                    raise (
                        serializers.ValidationError({
                            "hire": (
                                "An invoice already "
                                "exists for this "
                                "hire request."
                            )
                        })
                    )

                get_hire_slot_count(
                    hire
                )

                slot_shifts_data = (
                    validate_slot_shifts(
                        hire=hire,
                        slot_shifts=(
                            slot_shifts_data
                        ),
                    )
                )

                validated_data[
                    "service_price"
                ] = (
                    calculate_service_price_from_slot_shifts(
                        hire=hire,
                        slot_shifts=(
                            slot_shifts_data
                        ),
                    )
                )

                validate_invoice_financial_data(
                    validated_data
                )

                invoice = (
                    Invoice.objects.create(
                        hire=hire,
                        **validated_data,
                    )
                )

                apply_slot_shifts(
                    invoice,
                    slot_shifts_data,
                )

                create_invoice_created_notification(
                    invoice
                )

                transaction.on_commit(
                    lambda invoice_pk=invoice.pk: (
                        send_invoice_created_email(
                            invoice_pk
                        )
                    ),
                    robust=True,
                )

                return invoice

        except Hire.DoesNotExist as error:
            raise serializers.ValidationError({
                "hire": (
                    "The selected hire request "
                    "does not exist."
                )
            }) from error

        except IntegrityError as error:
            raise serializers.ValidationError({
                "hire": (
                    "An invoice already exists for "
                    "this hire request, or the invoice "
                    "could not be created because of "
                    "a database conflict."
                )
            }) from error

        except DjangoValidationError as error:
            raise (
                convert_model_validation_error(
                    error
                )
            ) from error

    def to_representation(
        self,
        instance,
    ):
        return InvoiceDetailSerializer(
            instance,
            context=self.context,
        ).data


# =========================================================
# Customer invoice decision serializer
# =========================================================


class InvoiceCustomerDecisionSerializer(
    serializers.ModelSerializer
):
    customer_agreed = (
        serializers.BooleanField(
            required=True,
            allow_null=False,
        )
    )

    class Meta:
        model = Invoice

        fields = [
            "customer_agreed",
        ]

    def validate(
        self,
        attrs,
    ):
        request = (
            self.context.get("request")
        )

        invoice = self.instance

        if not request:
            raise PermissionDenied(
                "Authentication is required."
            )

        user = request.user

        if not user.is_authenticated:
            raise PermissionDenied(
                "Authentication is required."
            )

        if (
            getattr(
                user,
                "role",
                None,
            )
            != "customer"
        ):
            raise PermissionDenied(
                "Only customers can submit "
                "an invoice decision."
            )

        if invoice is None:
            raise serializers.ValidationError({
                "detail": (
                    "Invoice instance is required."
                )
            })

        if (
            invoice.hire.customer_id
            != user.id
        ):
            raise PermissionDenied(
                "You cannot submit a decision "
                "for another customer's invoice."
            )

        if (
            invoice.customer_agreed
            is not None
        ):
            decision = (
                "agreed"
                if invoice.customer_agreed
                else "disagreed"
            )

            raise serializers.ValidationError({
                "customer_agreed": (
                    f"You have already {decision} "
                    "with this invoice."
                )
            })

        return attrs

    def update(
        self,
        instance,
        validated_data,
    ):
        request = (
            self.context["request"]
        )

        customer = request.user

        try:
            with transaction.atomic():
                locked_hire = (
                    Hire.objects
                    .select_for_update()
                    .get(
                        pk=instance.hire_id
                    )
                )

                locked_invoice = (
                    Invoice.objects
                    .select_for_update()
                    .select_related(
                        "hire",
                        "hire__customer",
                        "hire__service",
                        (
                            "hire__service__"
                            "brand"
                        ),
                        (
                            "hire__service__brand__"
                            "seller"
                        ),
                    )
                    .get(
                        pk=instance.pk
                    )
                )

                if (
                    locked_hire.customer_id
                    != customer.id
                ):
                    raise PermissionDenied(
                        "You cannot submit a "
                        "decision for this invoice."
                    )

                if (
                    locked_invoice
                    .customer_agreed
                    is not None
                ):
                    decision = (
                        "agreed"
                        if (
                            locked_invoice
                            .customer_agreed
                        )
                        else "disagreed"
                    )

                    raise (
                        serializers.ValidationError({
                            "customer_agreed": (
                                f"You have already "
                                f"{decision} with "
                                "this invoice."
                            )
                        })
                    )

                customer_agreed = (
                    validated_data[
                        "customer_agreed"
                    ]
                )

                if (
                    customer_agreed
                    and locked_hire.status
                    != HireStatus.ACCEPTED
                ):
                    raise (
                        serializers.ValidationError({
                            "customer_agreed": (
                                "Only an accepted hire "
                                "can be completed."
                            )
                        })
                    )

                locked_invoice.customer_agreed = (
                    customer_agreed
                )

                locked_invoice.save()

                if customer_agreed:
                    locked_hire.status = (
                        HireStatus.COMPLETED
                    )

                    locked_hire.completed_at = (
                        timezone.now()
                    )

                    locked_hire.save()

        except Invoice.DoesNotExist as error:
            raise serializers.ValidationError({
                "detail": (
                    "The invoice could not be found."
                )
            }) from error

        except Hire.DoesNotExist as error:
            raise serializers.ValidationError({
                "detail": (
                    "The hire request could "
                    "not be found."
                )
            }) from error

        except DjangoValidationError as error:
            raise (
                convert_model_validation_error(
                    error
                )
            ) from error

        return locked_invoice


# =========================================================
# Seller invoice update serializer
# =========================================================


class InvoiceUpdateSerializer(
    serializers.ModelSerializer
):
    service_price = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
            read_only=True,
        )
    )

    slot_shifts = (
        InvoiceSlotShiftInputSerializer(
            many=True,
            required=False,
            allow_empty=False,
            write_only=True,
            error_messages={
                "empty": (
                    "A shift count is required "
                    "for every booking slot."
                ),
            },
        )
    )

    discount_price = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
            min_value=ZERO_AMOUNT,
            required=False,
            error_messages={
                "invalid": (
                    "Discount price must be "
                    "a valid amount."
                ),
                "min_value": (
                    "Discount price cannot "
                    "be negative."
                ),
                "max_digits": (
                    "Discount price is too large."
                ),
                "max_decimal_places": (
                    "Discount price can have "
                    "a maximum of 2 decimal places."
                ),
            },
        )
    )

    advance_payment = (
        serializers.DecimalField(
            max_digits=12,
            decimal_places=2,
            min_value=ZERO_AMOUNT,
            required=False,
            error_messages={
                "invalid": (
                    "Advance payment must be "
                    "a valid amount."
                ),
                "min_value": (
                    "Advance payment cannot "
                    "be negative."
                ),
                "max_digits": (
                    "Advance payment amount "
                    "is too large."
                ),
                "max_decimal_places": (
                    "Advance payment can have "
                    "a maximum of 2 decimal places."
                ),
            },
        )
    )

    due_payment_last_date = (
        serializers.DateField(
            required=False,
            error_messages={
                "invalid": (
                    "Enter a valid due "
                    "payment date."
                ),
            },
        )
    )

    seller_note = (
        serializers.CharField(
            required=False,
            allow_blank=True,
            allow_null=True,
        )
    )

    terms_conditions = (
        serializers.ListField(
            child=serializers.CharField(
                max_length=MAX_TERM_LENGTH,
                allow_blank=False,
                trim_whitespace=True,
                error_messages={
                    "blank": (
                        "Terms and conditions cannot "
                        "contain an empty item."
                    ),
                    "max_length": (
                        "Each term can contain a "
                        f"maximum of "
                        f"{MAX_TERM_LENGTH} characters."
                    ),
                },
            ),
            required=False,
            allow_empty=True,
            max_length=MAX_TERMS_CONDITIONS,
            error_messages={
                "not_a_list": (
                    "Terms and conditions must "
                    "be provided as a list."
                ),
                "max_length": (
                    f"A maximum of "
                    f"{MAX_TERMS_CONDITIONS} "
                    "terms and conditions is allowed."
                ),
            },
        )
    )

    class Meta:
        model = Invoice

        fields = [
            "due_payment_last_date",
            "slot_shifts",
            "service_price",
            "discount_price",
            "additional_charge",
            "additional_charge_reason",
            "advance_payment",
            "seller_note",
            "terms_conditions",
        ]

    def validate_due_payment_last_date(
        self,
        value,
    ):
        if value < timezone.localdate():
            raise serializers.ValidationError(
                "Due payment date cannot be "
                "changed to a past date."
            )

        return value

    def validate(
        self,
        attrs,
    ):
        request = (
            self.context.get("request")
        )

        invoice = self.instance

        if not request:
            raise PermissionDenied(
                "Authentication is required."
            )

        user = request.user

        if not user.is_authenticated:
            raise PermissionDenied(
                "Authentication is required."
            )

        if (
            getattr(
                user,
                "role",
                None,
            )
            != "seller"
        ):
            raise PermissionDenied(
                "Only sellers can edit invoices."
            )

        if invoice is None:
            raise serializers.ValidationError({
                "detail": (
                    "Invoice instance is required."
                )
            })

        seller_id = (
            invoice.hire
            .service
            .brand
            .seller_id
        )

        if seller_id != user.id:
            raise PermissionDenied(
                "You cannot edit another "
                "seller's invoice."
            )

        if (
            invoice.customer_agreed
            is not None
        ):
            decision = (
                "agreed"
                if invoice.customer_agreed
                else "disagreed"
            )

            raise serializers.ValidationError({
                "detail": (
                    "This invoice can no longer "
                    "be edited because the customer "
                    f"has already {decision}."
                )
            })

        if (
            timezone.localdate()
            > invoice.due_payment_last_date
        ):
            raise serializers.ValidationError({
                "detail": (
                    "This invoice can no longer "
                    "be edited because the due "
                    "payment date has passed."
                )
            })

        if "slot_shifts" in attrs:
            slot_shifts = (
                validate_slot_shifts(
                    hire=invoice.hire,
                    slot_shifts=(
                        attrs["slot_shifts"]
                    ),
                )
            )

            attrs["slot_shifts"] = (
                slot_shifts
            )

            attrs["service_price"] = (
                calculate_service_price_from_slot_shifts(
                    hire=invoice.hire,
                    slot_shifts=slot_shifts,
                )
            )

        return (
            validate_invoice_financial_data(
                attrs,
                instance=invoice,
            )
        )

    def update(
        self,
        instance,
        validated_data,
    ):
        request = (
            self.context["request"]
        )

        seller = request.user

        slot_shifts_data = (
            validated_data.pop(
                "slot_shifts",
                None,
            )
        )

        try:
            with transaction.atomic():
                locked_invoice = (
                    Invoice.objects
                    .select_for_update()
                    .select_related(
                        "hire",
                        "hire__customer",
                        "hire__service",
                        (
                            "hire__service__"
                            "brand"
                        ),
                        (
                            "hire__service__brand__"
                            "seller"
                        ),
                    )
                    .get(
                        pk=instance.pk
                    )
                )

                seller_id = (
                    locked_invoice
                    .hire
                    .service
                    .brand
                    .seller_id
                )

                if seller_id != seller.id:
                    raise PermissionDenied(
                        "You cannot edit "
                        "this invoice."
                    )

                if (
                    locked_invoice
                    .customer_agreed
                    is not None
                ):
                    decision = (
                        "agreed"
                        if (
                            locked_invoice
                            .customer_agreed
                        )
                        else "disagreed"
                    )

                    raise (
                        serializers.ValidationError({
                            "detail": (
                                "This invoice can no "
                                "longer be edited because "
                                "the customer has already "
                                f"{decision}."
                            )
                        })
                    )

                if (
                    timezone.localdate()
                    > locked_invoice
                    .due_payment_last_date
                ):
                    raise (
                        serializers.ValidationError({
                            "detail": (
                                "This invoice can no "
                                "longer be edited because "
                                "the due payment date "
                                "has passed."
                            )
                        })
                    )

                if (
                    slot_shifts_data
                    is not None
                ):
                    slot_shifts_data = (
                        validate_slot_shifts(
                            hire=(
                                locked_invoice.hire
                            ),
                            slot_shifts=(
                                slot_shifts_data
                            ),
                        )
                    )

                    validated_data[
                        "service_price"
                    ] = (
                        calculate_service_price_from_slot_shifts(
                            hire=(
                                locked_invoice.hire
                            ),
                            slot_shifts=(
                                slot_shifts_data
                            ),
                        )
                    )

                validate_invoice_financial_data(
                    validated_data,
                    instance=locked_invoice,
                )

                changed_fields = []

                for (
                    field_name,
                    new_value,
                ) in validated_data.items():
                    old_value = getattr(
                        locked_invoice,
                        field_name,
                    )

                    if old_value == new_value:
                        continue

                    setattr(
                        locked_invoice,
                        field_name,
                        new_value,
                    )

                    changed_fields.append(
                        field_name
                    )

                if (
                    slot_shifts_data
                    is not None
                ):
                    changed_fields.append(
                        "slot_shifts"
                    )

                if not changed_fields:
                    return locked_invoice

                locked_invoice.save()

                if (
                    slot_shifts_data
                    is not None
                ):
                    apply_slot_shifts(
                        locked_invoice,
                        slot_shifts_data,
                    )

                create_invoice_updated_notification(
                    invoice=locked_invoice,
                    changed_fields=changed_fields,
                )

                return locked_invoice

        except Invoice.DoesNotExist as error:
            raise serializers.ValidationError({
                "detail": (
                    "The invoice could not be found. "
                    "It may have been deleted."
                )
            }) from error

        except DjangoValidationError as error:
            raise (
                convert_model_validation_error(
                    error
                )
            ) from error

    def to_representation(
        self,
        instance,
    ):
        return InvoiceDetailSerializer(
            instance,
            context=self.context,
        ).data