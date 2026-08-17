from django.conf import settings
from django.db.models import F
from django.http import HttpResponseRedirect
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie

from rest_framework import generics, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.event_planner.models import EventBrand
from apps.users.models import User
from apps.users.permissions import IsAdminUserOnly
from apps.users.serializers import (
    AdminLoginSerializer,
    AdminProfileSerializer,
    AdminUserListSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UpdateProfileSerializer,
    UserProfileSerializer,
    VerifyOtpSerializer,
)
from apps.users.throttles import (
    LoginRateThrottle,
    OtpRateThrottle,
    PasswordResetRateThrottle,
)
from apps.users.utils import get_tokens_for_user


# ── Cookie helpers ─────────────────────────────────────────────────────────────

def set_refresh_cookie(response, refresh_token):
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_COOKIE_MAX_AGE,
        path=settings.REFRESH_TOKEN_COOKIE_PATH,
        domain=settings.REFRESH_TOKEN_COOKIE_DOMAIN,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
        httponly=settings.REFRESH_TOKEN_COOKIE_HTTPONLY,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
    )


def delete_refresh_cookie(response):
    response.delete_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        path=settings.REFRESH_TOKEN_COOKIE_PATH,
        domain=settings.REFRESH_TOKEN_COOKIE_DOMAIN,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
    )


def prevent_token_cache(response):
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


def invalid_refresh_response():
    response = Response(
        {
            "detail": (
                "Refresh session is invalid or expired. "
                "Please log in again."
            )
        },
        status=status.HTTP_401_UNAUTHORIZED,
    )

    delete_refresh_cookie(response)
    return prevent_token_cache(response)


# ── CSRF token ─────────────────────────────────────────────────────────────────

@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        response = Response(
            {
                "csrfToken": get_token(request._request),
            }
        )

        return prevent_token_cache(response)


# ── Register ───────────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []


# ── Verify OTP ─────────────────────────────────────────────────────────────────

