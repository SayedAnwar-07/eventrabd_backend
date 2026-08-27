from django.conf import settings
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken


from apps.users.models import User

from apps.users.permissions import IsAdminUserOnly

from apps.users.serializers import (
    AdminLoginSerializer,
    AdminProfileSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserProfileSerializer,
    VerifyOtpSerializer,
    AdminForgotPasswordSerializer,
    AdminResetPasswordSerializer
)

from apps.users.throttles import (
    LoginRateThrottle,
    OtpRateThrottle,
    PasswordResetRateThrottle,
)

from apps.users.utils import get_tokens_for_user



# ─────────────────────────────────────────────
# Cookie Helpers
# ─────────────────────────────────────────────


def set_refresh_cookie(
    response,
    refresh_token,
    cookie_name,
):

    response.set_cookie(

        key=cookie_name,

        value=refresh_token,

        max_age=settings.REFRESH_TOKEN_COOKIE_MAX_AGE,

        path=settings.REFRESH_TOKEN_COOKIE_PATH,

        domain=settings.REFRESH_TOKEN_COOKIE_DOMAIN,

        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,

        httponly=settings.REFRESH_TOKEN_COOKIE_HTTPONLY,

        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,

    )



def delete_refresh_cookie(
    response,
    cookie_name,
):
    response.delete_cookie(
        key=cookie_name,
        path=settings.REFRESH_TOKEN_COOKIE_PATH,
        domain=settings.REFRESH_TOKEN_COOKIE_DOMAIN,
        # secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
    )



def prevent_token_cache(response):

    response["Cache-Control"] = "no-store"

    response["Pragma"] = "no-cache"

    return response



def invalid_refresh_response(cookie_name):

    response = Response(

        {
            "detail":
            "Refresh session is invalid or expired. Please log in again."
        },

        status=status.HTTP_401_UNAUTHORIZED,

    )


    delete_refresh_cookie(
        response,
        cookie_name,
    )


    return prevent_token_cache(response)





# ─────────────────────────────────────────────
# CSRF
# ─────────────────────────────────────────────


@method_decorator(
    ensure_csrf_cookie,
    name="dispatch",
)
class CsrfTokenView(generics.GenericAPIView):

    permission_classes = [
        AllowAny
    ]

    authentication_classes = []


    def get(self, request):

        response = Response(

            {
                "csrfToken":
                get_token(request._request)
            }

        )


        return prevent_token_cache(response)





# ─────────────────────────────────────────────
# Register
# ─────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):

    serializer_class = RegisterSerializer

    permission_classes = [
        AllowAny
    ]

    authentication_classes = []



# ─────────────────────────────────────────────
# Verify OTP
# ─────────────────────────────────────────────

class VerifyOtpView(generics.GenericAPIView):

    serializer_class = VerifyOtpSerializer

    permission_classes = [
        AllowAny
    ]

    authentication_classes = []

    throttle_classes = [
        OtpRateThrottle
    ]



    def post(self, request):

        serializer = self.get_serializer(
            data=request.data
        )


        serializer.is_valid(
            raise_exception=True
        )


        user = serializer.validated_data["user"]


        tokens = get_tokens_for_user(user)



        response = Response(

            {
                "message":
                "Account verified successfully.",


                "access":
                tokens["access"],


                "user":
                UserProfileSerializer(user).data,

            },

            status=status.HTTP_200_OK,

        )


        set_refresh_cookie(
            response,
            tokens["refresh"],
            settings.CLIENT_REFRESH_TOKEN_COOKIE_NAME,
        )


        return prevent_token_cache(response)



# ─────────────────────────────────────────────
# Normal Login
# ─────────────────────────────────────────────

