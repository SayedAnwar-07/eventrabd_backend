import random
import string
from django.db.models.functions import Lower
from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone
from django.db import transaction
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from rest_framework import status,permissions
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import timedelta
from django.utils.text import slugify
from .models import User
from apps.events.models import Event
from .serializers import (
    UserRegisterSerializer,
    UserLoginSerializer,
    UserSerializer,
    UserUpdateSerializer,
    OTPVerifySerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    text_fallback_from_html,
    SellerUserEventDashboardSerializer,
)
import logging
logger = logging.getLogger(__name__)

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

def send_templated_email(*, subject: str, to_email: str, html_template: str, text_template: str, ctx: dict):
    """
    Send a multipart/alternative email using an HTML template and a text fallback.
    """
    html_content = render_to_string(html_template, ctx)
    text_content = text_fallback_from_html(html_content, text_template, ctx)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,                    
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    msg.attach_alternative(html_content, "text/html") 
    msg.send()


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = UserRegisterSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            # flatten errors
            errors = {
                field: (errs[0] if isinstance(errs, list) and errs else str(errs))
                for field, errs in serializer.errors.items()
            }
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = serializer.save()

            # generate & store OTP
            otp = generate_otp()
            user.otp = otp
            user.otp_expiry = timezone.now() + timedelta(minutes=10)  # <- fixed
            user.save(update_fields=["otp", "otp_expiry"])

            # send HTML + text email using your template
            try:
                ctx = {
                    "site_name": getattr(settings, "SITE_NAME", "Our Site"),
                    "user": user,
                    "otp": otp,
                }
                send_templated_email(
                    subject="Verify your email",
                    to_email=user.email,
                    html_template="email/otp_email.html",
                    text_template="email/otp_email.txt",  # optional: if missing, helper strips HTML
                    ctx=ctx,
                )
            except Exception as e:
                logger.error(f"Failed to send verification email to {user.email}: {e}")

            return Response(
                {
                    'message': 'User registered successfully. Please verify your email.',
                    'user': UserSerializer(user, context={'request': request}).data
                },
                status=status.HTTP_201_CREATED
            )

        except Exception:
            logger.exception("Registration error")
            return Response(
                {"errors": {"non_field_errors": ["An unexpected error occurred during registration."]}},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        user = authenticate(email=email, password=password)

        if not user or not user.is_active:
            # Do not hint whether the email exists
            return Response({'error': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_verified:
            return Response(
                {'error': 'Account not verified. Please verify your email.'},
                status=status.HTTP_403_FORBIDDEN
            )

        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)


class VerifyOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {'errors': {'email': 'No account found with this email. Please sign up again.'}},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user is already verified
        if user.is_verified:
            return Response(
                {'errors': {'email': 'This email is already verified.'}},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Handle missing/expired/incorrect OTP cases
        now = timezone.now()
        
        # Check if OTP exists
        if not user.otp:
            return Response(
                {'errors': {'otp': 'No active OTP found. Please request a new one.'}},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if OTP is expired
        if user.otp_expiry and user.otp_expiry <= now:
            return Response(
                {'errors': {'otp_expiry': 'OTP has expired. Please request a new one.'}},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if OTP matches
        if user.otp != otp:
            return Response(
                {'errors': {'otp': 'Invalid OTP. Please check the code sent to your email.'}},
                status=status.HTTP_400_BAD_REQUEST
            )
        user.is_verified = True
        user.otp = None
        user.otp_expiry = None
        user.save(update_fields=["is_verified", "otp", "otp_expiry"])

        return Response({
            'message': 'Email verified successfully',
            'user': UserSerializer(user, context={'request': request}).data
        }, status=status.HTTP_200_OK)


class ResendOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Don’t leak existence
            return Response({'message': 'If the email exists, an OTP has been sent.'},
                            status=status.HTTP_200_OK)

        if getattr(user, "is_verified", False):
            return Response({'error': 'Account is already verified.'}, status=status.HTTP_400_BAD_REQUEST)

        otp = generate_otp()
        user.otp = otp
        user.otp_expiry = timezone.now() + timedelta(minutes=10) 
        user.save(update_fields=["otp", "otp_expiry"])

        try:
            ctx = {
                "site_name": getattr(settings, "SITE_NAME", "Our Site"),
                "user": user,
                "otp": otp,
            }
            send_templated_email(
                subject="Verify your email",
                to_email=user.email,
                html_template="email/otp_email.html",
                text_template="email/otp_email.txt",
                ctx=ctx,
            )
        except Exception as e:
            logger.error(f"Failed to resend OTP to {user.email}: {e}")
            # Keep response generic to the client
            return Response({'message': 'If the email exists, an OTP has been sent.'},
                            status=status.HTTP_200_OK)

        return Response({'message': 'OTP resent successfully.'}, status=status.HTTP_200_OK)

class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        generic_message = {'message': 'If the email exists, an OTP has been sent.'}

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(generic_message, status=status.HTTP_200_OK)

        otp = generate_otp()
        user.otp = otp
        user.otp_expiry = timezone.now() + timedelta(minutes=10)
        user.save(update_fields=["otp", "otp_expiry"])

        try:
            frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:3000")
            ctx = {
                "site_name": getattr(settings, "SITE_NAME", "Eventra BD"),
                "user": user,
                "otp": otp,
                "reset_url": f"{frontend_base}/reset-password?email={email}&otp={otp}",
            }
            
            send_templated_email(
                subject=f"Password Reset - {getattr(settings, 'SITE_NAME', 'Eventra BD')}",
                to_email=user.email,
                html_template="email/password_reset_email.html",
                text_template="email/password_reset_email.txt",
                ctx=ctx,  
            )
        except Exception as e:
            logger.error(f"Failed to send reset email: {e}")

        return Response(generic_message, status=status.HTTP_200_OK)

class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']
        password = serializer.validated_data['password']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid email or OTP.'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        if not user.otp or not user.otp_expiry:
            return Response({'error': 'No active OTP. Please request a new one.'},
                            status=status.HTTP_400_BAD_REQUEST)

        if user.otp_expiry <= now:
            return Response({'error': 'OTP has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        if user.otp != otp:
            return Response({'error': 'Invalid OTP.'}, status=status.HTTP_400_BAD_REQUEST)

        # All good: reset password and clear OTP
        user.set_password(password)
        user.otp = None
        user.otp_expiry = None
        user.save(update_fields=["password", "otp", "otp_expiry"])

        return Response({'message': 'Password reset successfully.'}, status=status.HTTP_200_OK)

class GetProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [AllowAny()]
        return super().get_permissions()

    def _get_user_by_slug(self, slug: str):
        slug = slug.lower()
        parts = slug.split('-')
        if len(parts) < 2:
            return None, Response({"error": "Invalid profile URL format"}, status=status.HTTP_400_BAD_REQUEST)

        qs = User.objects.annotate(
            first_name_slug=Lower("first_name"),
            last_name_slug=Lower("last_name")
        ).filter(
            first_name_slug=parts[0],
            last_name_slug=parts[1]
        )

        if not qs.exists():
            return None, Response({"error": "Profile not found"}, status=status.HTTP_404_NOT_FOUND)

        return qs, None

    def get(self, request, slug):
        qs, err = self._get_user_by_slug(slug)
        if err:
            return err
        user = qs.first()
        data = UserSerializer(user, context={"request": request}).data
        return Response(data, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request, slug):
        """
        Increments lifetime + today's WhatsApp click counters.
        Call this when the UI WhatsApp button is clicked.
        """
        qs, err = self._get_user_by_slug(slug)
        if err:
            return err

        user = qs.select_for_update().first()

        user.bump_whatsapp_clicks()
        user.save(update_fields=[
            "whatsapp_click_count",
            "whatsapp_daily_click_count",
            "whatsapp_daily_click_date",
        ])

        return Response({
            "message": "WhatsApp click counted.",
            "whatsapp_click_count": user.whatsapp_click_count,
            "whatsapp_daily_click_count": user.whatsapp_daily_click_count,
            "whatsapp_daily_click_date": user.whatsapp_daily_click_date,
        }, status=status.HTTP_200_OK)


class UpdateProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, slug):
        try:
            # Get the user by ID from the authenticated user
            user = request.user
            
            # Verify the slug matches the current user's expected slug
            expected_slug = f"{slugify(user.first_name)}-{slugify(user.last_name)}"
            
            if slug != expected_slug:
                return Response(
                    {"error": "Profile not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            serializer = UserUpdateSerializer(user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()

                # Regenerate the slug after update
                updated_slug = f"{slugify(user.first_name)}-{slugify(user.last_name)}"
                
                data = UserSerializer(user, context={"request": request}).data
                data["profile_url"] = request.build_absolute_uri(
                    f"/users/profile/{updated_slug}/"
                )

                return Response(
                    {"message": "Profile updated successfully", "user": data},
                    status=status.HTTP_200_OK
                )

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except User.DoesNotExist:
            return Response(
                {"error": "Profile not found"},
                status=status.HTTP_404_NOT_FOUND
            )

    patch = put


class SellerUserEventDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, slug, *args, **kwargs):
        first, last = slug.split("-", 1) if "-" in slug else (slug, "")
        seller = get_object_or_404(User, first_name__iexact=first, last_name__iexact=last, user_type="seller")

        # get all events of seller
        events = Event.objects.filter(seller=seller)
        payload = SellerUserEventDashboardSerializer(events, many=True).data
        return Response(payload, status=status.HTTP_200_OK)
