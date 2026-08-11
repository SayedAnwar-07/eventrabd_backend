from decimal import Decimal

from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from .emails import send_invoice_created_email

from apps.hires.models import Hire, HireStatus, HireBookingSlot
from apps.notifications.services import (
    create_invoice_created_notification,
    create_invoice_updated_notification,
)

from .models import Invoice, InvoiceSlotShift, MAX_TERM_LENGTH, MAX_TERMS_CONDITIONS, ZERO_AMOUNT


MINIMUM_SERVICE_PRICE = Decimal("0.01")


# =========================================================
# Helper functions
# =========================================================

def convert_model_validation_error(error):
    """
    Convert Django model ValidationError into DRF ValidationError.
    """

    if hasattr(error, "message_dict"):
        return serializers.ValidationError(
            error.message_dict
        )

    if hasattr(error, "messages"):
        return serializers.ValidationError(
            {
                "detail": error.messages,
            }
        )

    return serializers.ValidationError(
        {
            "detail": str(error),
        }
    )


def get_hire_slot_count(hire):
    """
    Ensure the hire has at least one booking slot and return the count.
    """

    slot_count = hire.booking_slots.count()

    if slot_count < 1:
        raise serializers.ValidationError({
            "hire": (
                "This hire has no booking slots. "
                "At least one booking slot is required "
                "before creating an invoice."
            )
        })

    return slot_count


def validate_slot_shifts(hire, slot_shifts):
    """
    Validate a list of {"booking_slot": <HireBookingSlot>, "shift_count": int}
    submitted for one hire.

    Rules:
        - Every booking_slot must belong to this hire.
        - A booking slot cannot appear more than once.
        - Every booked date (slot) on the hire must be assigned
          a shift count — nothing can be left out.
    """

    hire_slot_ids = set(
        hire.booking_slots.values_list("id", flat=True)
    )

    seen_slot_ids = set()

    for item in slot_shifts:
        booking_slot = item["booking_slot"]

        if booking_slot.hire_id != hire.id:
            raise serializers.ValidationError({
                "slot_shifts": (
                    "One of the booking slots does not belong "
                    "to this hire request."
                )
            })

        if booking_slot.id in seen_slot_ids:
            raise serializers.ValidationError({
                "slot_shifts": (
                    "Each booking slot (date) can only be "
                    "assigned a shift count once."
                )
            })

        seen_slot_ids.add(booking_slot.id)

    missing_slot_ids = hire_slot_ids - seen_slot_ids

    if missing_slot_ids:
        raise serializers.ValidationError({
            "slot_shifts": (
                "A shift count must be provided for every "
                f"booked date. Missing shift count for "
                f"{len(missing_slot_ids)} booking slot(s)."
            )
        })

    return slot_shifts


def calculate_service_price_from_slot_shifts(hire, slot_shifts):
    """
    total service_price = shift_charge × (sum of shift_count
    across every booking slot).
    """

    shift_charge = hire.service.shift_charge or ZERO_AMOUNT

    if shift_charge <= ZERO_AMOUNT:
        raise serializers.ValidationError({
            "service_price": (
                "Service price cannot be calculated "
                "because the service shift charge is "
                "not configured correctly."
            )
        })

    total_shift_count = sum(
        item["shift_count"] for item in slot_shifts
    )

    return shift_charge * total_shift_count


def apply_slot_shifts(invoice, slot_shifts):
    """
    Replace an invoice's InvoiceSlotShift rows with the given list.

    Existing rows not present anymore are removed; rows are otherwise
    (re)created so each one goes through its own full_clean().
    """

    invoice.slot_shifts.all().delete()

    for item in slot_shifts:
        InvoiceSlotShift.objects.create(
            invoice=invoice,
            booking_slot=item["booking_slot"],
            shift_count=item["shift_count"],
        )