class LoginView(generics.GenericAPIView):

    serializer_class = LoginSerializer

    permission_classes = [
        AllowAny
    ]

    authentication_classes = []

    throttle_classes = [
        LoginRateThrottle
    ]



    def post(self, request):

        serializer = self.get_serializer(
            data=request.data
        )


        serializer.is_valid(
            raise_exception=True
        )


        user = serializer.validated_data["user"]



        if user.is_staff:

            return Response(

                {
                    "detail":
                    "Please use admin login."
                },

                status=status.HTTP_403_FORBIDDEN,

            )



        tokens = get_tokens_for_user(user)



        response = Response(

            {
                "access":
                tokens["access"],


                "user":
                UserProfileSerializer(user).data,

            },

            status=status.HTTP_200_OK,

        )



        set_refresh_cookie(

            response,

            tokens["refresh"],

            settings.CLIENT_REFRESH_TOKEN_COOKIE_NAME,

        )


        return prevent_token_cache(response)



# ─────────────────────────────────────────────
# Admin Login
# ─────────────────────────────────────────────

class AdminLoginView(generics.GenericAPIView):

    serializer_class = AdminLoginSerializer

    permission_classes = [
        AllowAny
    ]

    authentication_classes = []

    throttle_classes = [
        LoginRateThrottle
    ]



    def post(self, request):

        serializer = self.get_serializer(
            data=request.data
        )


        serializer.is_valid(
            raise_exception=True
        )


        user = serializer.validated_data["user"]


        tokens = get_tokens_for_user(user)



        response = Response(

            {
                "access":
                tokens["access"],


                "user":
                AdminProfileSerializer(user).data,

            },

            status=status.HTTP_200_OK,

        )



        set_refresh_cookie(

            response,

            tokens["refresh"],

            settings.ADMIN_REFRESH_TOKEN_COOKIE_NAME,

        )


        return prevent_token_cache(response)



# ─────────────────────────────────────────────
# Refresh Token
# ─────────────────────────────────────────────

class ClientTokenRefreshView(generics.GenericAPIView):

    permission_classes = [
        AllowAny
    ]

    authentication_classes = []


    def post(self, request):

        refresh_token = request.COOKIES.get(
            settings.CLIENT_REFRESH_TOKEN_COOKIE_NAME
        )


        if not refresh_token:

            return invalid_refresh_response(
                settings.CLIENT_REFRESH_TOKEN_COOKIE_NAME
            )


        try:

            serializer = TokenRefreshSerializer(
                data={
                    "refresh": refresh_token
                }
            )


            serializer.is_valid(
                raise_exception=True
            )


            response = Response(
                {
                    "access":
                    serializer.validated_data["access"]
                },
                status=status.HTTP_200_OK,
            )


            if "refresh" in serializer.validated_data:

                set_refresh_cookie(
                    response,
                    serializer.validated_data["refresh"],
                    settings.CLIENT_REFRESH_TOKEN_COOKIE_NAME,
                )


            return prevent_token_cache(response)


        except TokenError:

            return invalid_refresh_response(
                settings.CLIENT_REFRESH_TOKEN_COOKIE_NAME
            )


class AdminTokenRefreshView(generics.GenericAPIView):

    permission_classes = [
        AllowAny
    ]

    authentication_classes = []


    def post(self, request):

        refresh_token = request.COOKIES.get(
            settings.ADMIN_REFRESH_TOKEN_COOKIE_NAME
        )


        if not refresh_token:

            return invalid_refresh_response(
                settings.ADMIN_REFRESH_TOKEN_COOKIE_NAME
            )


        try:

            serializer = TokenRefreshSerializer(
                data={
                    "refresh": refresh_token
                }
            )


            serializer.is_valid(
                raise_exception=True
            )


            response = Response(
                {
                    "access":
                    serializer.validated_data["access"]
                },
                status=status.HTTP_200_OK,
            )


            if "refresh" in serializer.validated_data:

                set_refresh_cookie(
                    response,
                    serializer.validated_data["refresh"],
                    settings.ADMIN_REFRESH_TOKEN_COOKIE_NAME,
                )


            return prevent_token_cache(response)


        except TokenError:

            return invalid_refresh_response(
                settings.ADMIN_REFRESH_TOKEN_COOKIE_NAME
            )



