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
)
from apps.users.throttles import (
    LoginRateThrottle, OtpRateThrottle, PasswordResetRateThrottle,
)
from apps.users.utils import get_tokens_for_user


# ── Register ───────────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    serializer_class   = RegisterSerializer
    permission_classes = [AllowAny]
    # Inherits default AnonRateThrottle (20/hour) from REST_FRAMEWORK settings.


# ── Verify OTP ─────────────────────────────────────────────────────────────────

class VerifyOtpView(generics.GenericAPIView):
    serializer_class   = VerifyOtpSerializer
    permission_classes = [AllowAny]
    throttle_classes   = [OtpRateThrottle]          # CRITICAL FIX #3 — 10/hour

    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(s.validated_data)


# ── Login ──────────────────────────────────────────────────────────────────────

class LoginView(generics.GenericAPIView):
    serializer_class   = LoginSerializer
    permission_classes = [AllowAny]
    throttle_classes   = [LoginRateThrottle]        # CRITICAL FIX #3 — 5/minute

    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)

        user   = s.validated_data["user"]
        tokens = get_tokens_for_user(user)          # embeds token_version

        return Response({
            **tokens,
            "user": UserProfileSerializer(user).data,
        })


# ── Profile ────────────────────────────────────────────────────────────────────

class ProfileView(generics.RetrieveAPIView):
    serializer_class = UserProfileSerializer
    lookup_field     = "slug"
    queryset         = User.objects.all()
    permission_classes = [AllowAny]                 # public profiles are readable


class UpdateProfileView(generics.UpdateAPIView):
    serializer_class   = UpdateProfileSerializer
    permission_classes = [IsAuthenticated]
    lookup_field       = "slug"

    def get_queryset(self):
        # WARNING FIX — users can only update their own profile
        return User.objects.filter(pk=self.request.user.pk)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        response = super().update(request, *args, **kwargs)
        updated_user = User.objects.get(pk=instance.pk)
        return Response({
            "message":  "Profile updated successfully",
            "user":     UserProfileSerializer(updated_user).data,
            "new_slug": updated_user.slug,
        })


# ── Forgot & Reset Password ────────────────────────────────────────────────────

class ForgotPasswordView(generics.GenericAPIView):
    serializer_class   = ForgotPasswordSerializer
    permission_classes = [AllowAny]
    throttle_classes   = [PasswordResetRateThrottle]   # CRITICAL FIX #3 — 5/hour

    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(s.validated_data)


class ResetPasswordView(generics.GenericAPIView):
    serializer_class   = ResetPasswordSerializer
    permission_classes = [AllowAny]
    throttle_classes   = [PasswordResetRateThrottle]   # CRITICAL FIX #3 — 5/hour

    def post(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(s.validated_data)


# ── Logout ─────────────────────────────────────────────────────────────────────

class LogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Logout from this device — blacklists the refresh token."""
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
        """Logout from ALL devices — increments token_version, invalidating all JWTs."""
        request.user.token_version += 1
        request.user.save(update_fields=["token_version"])
        return Response({"message": "Logged out from all devices."})