def validate_invoice_financial_data(
    attrs,
    instance=None,
):
    """
    Validate invoice financial values during create and update.
    """

    if instance is not None:
        service_price = attrs.get(
            "service_price",
            instance.service_price,
        )

        discount_price = attrs.get(
            "discount_price",
            instance.discount_price,
        )

        advance_payment = attrs.get(
            "advance_payment",
            instance.advance_payment,
        )

        issue_date = instance.issue_date

        due_payment_last_date = attrs.get(
            "due_payment_last_date",
            instance.due_payment_last_date,
        )

    else:
        service_price = attrs.get(
            "service_price",
            ZERO_AMOUNT,
        )

        discount_price = attrs.get(
            "discount_price",
            ZERO_AMOUNT,
        )

        advance_payment = attrs.get(
            "advance_payment",
            ZERO_AMOUNT,
        )

        issue_date = timezone.localdate()

        due_payment_last_date = attrs.get(
            "due_payment_last_date"
        )

    errors = {}

    if service_price <= ZERO_AMOUNT:
        errors["service_price"] = (
            "Service price must be greater than zero."
        )

    if discount_price < ZERO_AMOUNT:
        errors["discount_price"] = (
            "Discount price cannot be negative."
        )

    if discount_price > service_price:
        errors["discount_price"] = (
            "Discount cannot be greater than "
            "the service price."
        )

    calculated_total = (
        service_price - discount_price
    )

    if advance_payment < ZERO_AMOUNT:
        errors["advance_payment"] = (
            "Advance payment cannot be negative."
        )

    if advance_payment > calculated_total:
        errors["advance_payment"] = (
            "Advance payment cannot be greater than "
            "the total amount."
        )

    if (
        issue_date
        and due_payment_last_date
        and due_payment_last_date < issue_date
    ):
        errors["due_payment_last_date"] = (
            "Due payment date cannot be earlier "
            "than the invoice date."
        )

    if errors:
        raise serializers.ValidationError(errors)

    return attrs


# =========================================================
# Per-slot shift input
# =========================================================

class InvoiceSlotShiftInputSerializer(serializers.Serializer):
    """
    One entry of: "this booked date gets this many shifts".

    Example:
        {"booking_slot": "<slot-uid-for-10-aug>", "shift_count": 3}
        {"booking_slot": "<slot-uid-for-16-aug>", "shift_count": 2}
    """

    booking_slot = serializers.PrimaryKeyRelatedField(
        queryset=HireBookingSlot.objects.all(),
        error_messages={
            "does_not_exist": (
                "The selected booking slot does not exist."
            ),
        },
    )

    shift_count = serializers.IntegerField(
        min_value=1,
        error_messages={
            "invalid": "Shift count must be a valid whole number.",
            "min_value": "Shift count must be at least 1.",
        },
    )


# =========================================================
# Invoice detail serializer
# =========================================================