# ─────────────────────────────────────────────
# Forgot Password
# ─────────────────────────────────────────────

class ForgotPasswordView(generics.GenericAPIView):

    serializer_class = ForgotPasswordSerializer

    permission_classes = [
        AllowAny
    ]

    authentication_classes = []

    throttle_classes = [
        PasswordResetRateThrottle
    ]



    def post(self, request):

        serializer = self.get_serializer(

            data=request.data

        )


        serializer.is_valid(

            raise_exception=True

        )


        return Response(

            serializer.validated_data,

            status=status.HTTP_200_OK,

        )



# ─────────────────────────────────────────────
# Reset Password
# ─────────────────────────────────────────────


class ResetPasswordView(generics.GenericAPIView):

    serializer_class = ResetPasswordSerializer

    permission_classes = [
        AllowAny
    ]

    authentication_classes = []

    throttle_classes = [
        PasswordResetRateThrottle
    ]



    def post(self, request):

        serializer = self.get_serializer(

            data=request.data

        )


        serializer.is_valid(

            raise_exception=True

        )


        return Response(

            serializer.validated_data,

            status=status.HTTP_200_OK,

        )



# ─────────────────────────────────────────────
# Logout Current Device
# ─────────────────────────────────────────────

class LogoutView(generics.GenericAPIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request):

        refresh_token = request.COOKIES.get(
            settings.CLIENT_REFRESH_TOKEN_COOKIE_NAME
        )

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()

            except TokenError:
                pass


        response = Response(
            {
                "message":
                "Logged out successfully."
            },
            status=status.HTTP_200_OK,
        )


        delete_refresh_cookie(
            response,
            settings.CLIENT_REFRESH_TOKEN_COOKIE_NAME,
        )


        return prevent_token_cache(response)
    
class AdminLogoutView(generics.GenericAPIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request):

        refresh_token = request.COOKIES.get(
            settings.ADMIN_REFRESH_TOKEN_COOKIE_NAME
        )

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()

            except TokenError:
                pass


        response = Response(
            {
                "message":
                "Admin logout successfully."
            },
            status=status.HTTP_200_OK,
        )


        delete_refresh_cookie(
            response,
            settings.ADMIN_REFRESH_TOKEN_COOKIE_NAME,
        )


        return prevent_token_cache(response)



# ─────────────────────────────────────────────
# Logout All Devices
# ─────────────────────────────────────────────

class LogoutAllView(generics.GenericAPIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request):

        User.objects.filter(
            id=request.user.id
        ).update(
            token_version=request.user.token_version + 1
        )


        response = Response(
            {
                "message":
                "Logged out from all devices."
            },
            status=status.HTTP_200_OK,
        )


        delete_refresh_cookie(
            response,
            settings.CLIENT_REFRESH_TOKEN_COOKIE_NAME,
        )


        return prevent_token_cache(response)
    

class AdminLogoutAllView(generics.GenericAPIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request):

        User.objects.filter(
            id=request.user.id
        ).update(
            token_version=request.user.token_version + 1
        )


        response = Response(
            {
                "message":
                "Admin logged out from all devices."
            },
            status=status.HTTP_200_OK,
        )


        delete_refresh_cookie(
            response,
            settings.ADMIN_REFRESH_TOKEN_COOKIE_NAME,
        )


        return prevent_token_cache(response)
    
    
class AdminForgotPasswordView(generics.GenericAPIView):

    serializer_class = AdminForgotPasswordSerializer

    permission_classes=[
        AllowAny
    ]

    throttle_classes=[
        PasswordResetRateThrottle
    ]


    def post(self,request):

        serializer=self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        return Response(
            serializer.validated_data
        )


class AdminResetPasswordView(generics.GenericAPIView):

    serializer_class = AdminResetPasswordSerializer

    permission_classes=[
        AllowAny
    ]

    throttle_classes=[
        PasswordResetRateThrottle
    ]


    def post(self,request):

        serializer=self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )


        return Response(
            serializer.validated_data
        )