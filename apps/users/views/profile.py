from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
)
from rest_framework.response import Response


from apps.event_planner.models import EventBrand

from apps.users.models import User

from apps.users.serializers import (
    UpdateProfileSerializer,
    UserProfileSerializer,
)



# ── Current User Profile ──────────────────────────────────────────────────────


class MyProfileView(generics.RetrieveAPIView):

    serializer_class = UserProfileSerializer

    permission_classes = [
        IsAuthenticated
    ]


    def get_object(self):

        return self.request.user





# ── Public Profile Redirect ───────────────────────────────────────────────────


class ProfileView(generics.GenericAPIView):

    permission_classes = [
        AllowAny
    ]

    authentication_classes = []



    def get(self, request, slug):

        target_user = get_object_or_404(

            User.objects.only(
                "id",
                "slug",
                "role",
            ),

            slug=slug,

        )



        brand = None


        if target_user.role == "seller":

            brand = (

                EventBrand.objects

                .filter(
                    seller=target_user
                )

                .only(
                    "slug"
                )

                .first()

            )



        if not brand:

            return Response(

                {
                    "detail":
                    "This page is not available."
                },

                status=status.HTTP_404_NOT_FOUND,

            )



        return Response(

            {
                "redirect_url":
                f"/event-planner/brands/{brand.slug}/"
            },

            status=status.HTTP_200_OK,

        )







# ── Update Profile ────────────────────────────────────────────────────────────


class UpdateProfileView(generics.UpdateAPIView):

    serializer_class = UpdateProfileSerializer

    permission_classes = [
        IsAuthenticated
    ]


    lookup_field = "slug"



    def get_queryset(self):

        return User.objects.filter(

            pk=self.request.user.pk

        )



    def update(
        self,
        request,
        *args,
        **kwargs,
    ):

        instance = self.get_object()



        super().update(

            request,

            *args,

            **kwargs,

        )



        updated_user = User.objects.get(

            pk=instance.pk

        )



        return Response(

            {
                "message":
                "Profile updated successfully",


                "user":
                UserProfileSerializer(
                    updated_user
                ).data,


                "new_slug":
                updated_user.slug,

            }

        )