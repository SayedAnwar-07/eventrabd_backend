import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import (
    password_changed,
    validate_password,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework import serializers

from apps.users.models import User
from apps.users.utils import generate_otp, send_otp_email


# ── OTP Helpers ────────────────────────────────────────────────────────────────

OTP_KEY_SALT = "eventrabd.users.otp"


def hash_otp(otp: str) -> str:
    """
    Create a keyed HMAC hash of the OTP.

    The original OTP is never stored in the database.
    """
    return salted_hmac(
        key_salt=OTP_KEY_SALT,
        value=str(otp),
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()


def verify_otp(raw_otp: str, stored_hash: str) -> bool:
    """
    Compare an incoming OTP with the stored hash safely.
    """
    if not raw_otp or not stored_hash:
        return False

    expected_hash = hash_otp(raw_otp)

    return constant_time_compare(
        stored_hash,
        expected_hash,
    )


def otp_expiry():
    """
    Return a timezone-aware OTP expiration datetime.
    """
    seconds = getattr(
        settings,
        "OTP_VALIDITY_SECONDS",
        600,
    )

    return timezone.now() + timedelta(seconds=seconds)


# ── Register ───────────────────────────────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )

    confirm_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        required=False,
    )

    bio = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    service_area = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    contact_number = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    whatsapp_number = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    terms_accept = serializers.BooleanField(
        required=True,
    )

    ROLE_CHOICES = (
        "seller",
        "customer",
    )

    role = serializers.ChoiceField(
        choices=ROLE_CHOICES,
        default="customer",
    )

    class Meta:
        model = User
        fields = [
            "email",
            "full_name",
            "bio",
            "password",
            "confirm_password",
            "role",
            "service_area",
            "contact_number",
            "whatsapp_number",
            "terms_accept",
        ]

    def validate_terms_accept(self, value):
        if not value:
            raise serializers.ValidationError(
                "You must accept the terms & conditions."
            )

        return value

    def validate(self, data):
        password = data.get("password")
        confirm_password = data.get("confirm_password")
        role = data.get("role", "customer")

        if role in ("seller", "admin"):
            if not confirm_password:
                raise serializers.ValidationError(
                    {
                        "confirm_password": (
                            "This field is required."
                        )
                    }
                )

            if password != confirm_password:
                raise serializers.ValidationError(
                    {
                        "confirm_password": (
                            "Passwords do not match."
                        )
                    }
                )

        candidate_user = User(
            email=data.get("email"),
            full_name=data.get("full_name"),
            role=role,
        )

        try:
            validate_password(
                password,
                user=candidate_user,
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                {
                    "password": list(error.messages)
                }
            )

        if role == "seller":
            errors = {}

            if not data.get("service_area", "").strip():
                errors["service_area"] = (
                    "Service area is required for sellers."
                )

            if not data.get("contact_number", "").strip():
                errors["contact_number"] = (
                    "Contact number is required for sellers."
                )

            if not data.get("whatsapp_number", "").strip():
                errors["whatsapp_number"] = (
                    "WhatsApp number is required for sellers."
                )

            if errors:
                raise serializers.ValidationError(errors)

        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password", None)
        password = validated_data.pop("password")

        for field in (
            "service_area",
            "whatsapp_number",
            "contact_number",
        ):
            value = validated_data.get(field)

            if not value or not value.strip():
                validated_data[field] = None

        user = User.objects.create_user(
            **validated_data,
            password=password,
        )

        otp = generate_otp()

        user.access_token = hash_otp(otp)
        user.otp_expires_at = otp_expiry()

        user.save(
            update_fields=[
                "access_token",
                "otp_expires_at",
            ]
        )

        success, _ = send_otp_email(
            user=user,
            otp=otp,
            template_name="emails/register_otp.html",
        )

        if not success:
            user.delete()

            raise serializers.ValidationError(
                {
                    "email": (
                        "We could not send the verification "
                        "email. Please try again."
                    )
                }
            )

        return user

# ── Verify Registration OTP ────────────────────────────────────────────────────

class VerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()

    otp = serializers.CharField(
        write_only=True,
        trim_whitespace=True,
    )

    def validate(self, data):
        try:
            user = User.objects.get(
                email__iexact=data["email"]
            )
        except User.DoesNotExist:
            raise serializers.ValidationError(
                "Invalid email or OTP."
            )

        if (
            not user.otp_expires_at
            or timezone.now() >= user.otp_expires_at
        ):
            raise serializers.ValidationError(
                {
                    "otp": (
                        "OTP has expired. "
                        "Please request a new one."
                    )
                }
            )

        if not verify_otp(
            data["otp"],
            user.access_token,
        ):
            raise serializers.ValidationError(
                {
                    "otp": "Invalid email or OTP."
                }
            )

        user.is_verified = True
        user.access_token = ""
        user.otp_expires_at = None

        user.save(
            update_fields=[
                "is_verified",
                "access_token",
                "otp_expires_at",
            ]
        )

        return {
            "user": user,
        }


# ── Login ──────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()

    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )

    def validate(self, data):
        user = authenticate(
            email=data["email"],
            password=data["password"],
        )

        if not user:
            raise serializers.ValidationError(
                "Invalid email or password."
            )

        if not user.is_verified:
            raise serializers.ValidationError(
                "Account not verified. Please verify OTP."
            )

        if not user.is_active:
            raise serializers.ValidationError(
                "This account is inactive."
            )

        return {
            "user": user
        }