class VerifyOtpView(generics.GenericAPIView):
    serializer_class = VerifyOtpSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [OtpRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]

        tokens = get_tokens_for_user(user)

        response = Response(
            {
                "message": "Account verified successfully.",
                "access": tokens["access"],
                "user": UserProfileSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )

        set_refresh_cookie(response, tokens["refresh"])

        return prevent_token_cache(response)


# ── Normal User Login ──────────────────────────────────────────────────────────

class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]

        if user.is_staff:
            return Response(
                {
                    "detail": "Please use admin login.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        tokens = get_tokens_for_user(user)

        # Refresh token is intentionally not returned in JSON.
        response = Response(
            {
                "access": tokens["access"],
                "user": UserProfileSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )

        set_refresh_cookie(
            response,
            tokens["refresh"],
        )

        return prevent_token_cache(response)


# ── Admin Login ────────────────────────────────────────────────────────────────

class AdminLoginView(generics.GenericAPIView):
    serializer_class = AdminLoginSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        user = serializer.validated_data["user"]

        tokens = get_tokens_for_user(user)

        response = Response(
            {
                "access": tokens["access"],
                "user": AdminProfileSerializer(
                    user
                ).data,
            },
            status=status.HTTP_200_OK,
        )
        set_refresh_cookie(
            response,
            tokens["refresh"],
        )

        return prevent_token_cache(response)


# ── HttpOnly Cookie Token Refresh ──────────────────────────────────────────────

class CookieTokenRefreshView(generics.GenericAPIView):
    serializer_class = TokenRefreshSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token_refresh"

    def post(self, request):
        refresh_token = request.COOKIES.get(
            settings.REFRESH_TOKEN_COOKIE_NAME
        )

        if not refresh_token:
            return invalid_refresh_response()

        try:
            # Validate token signature, expiry and blacklist status.
            parsed_token = RefreshToken(refresh_token)

            user_id = parsed_token.get(
                api_settings.USER_ID_CLAIM
            )

            if user_id is None:
                raise TokenError("Missing user ID.")

            user = (
                User.objects
                .only(
                    api_settings.USER_ID_FIELD,
                    "is_active",
                    "token_version",
                )
                .filter(
                    **{
                        api_settings.USER_ID_FIELD: user_id,
                    }
                )
                .first()
            )

            if not user or not user.is_active:
                raise TokenError("User is unavailable.")

            token_version = parsed_token.get(
                "token_version",
                -1,
            )

            if token_version != user.token_version:
                try:
                    parsed_token.blacklist()
                except AttributeError:
                    pass

                raise TokenError("Session expired.")

            # SimpleJWT performs rotation and old-token blacklisting.
            serializer = self.get_serializer(
                data={
                    "refresh": refresh_token,
                }
            )
            serializer.is_valid(raise_exception=True)

        except (TokenError, APIException):
            return invalid_refresh_response()

        access_token = serializer.validated_data["access"]

        rotated_refresh_token = (
            serializer.validated_data.get("refresh")
            or refresh_token
        )

        response = Response(
            {
                "access": access_token,
            },
            status=status.HTTP_200_OK,
        )

        set_refresh_cookie(
            response,
            rotated_refresh_token,
        )

        return prevent_token_cache(response)


# ── Profile ────────────────────────────────────────────────────────────────────

class MyProfileView(generics.RetrieveAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ProfileView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        target_user = get_object_or_404(
            User.objects.only("id", "slug", "role"),
            slug=slug,
        )

        brand = None
        if target_user.role == "seller":
            brand = (
                EventBrand.objects
                .filter(seller=target_user)
                .only("slug")
                .first()
            )

        if not brand:
            return Response(
                {"detail": "This page is not available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"redirect_url": f"/event-planner/brands/{brand.slug}/"},
            status=status.HTTP_200_OK,
        )


class UpdateProfileView(generics.UpdateAPIView):
    serializer_class = UpdateProfileSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return User.objects.filter(
            pk=self.request.user.pk
        )

    def update(self, request, *args, **kwargs):
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
                "message": (
                    "Profile updated successfully"
                ),
                "user": UserProfileSerializer(
                    updated_user
                ).data,
                "new_slug": updated_user.slug,
            }
        )


# ── Admin User Management ──────────────────────────────────────────────────────

class AdminSellerListView(generics.ListAPIView):
    serializer_class = AdminUserListSerializer
    permission_classes = [IsAdminUserOnly]

    def get_queryset(self):
        return (
            User.objects
            .filter(role="seller")
            .order_by("-created_at")
        )


class AdminCustomerListView(generics.ListAPIView):
    serializer_class = AdminUserListSerializer
    permission_classes = [IsAdminUserOnly]

    def get_queryset(self):
        return (
            User.objects
            .filter(role="customer")
            .order_by("-created_at")
        )


class AdminUserDeleteView(generics.DestroyAPIView):
    queryset = User.objects.all()
    permission_classes = [IsAdminUserOnly]
    lookup_field = "id"

    def destroy(self, request, *args, **kwargs):
        user_to_delete = self.get_object()

        if request.user == user_to_delete:
            return Response(
                {
                    "detail": (
                        "You cannot delete your "
                        "own admin account."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_to_delete.delete()

        return Response(
            {
                "message": (
                    "User deleted successfully."
                ),
            },
            status=status.HTTP_200_OK,
        )


# ── Forgot & Reset Password ────────────────────────────────────────────────────

class ForgotPasswordView(generics.GenericAPIView):
    serializer_class = ForgotPasswordSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        return Response(serializer.validated_data)


class ResetPasswordView(generics.GenericAPIView):
    serializer_class = ResetPasswordSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        return Response(serializer.validated_data)


# ── Logout Current Device ──────────────────────────────────────────────────────

class LogoutView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        refresh_token = request.COOKIES.get(
            settings.REFRESH_TOKEN_COOKIE_NAME
        )

        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except TokenError:
                pass

        response = Response(
            {
                "message": "Logged out successfully.",
            },
            status=status.HTTP_200_OK,
        )

        delete_refresh_cookie(response)

        return prevent_token_cache(response)


# ── Logout All Devices ─────────────────────────────────────────────────────────

class LogoutAllView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.COOKIES.get(
            settings.REFRESH_TOKEN_COOKIE_NAME
        )

        if refresh_token:
            try:
                RefreshToken(refresh_token).blacklist()
            except TokenError:
                pass

        User.objects.filter(
            pk=request.user.pk
        ).update(
            token_version=F("token_version") + 1
        )

        response = Response(
            {
                "message": (
                    "Logged out from all devices."
                )
            },
            status=status.HTTP_200_OK,
        )

        delete_refresh_cookie(response)

        return prevent_token_cache(response)