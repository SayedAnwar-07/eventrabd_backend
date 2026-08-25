from django.contrib.auth import authenticate
from rest_framework import serializers
from apps.users.models import User
from django.contrib.auth.password_validation import validate_password
from apps.event_planner.utils import validate_image_size
from django.utils import timezone
from apps.users.utils import (
    generate_otp,
    send_otp_email,
)
from .auth import (
    hash_otp,
    otp_expiry,
    verify_otp,
)


# ── Admin Login ────────────────────────────────────────────────────────────────

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
            "user": user,
        }


# ── Admin Profile ──────────────────────────────────────────────────────────────

class AdminProfileSerializer(serializers.ModelSerializer):

    profile_image_url = serializers.SerializerMethodField()


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
            "role",
            "terms_accept",
            "is_verified",
            "is_staff",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "email",
            "username",
            "username_last_changed",
            "slug",
            "role",
            "terms_accept",
            "is_verified",
            "is_staff",
            "created_at",
        ]


    def get_profile_image_url(self,obj):

        if not obj.profile_image:
            return None

        return obj.profile_image.build_url(
            transformation=[
                {
                    "width":500,
                    "height":500,
                    "crop":"limit",
                }
            ],
            quality="auto",
            fetch_format="auto",
        )


class AdminProfileUpdateSerializer(serializers.ModelSerializer):

    class Meta:

        model = User

        fields = [
            "full_name",
            "bio",
            "profile_image",
            "contact_number",
            "whatsapp_number",
        ]


    def validate_profile_image(self,value):

        if value:
            validate_image_size(value)

        return value


# ── Admin User List ───────────────────────────────────────────────────────────

class AdminUserListSerializer(serializers.ModelSerializer):

    profile_image_url = serializers.SerializerMethodField()



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

            "whatsapp_number",

            "is_verified",

            "is_staff",

            "created_at",

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
        
       
# ── Admin Forgot Password ───────────────────────────────────────────────────────────
 
class AdminForgotPasswordSerializer(serializers.Serializer):

    email = serializers.EmailField()


    def validate(self,data):

        try:

            user = User.objects.get(
                email__iexact=data["email"],
                is_staff=True,
            )

        except User.DoesNotExist:

            raise serializers.ValidationError(
                {
                    "email":
                    "Admin account not found."
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


        send_otp_email(
            user=user,
            otp=otp,
            template_name="admin/auth/admin_reset_password.html"
        )


        return {
            "message":
            "OTP sent successfully."
        }
        

# ── Admin Reset Password ───────────────────────────────────────────────────────────

class AdminResetPasswordSerializer(serializers.Serializer):

    email = serializers.EmailField()

    otp = serializers.CharField()

    new_password = serializers.CharField(
        write_only=True
    )

    confirm_password = serializers.CharField(
        write_only=True
    )


    def validate(self,data):

        if data["new_password"] != data["confirm_password"]:

            raise serializers.ValidationError(
                {
                    "confirm_password":
                    "Passwords do not match."
                }
            )


        user = User.objects.filter(
            email__iexact=data["email"],
            is_staff=True,
        ).first()


        if not user:
            raise serializers.ValidationError(
                "Invalid request."
            )

        if (
            not user.otp_expires_at
            or timezone.now() >= user.otp_expires_at
        ):

            raise serializers.ValidationError(
                {
                    "otp": "OTP expired."
                }
            )


        if not verify_otp(
            data["otp"],
            user.refresh_token
        ):

            raise serializers.ValidationError(
                {
                    "otp": "Invalid OTP."
                }
            )


        validate_password(
            data["new_password"],
            user=user,
        )


        user.set_password(
            data["new_password"]
        )


        user.refresh_token=""
        user.otp_expires_at=None

        # logout every device
        user.token_version += 1


        user.save(
            update_fields=[
                "password",
                "refresh_token",
                "otp_expires_at",
                "token_version",
            ]
        )


        return {
            "message":
            "Admin password reset successful."
        }