class InvoiceDetailSerializer(
    serializers.ModelSerializer
):
    hire = serializers.SerializerMethodField()

    customer = serializers.SerializerMethodField()
    seller = serializers.SerializerMethodField()
    brand = serializers.SerializerMethodField()
    service = serializers.SerializerMethodField()
    service_summary = serializers.SerializerMethodField()

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

    is_partially_paid = serializers.BooleanField(
        read_only=True,
    )

    is_overdue = serializers.BooleanField(
        read_only=True,
    )

    payment_status = serializers.CharField(
        read_only=True,
    )

    customer_agreed = serializers.BooleanField(
        read_only=True,
        allow_null=True,
    )

    can_edit = serializers.SerializerMethodField()

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
            "id": str(obj.hire.customer_id),
            "full_name": obj.customer_name_snapshot,
            "email": obj.customer_email_snapshot,
            "whatsapp_number": obj.customer_whatsapp_snapshot,
        }

    def get_seller(self, obj):
        seller = (
            obj.hire.service.brand.seller
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
        brand = obj.hire.service.brand

        return {
            "id": str(brand.id),
            "brand_name": (
                obj.brand_name_snapshot
            ),
            "display_name": obj.display_name_snapshot,
        }

    def get_service_summary(self, obj):
        """
        Now returns a per-date breakdown, since each booking slot
        (event date) can carry its own seller-chosen shift count.

        Example:
            10 Aug 2026 -> 3 shifts -> ৳X
            16 Aug 2026 -> 2 shifts -> ৳Y
        """

        service = obj.hire.service

        shift_hour = service.shift_hour or 0
        shift_charge = service.shift_charge or ZERO_AMOUNT

        slot_shifts = (
            obj.slot_shifts
            .select_related("booking_slot")
            .order_by("booking_slot__starts_at")
        )

        breakdown = []

        for slot_shift in slot_shifts:
            starts_at = timezone.localtime(
                slot_shift.booking_slot.starts_at
            )
            slot_amount = shift_charge * slot_shift.shift_count

            breakdown.append({
                "booking_slot_id": str(slot_shift.booking_slot_id),
                "date": starts_at.strftime("%d %B %Y"),
                "shift_count": slot_shift.shift_count,
                "shift_hours": shift_hour * slot_shift.shift_count,
                "amount": f"{slot_amount:.2f}",
            })

        return {
            "slot_count": obj.hire.booking_slots.count(),
            "shift_count": obj.shift_count,
            "shift_hour_per_slot": shift_hour,
            "total_shift_hours": shift_hour * obj.shift_count,
            "shift_charge_per_slot": f"{shift_charge:.2f}",
            "total_amount": f"{obj.service_price:.2f}",
            "breakdown": breakdown,
        }

    def get_service(self, obj):
        service = obj.hire.service

        return {
            "id": str(service.id),
            "service_name": (
                obj.service_name_snapshot
            ),
        }

    def get_can_edit(self, obj):
        request = self.context.get("request")

        if not request:
            return False

        user = request.user

        if not user.is_authenticated:
            return False

        if getattr(user, "role", None) != "seller":
            return False

        seller_id = (
            obj.hire.service.brand.seller_id
        )

        if seller_id != user.id:
            return False

        if obj.customer_agreed is not None:
            return False

        return (
            timezone.localdate()
            <= obj.due_payment_last_date
        )

    def get_can_customer_decide(self, obj):
        request = self.context.get("request")

        if not request:
            return False

        user = request.user

        if not user.is_authenticated:
            return False

        if getattr(user, "role", None) != "customer":
            return False

        if obj.hire.customer_id != user.id:
            return False

        return obj.customer_agreed is None


# =========================================================
# Seller invoice create serializer
# =========================================================

class InvoiceCreateSerializer(
    serializers.ModelSerializer
):
    hire = serializers.PrimaryKeyRelatedField(
        queryset=Hire.objects.none(),
        error_messages={
            "required": "A hire request is required.",
            "does_not_exist": (
                "The selected hire request does not exist "
                "or is not available for invoice creation."
            ),
            "incorrect_type": (
                "Invalid hire request ID."
            ),
        },
    )

    service_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    slot_shifts = InvoiceSlotShiftInputSerializer(
        many=True,
        allow_empty=False,
        write_only=True,
        error_messages={
            "required": (
                "A shift count is required for every booked date."
            ),
            "empty": (
                "A shift count is required for every booked date."
            ),
        },
    )

    discount_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO_AMOUNT,
        default=ZERO_AMOUNT,
        error_messages={
            "invalid": (
                "Discount price must be a valid amount."
            ),
            "min_value": (
                "Discount price cannot be negative."
            ),
            "max_digits": (
                "Discount price is too large."
            ),
            "max_decimal_places": (
                "Discount price can have a maximum "
                "of 2 decimal places."
            ),
        },
    )

    advance_payment = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO_AMOUNT,
        default=ZERO_AMOUNT,
        error_messages={
            "invalid": (
                "Advance payment must be a valid amount."
            ),
            "min_value": (
                "Advance payment cannot be negative."
            ),
            "max_digits": (
                "Advance payment amount is too large."
            ),
            "max_decimal_places": (
                "Advance payment can have a maximum "
                "of 2 decimal places."
            ),
        },
    )

    terms_conditions = serializers.ListField(
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
                    f"Each term can contain a maximum "
                    f"of {MAX_TERM_LENGTH} characters."
                ),
            },
        ),
        required=False,
        allow_empty=True,
        max_length=MAX_TERMS_CONDITIONS,
        error_messages={
            "not_a_list": (
                "Terms and conditions must be "
                "provided as a list."
            ),
            "max_length": (
                f"A maximum of "
                f"{MAX_TERMS_CONDITIONS} terms "
                f"and conditions is allowed."
            ),
        },
    )

    class Meta:
        model = Invoice

        fields = [
            "hire",
            "slot_shifts",
            "due_payment_last_date",
            "service_price",
            "discount_price",
            "advance_payment",
            "seller_note",
            "terms_conditions",
        ]

    # Initialization

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")

        if not request:
            return

        user = request.user

        if (
            user.is_authenticated
            and getattr(user, "role", None) == "seller"
        ):
            self.fields["hire"].queryset = (
                Hire.objects
                .select_related(
                    "customer",
                    "service",
                    "service__brand",
                    "service__brand__seller",
                )
                .filter(
                    status=HireStatus.ACCEPTED,
                    service__brand__seller=user,
                    invoice__isnull=True,
                )
            )

    # Hire validation

    def validate_hire(
        self,
        hire,
    ):
        request = self.context.get("request")

        if not request:
            raise PermissionDenied(
                "Authentication is required."
            )

        user = request.user

        if not user.is_authenticated:
            raise PermissionDenied(
                "Authentication is required."
            )

        if getattr(user, "role", None) != "seller":
            raise PermissionDenied(
                "Only sellers can create invoices."
            )

        seller_id = (
            hire.service.brand.seller_id
        )

        if seller_id != user.id:
            raise PermissionDenied(
                "You cannot create an invoice "
                "for another seller's hire."
            )

        if hire.status != HireStatus.ACCEPTED:
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

    # Due date validation

    def validate_due_payment_last_date(
        self,
        value,
    ):
        today = timezone.localdate()

        if value < today:
            raise serializers.ValidationError(
                "Due payment date cannot be "
                "in the past."
            )

        return value

    # Object validation

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

        get_hire_slot_count(hire)

        slot_shifts = validate_slot_shifts(
            hire=hire,
            slot_shifts=attrs.get("slot_shifts", []),
        )

        attrs["slot_shifts"] = slot_shifts

        attrs["service_price"] = (
            calculate_service_price_from_slot_shifts(
                hire=hire,
                slot_shifts=slot_shifts,
            )
        )

        return validate_invoice_financial_data(
            attrs
        )

    # Create

    def create(
        self,
        validated_data,
    ):
        request = self.context["request"]
        seller = request.user

        submitted_hire = (
            validated_data.pop("hire")
        )

        slot_shifts_data = (
            validated_data.pop("slot_shifts")
        )

        try:
            with transaction.atomic():
                # Lock hire to protect invoice creation
                # against concurrent requests.
                hire = (
                    Hire.objects
                    .select_for_update()
                    .select_related(
                        "customer",
                        "service",
                        "service__brand",
                        "service__brand__seller",
                    )
                    .get(
                        pk=submitted_hire.pk
                    )
                )

                # Re-check hire status after database lock
                if hire.status != HireStatus.ACCEPTED:
                    raise serializers.ValidationError({
                        "hire": (
                            "The hire request is no longer "
                            "accepted, so an invoice cannot "
                            "be created."
                        )
                    })

                # Re-check seller ownership
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

                # Re-check duplicate invoice
                if Invoice.objects.filter(
                    hire=hire
                ).exists():
                    raise serializers.ValidationError({
                        "hire": (
                            "An invoice already exists "
                            "for this hire request."
                        )
                    })

                # Re-validate booking slots / shift counts
                get_hire_slot_count(hire)

                slot_shifts_data = validate_slot_shifts(
                    hire=hire,
                    slot_shifts=slot_shifts_data,
                )

                # Recalculate service price
                validated_data["service_price"] = (
                    calculate_service_price_from_slot_shifts(
                        hire=hire,
                        slot_shifts=slot_shifts_data,
                    )
                )

                # Final financial validation
                validate_invoice_financial_data(
                    validated_data
                )

                # Create invoice
                invoice = (
                    Invoice.objects.create(
                        hire=hire,
                        **validated_data,
                    )
                )

                # Create one InvoiceSlotShift row per booked date
                apply_slot_shifts(invoice, slot_shifts_data)

                # Notification
                create_invoice_created_notification(
                    invoice
                )

                # Email after transaction commits
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
            raise convert_model_validation_error(
                error
            ) from error

    # Response
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
    customer_agreed = serializers.BooleanField(
        required=True,
        allow_null=False,
    )

    class Meta:
        model = Invoice

        fields = [
            "customer_agreed",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
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

        if getattr(user, "role", None) != "customer":
            raise PermissionDenied(
                "Only customers can submit an "
                "invoice decision."
            )

        if invoice is None:
            raise serializers.ValidationError(
                {
                    "detail": (
                        "Invoice instance is required."
                    )
                }
            )

        if invoice.hire.customer_id != user.id:
            raise PermissionDenied(
                "You cannot submit a decision for "
                "another customer's invoice."
            )

        if invoice.customer_agreed is not None:
            decision = (
                "agreed"
                if invoice.customer_agreed
                else "disagreed"
            )

            raise serializers.ValidationError(
                {
                    "customer_agreed": (
                        f"You have already {decision} "
                        "with this invoice."
                    )
                }
            )

        return attrs

    def update(
        self,
        instance,
        validated_data,
    ):
        request = self.context["request"]
        customer = request.user

        try:
            with transaction.atomic():
                locked_invoice = (
                    Invoice.objects
                    .select_for_update()
                    .select_related(
                        "hire",
                        "hire__customer",
                        "hire__service",
                        "hire__service__brand",
                        "hire__service__brand__seller",
                    )
                    .get(pk=instance.pk)
                )

                if (
                    locked_invoice.hire.customer_id
                    != customer.id
                ):
                    raise PermissionDenied(
                        "You cannot submit a decision "
                        "for this invoice."
                    )

                if (
                    locked_invoice.customer_agreed
                    is not None
                ):
                    decision = (
                        "agreed"
                        if locked_invoice.customer_agreed
                        else "disagreed"
                    )

                    raise serializers.ValidationError(
                        {
                            "customer_agreed": (
                                f"You have already "
                                f"{decision} with this "
                                "invoice."
                            )
                        }
                    )

                locked_invoice.customer_agreed = (
                    validated_data[
                        "customer_agreed"
                    ]
                )

                locked_invoice.save()

        except Invoice.DoesNotExist as error:
            raise serializers.ValidationError({
                "hire":
                "An invoice can only be created for an accepted hire request."
            }) from error

        except DjangoValidationError as error:
            raise convert_model_validation_error(
                error
            ) from error

        return locked_invoice

    def to_representation(self, instance):
        return InvoiceDetailSerializer(
            instance,
            context=self.context,
        ).data


# =========================================================
# Seller invoice update serializer
# =========================================================

class InvoiceUpdateSerializer(
    serializers.ModelSerializer
):
    service_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    slot_shifts = InvoiceSlotShiftInputSerializer(
        many=True,
        required=False,
        allow_empty=False,
        write_only=True,
        error_messages={
            "empty": (
                "A shift count is required for every booked date."
            ),
        },
    )

    discount_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO_AMOUNT,
        required=False,
        error_messages={
            "invalid": "Discount price must be a valid amount.",
            "min_value": "Discount price cannot be negative.",
            "max_digits": "Discount price is too large.",
            "max_decimal_places": (
                "Discount price can have a maximum "
                "of 2 decimal places."
            ),
        },
    )

    advance_payment = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO_AMOUNT,
        required=False,
        error_messages={
            "invalid": "Advance payment must be a valid amount.",
            "min_value": "Advance payment cannot be negative.",
            "max_digits": "Advance payment amount is too large.",
            "max_decimal_places": (
                "Advance payment can have a maximum "
                "of 2 decimal places."
            ),
        },
    )

    due_payment_last_date = serializers.DateField(
        required=False,
        error_messages={
            "invalid": "Enter a valid due payment date.",
        },
    )

    seller_note = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    terms_conditions = serializers.ListField(
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
                    f"Each term can contain a maximum "
                    f"of {MAX_TERM_LENGTH} characters."
                ),
            },
        ),
        required=False,
        allow_empty=True,
        max_length=MAX_TERMS_CONDITIONS,
        error_messages={
            "not_a_list": (
                "Terms and conditions must be provided "
                "as a list."
            ),
            "max_length": (
                f"A maximum of {MAX_TERMS_CONDITIONS} "
                "terms and conditions is allowed."
            ),
        },
    )

    class Meta:
        model = Invoice

        fields = [
            "due_payment_last_date",
            "slot_shifts",
            "service_price",
            "discount_price",
            "advance_payment",
            "seller_note",
            "terms_conditions",
        ]

    # Field validation
    def validate_due_payment_last_date(
        self,
        value,
    ):
        today = timezone.localdate()

        if value < today:
            raise serializers.ValidationError(
                "Due payment date cannot be changed "
                "to a past date."
            )

        return value

    # Object validation
    def validate(self, attrs):
        request = self.context.get("request")
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

        if getattr(user, "role", None) != "seller":
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
                "You cannot edit another seller's invoice."
            )

        if invoice.customer_agreed is not None:
            decision = (
                "agreed"
                if invoice.customer_agreed
                else "disagreed"
            )

            raise serializers.ValidationError({
                "detail": (
                    f"This invoice can no longer be edited "
                    f"because the customer has already "
                    f"{decision}."
                )
            })

        if (
            timezone.localdate()
            > invoice.due_payment_last_date
        ):
            raise serializers.ValidationError({
                "detail": (
                    "This invoice can no longer be edited "
                    "because the due payment date has passed."
                )
            })

        # Only recalculate service price when
        # slot_shifts is actually being changed.
        if "slot_shifts" in attrs:
            slot_shifts = validate_slot_shifts(
                hire=invoice.hire,
                slot_shifts=attrs["slot_shifts"],
            )

            attrs["slot_shifts"] = slot_shifts

            attrs["service_price"] = (
                calculate_service_price_from_slot_shifts(
                    hire=invoice.hire,
                    slot_shifts=slot_shifts,
                )
            )

        return validate_invoice_financial_data(
            attrs,
            instance=invoice,
        )

    # Update
    def update(
        self,
        instance,
        validated_data,
    ):
        request = self.context["request"]
        seller = request.user

        slot_shifts_data = validated_data.pop(
            "slot_shifts", None
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
                        "hire__service__brand",
                        "hire__service__brand__seller",
                    )
                    .get(
                        pk=instance.pk
                    )
                )

                # Re-check seller ownership after database lock
                seller_id = (
                    locked_invoice
                    .hire
                    .service
                    .brand
                    .seller_id
                )

                if seller_id != seller.id:
                    raise PermissionDenied(
                        "You cannot edit this invoice."
                    )

                # Re-check customer decision after database lock
                if (
                    locked_invoice.customer_agreed
                    is not None
                ):
                    decision = (
                        "agreed"
                        if locked_invoice.customer_agreed
                        else "disagreed"
                    )

                    raise serializers.ValidationError({
                        "detail": (
                            f"This invoice can no longer "
                            f"be edited because the customer "
                            f"has already {decision}."
                        )
                    })

                # Re-check due date after database lock
                if (
                    timezone.localdate()
                    > locked_invoice.due_payment_last_date
                ):
                    raise serializers.ValidationError({
                        "detail": (
                            "This invoice can no longer "
                            "be edited because the due "
                            "payment date has passed."
                        )
                    })

                # Slot shifts + service price
                if slot_shifts_data is not None:
                    slot_shifts_data = validate_slot_shifts(
                        hire=locked_invoice.hire,
                        slot_shifts=slot_shifts_data,
                    )

                    validated_data["service_price"] = (
                        calculate_service_price_from_slot_shifts(
                            hire=locked_invoice.hire,
                            slot_shifts=slot_shifts_data,
                        )
                    )

                # Financial validation
                validate_invoice_financial_data(
                    validated_data,
                    instance=locked_invoice,
                )

                # Apply only changed fields
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

                if slot_shifts_data is not None:
                    changed_fields.append("slot_shifts")

                # Nothing changed
                if not changed_fields:
                    return locked_invoice

                # Model full_clean() will also run
                # from your Invoice.save().
                locked_invoice.save()

                if slot_shifts_data is not None:
                    apply_slot_shifts(
                        locked_invoice, slot_shifts_data
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
            raise convert_model_validation_error(
                error
            ) from error

    # Response

    def to_representation(
        self,
        instance,
    ):
        return InvoiceDetailSerializer(
            instance,
            context=self.context,
        ).data