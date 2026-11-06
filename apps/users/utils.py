import secrets
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from rest_framework_simplejwt.tokens import RefreshToken


logger = logging.getLogger(__name__)


def generate_otp() -> str:
    """
    Generate a cryptographically secure six-digit OTP.
    """
    return str(
        100000 + secrets.randbelow(900000)
    )


def send_otp_email(
    user,
    otp: str,
    template_name: str,
):
    if "forgot" in template_name:
        subject = "Reset Your EventraBD Password"
    else:
        subject = "Verify Your EventraBD Account"

    try:
        html_message = render_to_string(
            template_name,
            {
                "full_name": user.full_name,
                "otp": otp,
            },
        )

        sent_count = send_mail(
            subject=subject,
            message="",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )

        if sent_count == 1:
            logger.info(
                "OTP email sent successfully to %s",
                user.email,
            )

            return (
                True,
                "OTP email sent successfully.",
            )

        logger.error(
            "OTP email was not sent to %s",
            user.email,
        )

        return (
            False,
            "OTP email was not sent.",
        )

    except Exception:
        logger.exception(
            "OTP email sending failed for %s",
            user.email,
        )

        return (
            False,
            "Email delivery failed. Check server logs.",
        )


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    refresh["token_version"] = user.token_version

    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }