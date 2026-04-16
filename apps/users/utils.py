import random
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(user, otp, template_name):
    # Email subject based on action
    if "forgot" in template_name:
        subject = "Reset Your EventraBD Password"
    else:
        subject = "Verify Your EventraBD Account"

    # Render HTML email
    html_message = render_to_string(template_name, {
        "full_name": user.full_name,
        "otp": otp,
    })

    # Send email
    send_mail(
        subject,
        "", 
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html_message,
    )

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    refresh['token_version'] = user.token_version
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