# ── Forgot Password ────────────────────────────────────────────────────────────

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, data):
        try:
            user = User.objects.get(
                email__iexact=data["email"]
            )
        except User.DoesNotExist:
            user = None

        if user:
            otp = generate_otp()

            user.refresh_token = hash_otp(otp)
            user.otp_expires_at = otp_expiry()

            user.save(
                update_fields=[
                    "refresh_token",
                    "otp_expires_at",
                ]
            )

            success, _ = send_otp_email(
                user=user,
                otp=otp,
                template_name=(
                    "emails/forgot_password_otp.html"
                ),
            )

            # Do not keep an active OTP that the user did not receive.
            if not success:
                user.refresh_token = ""
                user.otp_expires_at = None

                user.save(
                    update_fields=[
                        "refresh_token",
                        "otp_expires_at",
                    ]
                )

        # Always return the same response to prevent email enumeration.
        return {
            "message": (
                "If this email is registered, "
                "an OTP has been sent."
            )
        }


# ── Reset Password ─────────────────────────────────────────────────────────────

class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    otp = serializers.CharField(
        write_only=True,
        trim_whitespace=True,
    )

    new_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )

    confirm_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )

    def validate(self, data):
        new_password = data["new_password"]
        confirm_password = data["confirm_password"]

        if new_password != confirm_password:
            raise serializers.ValidationError(
                {
                    "confirm_password": (
                        "Passwords do not match."
                    )
                }
            )

        try:
            user = User.objects.get(
                email__iexact=data["email"]
            )
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {
                    "detail": "Invalid request."
                }
            )

        if (
            not user.otp_expires_at
            or timezone.now() >= user.otp_expires_at
        ):
            raise serializers.ValidationError(
                {
                    "otp": (
                        "OTP has expired. "
                        "Please request a new one."
                    )
                }
            )

        if not verify_otp(
            data["otp"],
            user.refresh_token,
        ):
            raise serializers.ValidationError(
                {
                    "otp": "Invalid OTP."
                }
            )

        try:
            validate_password(
                new_password,
                user=user,
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                {
                    "new_password": list(error.messages)
                }
            )

        user.set_password(new_password)

        # Remove all temporary OTP data.
        user.access_token = ""
        user.refresh_token = ""
        user.otp_expires_at = None

        # Invalidate JWT sessions issued before the password reset.
        user.token_version += 1

        user.save(
            update_fields=[
                "password",
                "access_token",
                "refresh_token",
                "otp_expires_at",
                "token_version",
            ]
        )

        password_changed(
            new_password,
            user=user,
        )

        return {
            "message": (
                "Password reset successful. "
                "Please log in again."
            )
        }


# ── Profile ────────────────────────────────────────────────────────────────────

class UserProfileSerializer(serializers.ModelSerializer):
    brand_slug = serializers.SerializerMethodField()

    class Meta:
        model = User

        fields = [
            "id",
            "email",
            "full_name",
            "username",
            "username_last_changed",
            "slug",
            "bio",
            "profile_image_url",
            "contact_number",
            "whatsapp_number",
            "office_address",
            "service_area",
            "role",
            "terms_accept",
            "is_verified",
            "brand_slug",
            "created_at",
        ]

        read_only_fields = [
            "email",
            "slug",
            "role",
            "is_verified",
            "username",
            "username_last_changed",
            "brand_slug",
        ]

    def get_brand_slug(self, obj):
        if obj.role != "seller":
            return None

        from apps.event_planner.models import EventBrand

        return (
            EventBrand.objects
            .filter(seller=obj)
            .values_list("slug", flat=True)
            .first()
        )


class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User

        fields = [
            "full_name",
            "username",
            "bio",
            "profile_image_url",
            "contact_number",
            "whatsapp_number",
            "office_address",
            "service_area",
        ]

    def validate_username(self, value):
        user = self.instance

        if not value:
            return value

        value = value.strip()

        if value != value.lower():
            raise serializers.ValidationError(
                "Username must be lowercase."
            )

        if not re.fullmatch(
            r"[a-z0-9-]+",
            value,
        ):
            raise serializers.ValidationError(
                "Only lowercase letters, numbers, "
                "and hyphens are allowed."
            )

        if value != user.username:
            if user.username_last_changed:
                days = (
                    timezone.now()
                    - user.username_last_changed
                ).days

                if days < 60:
                    raise serializers.ValidationError(
                        (
                            "Username cannot be changed now. "
                            f"Try again after {60 - days} days."
                        )
                    )

            if (
                User.objects
                .filter(username=value)
                .exclude(pk=user.pk)
                .exists()
            ):
                raise serializers.ValidationError(
                    "Username already taken."
                )

        return value


# ── Admin ──────────────────────────────────────────────────────────────────────

class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()

    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )

    def validate(self, data):
        user = authenticate(
            email=data["email"],
            password=data["password"],
        )

        if not user:
            raise serializers.ValidationError(
                "Invalid email or password."
            )

        if not user.is_verified:
            raise serializers.ValidationError(
                "Account not verified."
            )

        if not user.is_active:
            raise serializers.ValidationError(
                "This account is inactive."
            )

        if not user.is_staff:
            raise serializers.ValidationError(
                "Admin access only."
            )

        return {
            "user": user
        }


class AdminUserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User

        fields = [
            "id",
            "full_name",
            "email",
            "profile_image_url",
            "username",
            "slug",
            "role",
            "contact_number",
            "service_area",
            "is_verified",
            "is_staff",
            "created_at",
        ]