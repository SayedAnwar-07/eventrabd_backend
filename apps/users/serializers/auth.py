import logging

from datetime import timedelta

from django.conf import settings

from django.contrib.auth import authenticate

from django.contrib.auth.password_validation import (
    password_changed,
    validate_password,
)

from django.core.exceptions import ValidationError as DjangoValidationError

from django.utils import timezone

from django.utils.crypto import (
    constant_time_compare,
    salted_hmac,
)

from rest_framework import serializers


from apps.users.models import User

from apps.users.utils import (
    generate_otp,
    send_otp_email,
)


logger = logging.getLogger(__name__)



# ── OTP Helpers ────────────────────────────────────────────────────────────────

OTP_KEY_SALT = "eventrabd.users.otp"



def hash_otp(otp: str) -> str:

    return salted_hmac(
        key_salt=OTP_KEY_SALT,
        value=str(otp),
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()



def verify_otp(
    raw_otp: str,
    stored_hash: str,
) -> bool:

    if not raw_otp or not stored_hash:
        return False


    expected_hash = hash_otp(raw_otp)


    return constant_time_compare(
        stored_hash,
        expected_hash,
    )



def otp_expiry():

    seconds = getattr(
        settings,
        "OTP_VALIDITY_SECONDS",
        600,
    )


    return timezone.now() + timedelta(
        seconds=seconds
    )



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

        confirm_password = data.get(
            "confirm_password"
        )

        role = data.get(
            "role",
            "customer",
        )


        if role == "seller":

            if not confirm_password:

                raise serializers.ValidationError(
                    {
                        "confirm_password":
                        "This field is required."
                    }
                )


            if password != confirm_password:

                raise serializers.ValidationError(
                    {
                        "confirm_password":
                        "Passwords do not match."
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
                    "password":
                    list(error.messages)
                }
            )



        if role == "seller":

            errors = {}


            if not data.get(
                "contact_number",
                "",
            ).strip():

                errors["contact_number"] = (
                    "Contact number is required for sellers."
                )


            if not data.get(
                "whatsapp_number",
                "",
            ).strip():

                errors["whatsapp_number"] = (
                    "WhatsApp number is required for sellers."
                )



            if errors:

                raise serializers.ValidationError(
                    errors
                )



        return data



    def create(self, validated_data):

        validated_data.pop(
            "confirm_password",
            None,
        )


        password = validated_data.pop(
            "password"
        )



        for field in (
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
                    "email":
                    "We could not send the verification email. Please try again."
                }
            )



        return user





# ── Verify OTP ────────────────────────────────────────────────────────────────

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
                    "otp":
                    "OTP has expired. Please request a new one."
                }
            )



        if not verify_otp(
            data["otp"],
            user.access_token,
        ):

            raise serializers.ValidationError(
                {
                    "otp":
                    "Invalid email or OTP."
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






# ── Login ─────────────────────────────────────────────────────────────────────

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





# ── Forgot Password ───────────────────────────────────────────────────────────

class ForgotPasswordSerializer(serializers.Serializer):

    email = serializers.EmailField()



    def validate(self, data):

        try:

            user = User.objects.get(
                email__iexact=data["email"]
            )


        except User.DoesNotExist:

            raise serializers.ValidationError(
                {
                    "email":
                    ["Email not found."]
                }
            )



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
            template_name="emails/forgot_password_otp.html",
        )



        if not success:

            user.refresh_token = ""

            user.otp_expires_at = None



            user.save(
                update_fields=[
                    "refresh_token",
                    "otp_expires_at",
                ]
            )



        return {
            "message":
            "OTP sent successfully."
        }





# ── Reset Password ────────────────────────────────────────────────────────────

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

        if data["new_password"] != data["confirm_password"]:

            raise serializers.ValidationError(
                {
                    "confirm_password":
                    "Passwords do not match."
                }
            )



        try:

            user = User.objects.get(
                email__iexact=data["email"]
            )


        except User.DoesNotExist:

            raise serializers.ValidationError(
                {
                    "detail":
                    "Invalid request."
                }
            )



        if (
            not user.otp_expires_at
            or timezone.now() >= user.otp_expires_at
        ):

            raise serializers.ValidationError(
                {
                    "otp":
                    "OTP has expired. Please request a new one."
                }
            )



        if not verify_otp(
            data["otp"],
            user.refresh_token,
        ):

            raise serializers.ValidationError(
                {
                    "otp":
                    "Invalid OTP. Please check and try again."
                }
            )



        validate_password(
            data["new_password"],
            user=user,
        )



        user.set_password(
            data["new_password"]
        )



        user.access_token = ""

        user.refresh_token = ""

        user.otp_expires_at = None

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
            data["new_password"],
            user=user,
        )



        return {
            "message":
            "Password reset successful. Please log in again."
        }