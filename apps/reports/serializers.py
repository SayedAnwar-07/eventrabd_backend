from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError as DjangoValidationError,
)

from rest_framework import serializers

from django.db import IntegrityError, transaction
from django.db.models import F

from apps.event_services.models import EventService
from apps.hires.models import Hire, HireStatus

from .models import (
    ReportStatus,
    ServiceReport,
)


class ReportSellerSerializer(serializers.Serializer):
    id = serializers.CharField(
        read_only=True,
    )

    full_name = serializers.CharField(
        read_only=True,
    )
    
    email = serializers.CharField(
        read_only=True,
    )

    whatsapp_number = serializers.CharField(
        read_only=True,
    )

    contact_number = serializers.CharField(
        read_only=True,
    )


class ReportServiceSerializer(serializers.ModelSerializer):
    service_display_name = serializers.CharField(
        source="get_service_name_display",
        read_only=True,
    )

    brand_name = serializers.CharField(
        source="brand.brand_name",
        read_only=True,
    )

    brand_display_name = serializers.CharField(
        source="brand.display_name",
        read_only=True,
    )

    seller = ReportSellerSerializer(
        source="brand.seller",
        read_only=True,
    )

    class Meta:
        model = EventService

        fields = [
            "id",
            "service_name",
            "service_display_name",
            "slug",
            "brand_name",
            "brand_display_name",
            "seller",
        ]

        read_only_fields = fields


class ReportReporterSerializer(serializers.Serializer):
    id = serializers.CharField(
        read_only=True,
    )

    full_name = serializers.CharField(
        read_only=True,
    )

    email = serializers.EmailField(
        read_only=True,
    )

    image_url = serializers.SerializerMethodField()

    def get_image_url(self, obj):
        if not getattr(obj, "image", None):
            return None

        try:
            return obj.image.url
        except (AttributeError, ValueError):
            return None


class ServiceReportDetailSerializer(
    serializers.ModelSerializer
):
    reporter = ReportReporterSerializer(
        read_only=True,
    )

    service = ReportServiceSerializer(
        read_only=True,
    )

    hire_id = serializers.CharField(
        source="hire.id",
        read_only=True,
    )

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ServiceReport

        fields = [
            "id",
            "reporter",
            "hire_id",
            "service",
            "message",
            "image_url",
            "status",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields

    def get_image_url(self, obj):
        if not obj.image:
            return None

        try:
            return obj.image.url
        except Exception:
            return None


class ServiceReportCreateSerializer(
    serializers.ModelSerializer
):
    hire = serializers.PrimaryKeyRelatedField(
        queryset=(
            Hire.objects
            .select_related(
                "customer",
                "service",
                "service__brand",
            )
        ),
    )

    message = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        max_length=3000,
    )

    image = serializers.ImageField(
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ServiceReport

        fields = [
            "hire",
            "message",
            "image",
        ]

    def validate_hire(self, hire):
        request = self.context.get("request")

        # =================================================
        # Authentication
        # =================================================

        if (
            not request
            or not request.user.is_authenticated
        ):
            raise serializers.ValidationError(
                "Authentication is required."
            )

        user = request.user

        # =================================================
        # Customer only
        # =================================================

        if (
            getattr(
                user,
                "role",
                None,
            )
            != "customer"
        ):
            raise serializers.ValidationError(
                "Only customers can create reports."
            )

        # =================================================
        # Hire ownership
        # =================================================

        if hire.customer_id != user.id:
            raise serializers.ValidationError(
                "You can only report a service "
                "that you personally hired."
            )

        # =================================================
        # Hire must be completed
        # =================================================

        if hire.status != HireStatus.COMPLETED:
            raise serializers.ValidationError(
                "You can report this service only "
                "after the hire has been completed."
            )

        # =================================================
        # Invoice must exist
        # =================================================

        try:
            invoice = hire.invoice

        except ObjectDoesNotExist:
            raise serializers.ValidationError(
                "The invoice process must be completed "
                "before you can report this service."
            )

        # =================================================
        # Customer must agree with invoice
        # =================================================

        if invoice.customer_agreed is not True:
            raise serializers.ValidationError(
                "You can report this service only "
                "after you have agreed to the invoice."
            )

        # =================================================
        # One report per Hire
        # =================================================

        if ServiceReport.objects.filter(
            hire=hire
        ).exists():
            raise serializers.ValidationError(
                "You have already submitted a report "
                "for this hire."
            )

        return hire

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]

        hire = validated_data.pop(
            "hire"
        )

        try:
            # =============================================
            # Create report
            # =============================================

            report = ServiceReport.objects.create(
                reporter=request.user,

                # Service always comes from Hire.
                # Never trust service ID from frontend.
                service=hire.service,

                hire=hire,

                **validated_data,
            )

            # =============================================
            # Increase service report count
            # =============================================

            EventService.objects.filter(
                pk=hire.service_id
            ).update(
                report_count=(
                    F("report_count") + 1
                )
            )

            return report

        except IntegrityError as error:
            raise serializers.ValidationError({
                "hire": (
                    "You have already submitted "
                    "a report for this hire."
                )
            }) from error

        except DjangoValidationError as error:
            if hasattr(
                error,
                "message_dict",
            ):
                raise serializers.ValidationError(
                    error.message_dict
                ) from error

            raise serializers.ValidationError({
                "detail": error.messages,
            }) from error

    def to_representation(
        self,
        instance,
    ):
        return ServiceReportDetailSerializer(
            instance,
            context=self.context,
        ).data


class AdminReportStatusUpdateSerializer(
    serializers.ModelSerializer
):
    status = serializers.ChoiceField(
        choices=ReportStatus.choices,
        required=True,
    )

    class Meta:
        model = ServiceReport

        fields = [
            "status",
        ]