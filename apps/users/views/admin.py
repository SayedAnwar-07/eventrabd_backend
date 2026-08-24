from django.db.models import Q

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


from apps.users.models import User

from apps.users.permissions import IsAdminUserOnly

from apps.users.serializers import (
    AdminProfileSerializer,
    AdminUserListSerializer,
)



# ─────────────────────────────────────────────
# Admin Profile
# ─────────────────────────────────────────────


class AdminProfileView(generics.RetrieveAPIView):

    serializer_class = AdminProfileSerializer

    permission_classes = [
        IsAuthenticated,
        IsAdminUserOnly,
    ]


    def get_object(self):

        return self.request.user





# ─────────────────────────────────────────────
# Admin Seller List
# ─────────────────────────────────────────────


class AdminSellerListView(generics.ListAPIView):

    serializer_class = AdminUserListSerializer

    permission_classes = [
        IsAuthenticated,
        IsAdminUserOnly,
    ]


    def get_queryset(self):

        return (
            User.objects
            .filter(
                role="seller"
            )
            .order_by(
                "-created_at"
            )
        )





# ─────────────────────────────────────────────
# Admin Customer List
# ─────────────────────────────────────────────


class AdminCustomerListView(generics.ListAPIView):

    serializer_class = AdminUserListSerializer

    permission_classes = [
        IsAuthenticated,
        IsAdminUserOnly,
    ]


    def get_queryset(self):

        return (
            User.objects
            .filter(
                role="customer"
            )
            .order_by(
                "-created_at"
            )
        )





# ─────────────────────────────────────────────
# Admin Delete User
# ─────────────────────────────────────────────


class AdminUserDeleteView(generics.DestroyAPIView):

    permission_classes = [
        IsAuthenticated,
        IsAdminUserOnly,
    ]


    lookup_field = "id"


    queryset = User.objects.all()



    def destroy(
        self,
        request,
        *args,
        **kwargs,
    ):

        user = self.get_object()



        # Prevent deleting another admin

        if user.is_staff:

            return Response(

                {
                    "detail":
                    "Admin users cannot be deleted."
                },

                status=status.HTTP_403_FORBIDDEN,

            )



        user.delete()



        return Response(

            {
                "message":
                "User deleted successfully."
            },

            status=status.HTTP_200_OK,

        )