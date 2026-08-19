from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError as DjangoValidationError,
)
from django.db import IntegrityError, transaction
from django.db.models import F

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.event_planner.models import EventBrand
from apps.event_services.models import EventService
from apps.hires.models import Hire, HireStatus
from apps.users.models import User
from apps.notifications.models import (
    Notification,
    NotificationType,
)

from .models import (
    Review,
    ReviewRating,
    validate_review_image,
)


# =========================================================
# Helpers
# =========================================================

def convert_model_validation_error(error):
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


def validate_review_eligibility(hire, customer):
    """
    Final backend eligibility validation.

    Review allowed only when:
    - Request user is the hire customer
    - Hire is completed
    - Invoice exists
    - Customer agreed to invoice
    """

    if hire.customer_id != customer.id:
        raise PermissionDenied(
            "You cannot review another customer's hire."
        )

    if hire.status != HireStatus.COMPLETED:
        raise serializers.ValidationError({
            "hire": (
                "This hire must be completed before "
                "you can submit a review."
            )
        })

    try:
        invoice = hire.invoice
    except ObjectDoesNotExist:
        raise serializers.ValidationError({
            "hire": (
                "This hire does not have an invoice."
            )
        })

    if invoice.customer_agreed is not True:
        raise serializers.ValidationError({
            "hire": (
                "You must agree to the invoice before "
                "submitting a review."
            )
        })

    return hire


# =========================================================
# Customer summary
# =========================================================

class ReviewCustomerSerializer(
    serializers.ModelSerializer
):
    profile_image_url = serializers.SerializerMethodField()

    class Meta:
        model = User

        fields = [
            "id",
            "full_name",
            "profile_image_url",
        ]

        read_only_fields = fields

    def get_profile_image_url(self, obj):
        if not obj.profile_image:
            return None

        try:
            return obj.profile_image.build_url(
                transformation=[
                    {
                        "width": 300,
                        "height": 300,
                        "crop": "limit",
                    }
                ],
                quality="auto",
                fetch_format="auto",
            )

        except Exception:
            return None


# =========================================================
# Review detail / list serializer
# =========================================================

class ReviewDetailSerializer(
    serializers.ModelSerializer
):
    customer = ReviewCustomerSerializer(
        source="hire.customer",
        read_only=True,
    )

    hire_id = serializers.CharField(
        source="hire.id",
        read_only=True,
    )

    service_id = serializers.CharField(
        source="hire.service.id",
        read_only=True,
    )

    brand_id = serializers.CharField(
        source="hire.service.brand.id",
        read_only=True,
    )

    stars = serializers.DecimalField(
        max_digits=2,
        decimal_places=1,
        read_only=True,
    )

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Review

        fields = [
            "id",
            "hire_id",
            "service_id",
            "brand_id",
            "customer",
            "rating",
            "stars",
            "comment",
            "image_url",
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


# =========================================================
# Create serializer
# =========================================================

class ReviewCreateSerializer(
    serializers.ModelSerializer
):
    hire = serializers.PrimaryKeyRelatedField(
        queryset=Hire.objects.none(),
        error_messages={
            "required": "A hire request is required.",
            "does_not_exist": (
                "The selected hire request does not exist "
                "or does not belong to you."
            ),
            "incorrect_type": "Invalid hire request ID.",
        },
    )

    rating = serializers.ChoiceField(
        choices=ReviewRating.choices,
        error_messages={
            "required": "Rating is required.",
            "invalid_choice": (
                "Rating must be an integer from 2 to 10."
            ),
        },
    )

    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )

    image = serializers.ImageField(
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Review

        fields = [
            "hire",
            "rating",
            "comment",
            "image",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")

        if not request:
            return

        user = request.user

        if (
            user.is_authenticated
            and getattr(user, "role", None) == "customer"
        ):
            self.fields["hire"].queryset = (
                Hire.objects
                .select_related(
                    "customer",
                    "service",
                    "service__brand",
                    "invoice",
                )
                .filter(
                    customer=user,
                )
            )

    def validate_image(self, value):
        if value is None:
            return value

        try:
            validate_review_image(value)

        except DjangoValidationError as error:
            if hasattr(error, "messages"):
                raise serializers.ValidationError(
                    error.messages[0]
                ) from error

            raise serializers.ValidationError(
                str(error)
            ) from error

        return value

    def validate(self, attrs):
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

        if getattr(user, "role", None) != "customer":
            raise PermissionDenied(
                "Only customers can submit reviews."
            )

        hire = attrs.get("hire")

        validate_review_eligibility(
            hire=hire,
            customer=user,
        )

        if Review.objects.filter(
            hire_id=hire.id,
        ).exists():
            raise serializers.ValidationError({
                "hire": (
                    "You have already reviewed this hire."
                )
            })

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        customer = request.user

        submitted_hire = validated_data.pop("hire")

        try:
            with transaction.atomic():
                # Lock only the Hire row.
                # Do not join the nullable reverse OneToOne
                # invoice relation in this FOR UPDATE query.
                hire = (
                    Hire.objects
                    .select_for_update(
                        of=("self",)
                    )
                    .select_related(
                        "customer",
                        "service",
                        "service__brand",
                        "service__brand__seller",
                    )
                    .get(
                        pk=submitted_hire.pk,
                    )
                )

                # Re-check eligibility after locking the hire.
                # hire.invoice will be fetched separately when needed.
                validate_review_eligibility(
                    hire=hire,
                    customer=customer,
                )

                # Extra application-level duplicate protection.
                if Review.objects.filter(
                    hire_id=hire.id,
                ).exists():
                    raise serializers.ValidationError({
                        "hire": (
                            "You have already reviewed "
                            "this hire."
                        )
                    })

                review = Review.objects.create(
                    hire=hire,
                    **validated_data,
                )

                rating = review.rating

                # Atomic service rating statistics.
                EventService.objects.filter(
                    pk=hire.service_id,
                ).update(
                    rating_sum=(
                        F("rating_sum") + rating
                    ),
                    review_count=(
                        F("review_count") + 1
                    ),
                )

                EventBrand.objects.filter(
                    pk=hire.service.brand_id,
                ).update(
                    rating_sum=(
                        F("rating_sum") + rating
                    ),
                    review_count=(
                        F("review_count") + 1
                    ),
                )

                # -----------------------------------------
                # Notify seller about new review
                # -----------------------------------------

                # -----------------------------------------
                # Notify seller about new review
                # -----------------------------------------

                seller = hire.service.brand.seller

                notification = Notification.objects.create(
                    recipient=seller,
                    review=review,
                    notification_type=(
                        NotificationType.REVIEW_CREATED
                    ),
                    title="New Service Review",
                    message=(
                        f"{customer.full_name} left a "
                        f"{review.stars}-star review on your "
                        f"{hire.service.get_service_name_display()} "
                        f"service."
                    ),
                    data={
                        "review_id": str(review.id),
                        "hire_id": str(hire.id),
                        "service_id": str(hire.service_id),
                        "service_name": hire.service.service_name,
                        "brand_slug": hire.service.brand.slug,
                        "brand_id": str(hire.service.brand_id),
                        "rating": str(review.stars),
                    },
                )

                from apps.notifications.services import send_notification_to_user

                send_notification_to_user(notification)

                return review

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
                    "You have already reviewed "
                    "this hire."
                )
            }) from error

        except DjangoValidationError as error:
            raise convert_model_validation_error(
                error
            ) from error


