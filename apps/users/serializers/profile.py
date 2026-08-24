import re

from django.utils import timezone

from rest_framework import serializers

from apps.users.models import User

from apps.event_planner.utils import validate_image_size



# ── Profile ───────────────────────────────────────────────────────────────────


class UserProfileSerializer(serializers.ModelSerializer):

    brand_slug = serializers.SerializerMethodField()

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
            "profile_image_url",
        ]



    def get_brand_slug(self, obj):

        if obj.role != "seller":

            return None


        from apps.event_planner.models import EventBrand


        return (
            EventBrand.objects
            .filter(
                seller=obj
            )
            .values_list(
                "slug",
                flat=True,
            )
            .first()
        )



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





# ── Update Profile ────────────────────────────────────────────────────────────


class UpdateProfileSerializer(serializers.ModelSerializer):


    class Meta:

        model = User


        fields = [

            "full_name",

            "username",

            "bio",

            "profile_image",

            "contact_number",

            "whatsapp_number",

        ]



    def validate_profile_image(self, value):

        if value:

            validate_image_size(value)


        return value



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
                "Only lowercase letters, numbers, and hyphens are allowed."
            )



        if value != user.username:



            if user.username_last_changed:


                days = (
                    timezone.now()
                    -
                    user.username_last_changed
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
                .filter(
                    username=value
                )
                .exclude(
                    pk=user.pk
                )
                .exists()
            ):

                raise serializers.ValidationError(
                    "Username already taken."
                )



        return value