import hashlib
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import serializers

from apps.users.models import User
from apps.users.utils import generate_otp, send_otp_email
import re

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError


# ── Helpers ────────────────────────────────────────────────────────────────────

def hash_otp(otp: str) -> str:
    """SHA-256 hash of the OTP. Never store plain OTPs in the DB."""
    return hashlib.sha256(otp.encode()).hexdigest()


def otp_expiry() -> object:
    """Returns timezone-aware expiry datetime (now + OTP_VALIDITY_SECONDS)."""
    seconds = getattr(settings, 'OTP_VALIDITY_SECONDS', 600)
    return timezone.now() + timedelta(seconds=seconds)


# ── Register ───────────────────────────────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    password         = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    bio              = serializers.CharField(required=False, allow_blank=True)

    service_area     = serializers.CharField(required=False, allow_blank=True)
    contact_number   = serializers.CharField(required=False, allow_blank=True)
    whatsapp_number  = serializers.CharField(required=False, allow_blank=True)

    terms_accept = serializers.BooleanField(required=True)

    ROLE_CHOICES = ("seller", "customer")
    role = serializers.ChoiceField(choices=ROLE_CHOICES, default="customer")

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

    def validate_username(self, value):
        if not value:
            return value

        if not re.match(r"^[a-z0-9\-]+$", value):
            raise serializers.ValidationError(
                "Only lowercase letters, numbers and hyphens allowed."
            )

        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")

        return value.lower()

    def validate_terms_accept(self, value):
        if not value:
            raise serializers.ValidationError("You must accept the terms & conditions.")
        return value

    def validate(self, data):
        if data.get("password") != data.get("confirm_password"):
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match"}
            )
        try:
            validate_password(data.get("password"))
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})

        role = data.get("role", "customer")

        if role == "seller":
            errors = {}
            if not data.get("service_area", "").strip():
                errors["service_area"] = "Service area is required for sellers."
            if not data.get("contact_number", "").strip():
                errors["contact_number"] = "Contact number is required for sellers."
            if not data.get("whatsapp_number", "").strip():
                errors["whatsapp_number"] = "WhatsApp number is required for sellers."
            if errors:
                raise serializers.ValidationError(errors)

        if role == "customer":
            if not data.get("contact_number", "").strip():
                raise serializers.ValidationError(
                    {"contact_number": "Contact number is required."}
                )

        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")
        username = validated_data.get("username")

        # If blank → let model generate it
        if not username:
            validated_data.pop("username", None)

        for field in ("service_area", "whatsapp_number"):
            if not validated_data.get(field, "").strip():
                validated_data[field] = None

        user = User.objects.create_user(**validated_data, password=password)
        otp = generate_otp()
        user.access_token     = hash_otp(otp)
        user.otp_expires_at   = otp_expiry()
        user.save()

        send_otp_email(user, otp, "emails/register_otp.html")
        return user


# ── Verify OTP ─────────────────────────────────────────────────────────────────

class VerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp   = serializers.CharField()

    def validate(self, data):
        try:
            user = User.objects.get(email=data["email"])
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email or OTP.")  # no enumeration

        # CRITICAL FIX #2 — Check expiry before comparing.
        if user.otp_expires_at and timezone.now() > user.otp_expires_at:
            raise serializers.ValidationError("OTP has expired. Please request a new one.")

        # CRITICAL FIX #1 — Compare hashes, never plain text.
        if user.access_token != hash_otp(data["otp"]):
            raise serializers.ValidationError("Invalid email or OTP.")

        user.is_verified    = True
        user.access_token   = ""
        user.otp_expires_at = None
        user.save()
        return {"message": "Account verified successfully"}


# ── Login ──────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, data):
        user = authenticate(email=data["email"], password=data["password"])
        if not user:
            raise serializers.ValidationError("Invalid email or password")
        if not user.is_verified:
            raise serializers.ValidationError("Account not verified. Please verify OTP.")
        return {"user": user}


# ── Forgot Password ────────────────────────────────────────────────────────────

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, data):
        # SECURITY: Always return the same message — prevents email enumeration.
        try:
            user = User.objects.get(email=data["email"])
            otp = generate_otp()
            user.refresh_token   = hash_otp(otp)     # CRITICAL FIX #1 — hash it
            user.otp_expires_at  = otp_expiry()       # CRITICAL FIX #2 — set expiry
            user.save()
            send_otp_email(user, otp, "emails/forgot_password_otp.html")
        except User.DoesNotExist:
            pass  # silent — do not reveal whether email exists

        return {"message": "If this email is registered, an OTP has been sent."}


# ── Reset Password ─────────────────────────────────────────────────────────────

class ResetPasswordSerializer(serializers.Serializer):
    email            = serializers.EmailField()
    otp              = serializers.CharField()
    new_password     = serializers.CharField()
    confirm_password = serializers.CharField()

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match"})

        try:
            user = User.objects.get(email=data["email"])
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid request.")

        # CRITICAL FIX #2 — Check expiry.
        if user.otp_expires_at and timezone.now() > user.otp_expires_at:
            raise serializers.ValidationError("OTP has expired. Please request a new one.")

        # CRITICAL FIX #1 — Compare hashes.
        if user.refresh_token != hash_otp(data["otp"]):
            raise serializers.ValidationError("Invalid OTP.")

        user.set_password(data["new_password"])
        user.refresh_token  = ""
        user.otp_expires_at = None
        user.save()
        return {"message": "Password reset successful"}


# ── Profile ────────────────────────────────────────────────────────────────────

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "email", "full_name", "username", "username_last_changed",
            "slug", "bio", "profile_image_url", "contact_number",
            "whatsapp_number", "office_address", "service_area",
            "role", "terms_accept", "is_verified", "created_at",
        ]
        read_only_fields = [
            "email", "slug", "role", "is_verified",
            "username", "username_last_changed",
        ]


class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "full_name", "username", "bio",
            "profile_image_url", "contact_number",
            "whatsapp_number", "office_address", "service_area",
        ]

    def validate_username(self, value):
        user = self.instance

        if not value:
            return value

        if value != value.lower():
            raise serializers.ValidationError("Username must be lowercase.")

        if not re.match(r"^[a-z0-9\-]+$", value):
            raise serializers.ValidationError(
                "Only lowercase letters, numbers, and hyphens are allowed."
            )

        if value != user.username:
            if user.username_last_changed:
                days = (timezone.now() - user.username_last_changed).days
                if days < 60:
                    raise serializers.ValidationError(
                        f"Username cannot be changed now. Try again after {60 - days} days."
                    )

        return value

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)