# =========================================================
# Update serializer
# =========================================================

class ReviewUpdateSerializer(
    serializers.ModelSerializer
):
    rating = serializers.ChoiceField(
        choices=ReviewRating.choices,
        required=False,
        error_messages={
            "invalid_choice": (
                "Rating must be an integer from 2 to 10."
            ),
        },
    )

    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    image = serializers.ImageField(
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Review

        fields = [
            "rating",
            "comment",
            "image",
        ]

    def validate_image(self, value):
        if value is None:
            return value

        try:
            validate_review_image(value)

        except DjangoValidationError as error:
            if hasattr(error, "messages"):
                raise serializers.ValidationError(
                    error.messages[0]
                ) from error

            raise serializers.ValidationError(
                str(error)
            ) from error

        return value

    def validate(self, attrs):
        request = self.context.get("request")
        review = self.instance

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
                "Only customers can edit reviews."
            )

        if review.hire.customer_id != user.id:
            raise PermissionDenied(
                "You cannot edit another customer's review."
            )

        return attrs

    def update(self, instance, validated_data):
        request = self.context["request"]
        customer = request.user

        try:
            with transaction.atomic():

                locked_review = (
                    Review.objects
                    .select_for_update(
                        of=("self",)
                    )
                    .select_related(
                        "hire",
                        "hire__customer",
                        "hire__service",
                        "hire__service__brand",
                    )
                    .get(
                        pk=instance.pk,
                    )
                )

                if (
                    locked_review.hire.customer_id
                    != customer.id
                ):
                    raise PermissionDenied(
                        "You cannot edit this review."
                    )

                validate_review_eligibility(
                    hire=locked_review.hire,
                    customer=customer,
                )

                old_rating = locked_review.rating

                new_rating = validated_data.get(
                    "rating",
                    old_rating,
                )

                changed = False

                for field_name, new_value in validated_data.items():
                    old_value = getattr(
                        locked_review,
                        field_name,
                    )

                    if old_value == new_value:
                        continue

                    setattr(
                        locked_review,
                        field_name,
                        new_value,
                    )

                    changed = True

                if not changed:
                    return locked_review

                locked_review.save()

                rating_difference = (
                    new_rating - old_rating
                )

                if rating_difference:
                    EventService.objects.filter(
                        pk=locked_review.hire.service_id,
                    ).update(
                        rating_sum=(
                            F("rating_sum")
                            + rating_difference
                        )
                    )

                    EventBrand.objects.filter(
                        pk=(
                            locked_review
                            .hire
                            .service
                            .brand_id
                        ),
                    ).update(
                        rating_sum=(
                            F("rating_sum")
                            + rating_difference
                        )
                    )

                return locked_review

        except Review.DoesNotExist as error:
            raise serializers.ValidationError({
                "detail": (
                    "The review could not be found."
                )
            }) from error

        except DjangoValidationError as error:
            raise convert_model_validation_error(
                error
            ) from error