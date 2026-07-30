import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from rest_framework_simplejwt.tokens import RefreshToken


def generate_otp() -> str:
    """
    Generate a cryptographically secure six-digit OTP.

    Possible range:
    100000–999999
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
            return (
                True,
                "OTP email sent successfully.",
            )

        return (
            False,
            "OTP email was not sent.",
        )

    except Exception as error:
        return (
            False,
            str(error),
        )


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    refresh["token_version"] = user.token_version

    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }