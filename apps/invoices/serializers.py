from decimal import Decimal

from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from .emails import send_invoice_created_email

from apps.hires.models import Hire, HireStatus
from apps.notifications.services import (
    create_invoice_created_notification,
    create_invoice_updated_notification,
)

from .models import (
    Invoice,
    MAX_TERM_LENGTH,
    MAX_TERMS_CONDITIONS,
    ZERO_AMOUNT,
)


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
        }
    
    def get_service_summary(self, obj):
        service = obj.hire.service
        slot_count = obj.hire.booking_slots.count()

        shift_hour = service.shift_hour or 0
        shift_charge = service.shift_charge or ZERO_AMOUNT

        return {
            "slot_count": slot_count,
            "shift_hour_per_slot": shift_hour,
            "total_shift_hours": shift_hour * slot_count,
            "shift_charge_per_slot": f"{shift_charge:.2f}",
            "total_amount": f"{obj.service_price:.2f}",
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
    )

    service_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    discount_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO_AMOUNT,
        default=ZERO_AMOUNT,
    )

    advance_payment = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO_AMOUNT,
        default=ZERO_AMOUNT,
    )
    
    terms_conditions = serializers.ListField(
        child=serializers.CharField(
            max_length=MAX_TERM_LENGTH,
            allow_blank=False,
            trim_whitespace=True,
        ),
        required=False,
        allow_empty=True,
        max_length=MAX_TERMS_CONDITIONS,
    )

    class Meta:
        model = Invoice
        fields = [
            "hire",
            "due_payment_last_date",
            "service_price",
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

    def validate_hire(self, hire):
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

        seller_id = hire.service.brand.seller_id

        if seller_id != user.id:
            raise PermissionDenied(
                "You cannot create an invoice for "
                "another seller's hire."
            )

        if hire.status != HireStatus.ACCEPTED:
            raise serializers.ValidationError(
                "An invoice can only be created "
                "for an accepted hire."
            )

        if Invoice.objects.filter(hire=hire).exists():
            raise serializers.ValidationError(
                "An invoice already exists for this hire."
            )

        return hire

    def validate_due_payment_last_date(
        self,
        value,
    ):
        if value < timezone.localdate():
            raise serializers.ValidationError(
                "Due payment date cannot be in the past."
            )

        return value

    def validate(self, attrs):
        hire = attrs.get("hire")

        if hire is None:
            raise serializers.ValidationError({
                "hire": "A hire request is required."
            })

        slot_count = hire.booking_slots.count()

        if slot_count < 1:
            raise serializers.ValidationError({
                "hire": "This hire has no booking slots."
            })

        shift_charge = (
            hire.service.shift_charge
            or ZERO_AMOUNT
        )

        attrs["service_price"] = (
            shift_charge * slot_count
        )

        return validate_invoice_financial_data(
            attrs
        )

    def create(self, validated_data):
        request = self.context["request"]
        seller = request.user

        submitted_hire = validated_data.pop(
            "hire"
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
                        "service__brand__seller",
                    )
                    .get(pk=submitted_hire.pk)
                )

                if hire.status != HireStatus.ACCEPTED:
                    raise serializers.ValidationError({
                        "hire": (
                            "The hire is no longer accepted."
                        )
                    })

                if (
                    hire.service.brand.seller_id
                    != seller.id
                ):
                    raise PermissionDenied(
                        "You cannot create an invoice "
                        "for this hire."
                    )

                if Invoice.objects.filter(
                    hire=hire
                ).exists():
                    raise serializers.ValidationError({
                        "hire": (
                            "An invoice already exists "
                            "for this hire."
                        )
                    })

                slot_count = (
                    hire.booking_slots.count()
                )

                if slot_count < 1:
                    raise serializers.ValidationError({
                        "hire": (
                            "This hire has no booking slots."
                        )
                    })

                shift_charge = (
                    hire.service.shift_charge
                    or ZERO_AMOUNT
                )

                validated_data["service_price"] = (
                    shift_charge * slot_count
                )

                validate_invoice_financial_data(
                    validated_data
                )

                invoice = Invoice.objects.create(
                    hire=hire,
                    **validated_data,
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

        except Hire.DoesNotExist as error:
            raise serializers.ValidationError({
                "hire": (
                    "The selected hire does not exist."
                )
            }) from error

        except IntegrityError as error:
            raise serializers.ValidationError({
                "hire": (
                    "An invoice already exists "
                    "for this hire."
                )
            }) from error

        return invoice

    def to_representation(self, instance):
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
            raise serializers.ValidationError(
                {
                    "detail": (
                        "Invoice does not exist."
                    )
                }
            ) from error

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
        min_value=MINIMUM_SERVICE_PRICE,
        required=False,
    )

    discount_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO_AMOUNT,
        required=False,
    )

    advance_payment = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=ZERO_AMOUNT,
        required=False,
    )

    due_payment_last_date = (
        serializers.DateField(
            required=False,
        )
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
        ),
        required=False,
        allow_empty=True,
        max_length=MAX_TERMS_CONDITIONS,
    )

    class Meta:
        model = Invoice

        fields = [
            "due_payment_last_date",
            "service_price",
            "discount_price",
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
            raise serializers.ValidationError(
                {
                    "detail": (
                        "Invoice instance is required."
                    )
                }
            )

        seller_id = (
            invoice.hire.service.brand.seller_id
        )

        if seller_id != user.id:
            raise PermissionDenied(
                "You cannot edit another "
                "seller's invoice."
            )

        if invoice.customer_agreed is not None:
            raise serializers.ValidationError(
                {
                    "detail": (
                        "This invoice can no longer be "
                        "edited because the customer has "
                        "already submitted a decision."
                    )
                }
            )

        if (
            timezone.localdate()
            > invoice.due_payment_last_date
        ):
            raise serializers.ValidationError(
                {
                    "detail": (
                        "This invoice can no longer be "
                        "edited because the due payment "
                        "date has passed."
                    )
                }
            )

        return validate_invoice_financial_data(
            attrs,
            instance=invoice,
        )

    def update(
        self,
        instance,
        validated_data,
    ):
        request = self.context["request"]
        seller = request.user

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

                if (
                    locked_invoice.customer_agreed
                    is not None
                ):
                    raise serializers.ValidationError(
                        {
                            "detail": (
                                "This invoice can no "
                                "longer be edited because "
                                "the customer has already "
                                "submitted a decision."
                            )
                        }
                    )

                if (
                    timezone.localdate()
                    > locked_invoice
                    .due_payment_last_date
                ):
                    raise serializers.ValidationError(
                        {
                            "detail": (
                                "This invoice can no "
                                "longer be edited because "
                                "the due payment date "
                                "has passed."
                            )
                        }
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

                    if old_value != new_value:
                        setattr(
                            locked_invoice,
                            field_name,
                            new_value,
                        )

                        changed_fields.append(
                            field_name
                        )

                if not changed_fields:
                    return locked_invoice

                locked_invoice.save()

                create_invoice_updated_notification(
                    invoice=locked_invoice,
                    changed_fields=changed_fields,
                )

        except Invoice.DoesNotExist as error:
            raise serializers.ValidationError(
                {
                    "detail": (
                        "Invoice does not exist."
                    )
                }
            ) from error

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