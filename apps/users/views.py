from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from apps.users.models import User
from apps.users.serializers import (
    RegisterSerializer, VerifyOtpSerializer, LoginSerializer,
    UserProfileSerializer, UpdateProfileSerializer,
    ForgotPasswordSerializer, ResetPasswordSerializer,
    AdminLoginSerializer, AdminUserListSerializer,
)
from apps.users.throttles import (
    LoginRateThrottle, OtpRateThrottle, PasswordResetRateThrottle,
)
from apps.users.utils import get_tokens_for_user
from apps.users.permissions import IsAdminUserOnly


# ── Register ───────────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


# ── Verify OTP ─────────────────────────────────────────────────────────────────

class VerifyOtpView(generics.GenericAPIView):
    serializer_class = VerifyOtpSerializer
    permission_classes = [AllowAny]
    throttle_classes = [OtpRateThrottle]

    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(s.validated_data)


# ── Normal User Login ──────────────────────────────────────────────────────────

class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)

        user = s.validated_data["user"]

        # normal user login block admin if you want separate panel only
        if user.is_staff:
            return Response(
                {"detail": "Please use admin login."},
                status=status.HTTP_403_FORBIDDEN
            )

        tokens = get_tokens_for_user(user)

        return Response({
            **tokens,
            "user": UserProfileSerializer(user).data,
        })


# ── Separate Admin Login ───────────────────────────────────────────────────────

class AdminLoginView(generics.GenericAPIView):
    serializer_class = AdminLoginSerializer
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)

        user = s.validated_data["user"]
        tokens = get_tokens_for_user(user)

        return Response({
            **tokens,
            "user": UserProfileSerializer(user).data,
        })


# ── Profile ────────────────────────────────────────────────────────────────────

class ProfileView(generics.RetrieveAPIView):
    serializer_class = UserProfileSerializer
    lookup_field = "slug"
    queryset = User.objects.all()
    permission_classes = [AllowAny]


class UpdateProfileView(generics.UpdateAPIView):
    serializer_class = UpdateProfileSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return User.objects.filter(pk=self.request.user.pk)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        super().update(request, *args, **kwargs)
        updated_user = User.objects.get(pk=instance.pk)

        return Response({
            "message": "Profile updated successfully",
            "user": UserProfileSerializer(updated_user).data,
            "new_slug": updated_user.slug,
        })


# ── Admin User Management ──────────────────────────────────────────────────────

class AdminSellerListView(generics.ListAPIView):
    serializer_class = AdminUserListSerializer
    permission_classes = [IsAdminUserOnly]

    def get_queryset(self):
        return User.objects.filter(role="seller").order_by("-created_at")


class AdminCustomerListView(generics.ListAPIView):
    serializer_class = AdminUserListSerializer
    permission_classes = [IsAdminUserOnly]

    def get_queryset(self):
        return User.objects.filter(role="customer").order_by("-created_at")


class AdminUserDeleteView(generics.DestroyAPIView):
    queryset = User.objects.all()
    permission_classes = [IsAdminUserOnly]
    lookup_field = "id"

    def destroy(self, request, *args, **kwargs):
        user_to_delete = self.get_object()

        if request.user == user_to_delete:
            return Response(
                {"detail": "You cannot delete your own admin account."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user_to_delete.delete()
        return Response(
            {"message": "User deleted successfully."},
            status=status.HTTP_200_OK
        )


# ── Forgot & Reset Password ────────────────────────────────────────────────────

class ForgotPasswordView(generics.GenericAPIView):
    serializer_class = ForgotPasswordSerializer
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(s.validated_data)


class ResetPasswordView(generics.GenericAPIView):
    serializer_class = ResetPasswordSerializer
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(s.validated_data)


# ── Logout ─────────────────────────────────────────────────────────────────────

class LogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token required."}, status=400)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response({"detail": "Invalid or already blacklisted token."}, status=400)
        return Response({"message": "Logged out successfully."})


class LogoutAllView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.token_version += 1
        request.user.save(update_fields=["token_version"])
        return Response({"message": "Logged out from all devices."})