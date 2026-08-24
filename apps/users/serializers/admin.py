from django.contrib.auth import authenticate

from rest_framework import serializers

from apps.users.models import User



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