from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.text import slugify
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string, get_template
from django.template import TemplateDoesNotExist
from django.utils.html import strip_tags
from django.conf import settings
import logging
from apps.events.models import Event
from django.utils import timezone
from apps.reviews.models import Review

User = get_user_model()
logger = logging.getLogger(__name__)
    
    
class SellerEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'slug', 'logo', 'brand_name', 
            'total_views', 'total_reviews', 'average_rating',
            'daily_views', 'daily_reviews', 'daily_ratings',
        ]

# ---------- helpers ----------

def template_exists(name: str) -> bool:
    """Return True if a Django template exists at the given path."""
    try:
        get_template(name)
        return True
    except TemplateDoesNotExist:
        return False


def text_fallback_from_html(html_content: str, txt_template_path: str, ctx: dict) -> str:
    """
    If a .txt template exists, render and return it.
    Otherwise, strip tags from the HTML as a reasonable plaintext fallback.
    """
    if template_exists(txt_template_path):
        return render_to_string(txt_template_path, ctx)
    return strip_tags(html_content)


# ---------- serializers ----------
class UserRegisterSerializer(serializers.ModelSerializer):
    confirm_password = serializers.CharField(style={'input_type': 'password'}, write_only=True)
    password = serializers.CharField(style={'input_type': 'password'}, write_only=True,
                                     validators=[validate_password])

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "profile_image","location",
            "phone_number", "whatsapp_number", "user_type",
            "accepted_terms", "password", "confirm_password",
            "whatsapp_click_count", "whatsapp_daily_click_count",
        ]
        extra_kwargs = {
            "accepted_terms": {
                "required": True,
                "error_messages": {"required": "You must accept the terms."}
            },
            "first_name": {
                "required": True,
                "error_messages": {"required": "First name is required.", "blank": "First name may not be blank."}
            },
            "last_name": {
                "required": True,
                "error_messages": {"required": "Last name is required.", "blank": "Last name may not be blank."}
            },
            "phone_number": {
                "required": True,
                "error_messages": {"required": "Phone number is required.", "blank": "Phone number may not be blank."}
            },
            "email": {"required": True},
        }

    def get_profile_url(self, obj):
        request = self.context.get("request")
        slug = f"{slugify(obj.first_name)}-{slugify(obj.last_name)}"
        path = f"/users/profile/{slug}/"
        return request.build_absolute_uri(path) if request else path

    def validate(self, data):
        errors = {}
        
        if data["password"] != data["confirm_password"]:
            errors["password"] = "Passwords must match."
            errors["confirm_password"] = "Passwords doesn't match."
            
        if User.objects.filter(email=data["email"]).exists():
            errors["email"] = "A user with this email already exists."
            
        if errors:
            raise serializers.ValidationError(errors)
            
        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user



class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    slug = serializers.SerializerMethodField()
    seller_created_events = serializers.SerializerMethodField()  

    class Meta:
        model = User
        fields = [
            "id", "slug", "email", "first_name", "last_name", "full_name","accepted_terms",
            "profile_image","location", "phone_number", "whatsapp_number",
            "user_type", "is_verified","seller_created_events","whatsapp_click_count", "whatsapp_daily_click_count",
            "created_at", "updated_at"
        ]
        read_only_fields = [
            "id", "email", "is_verified", "created_at",
            "updated_at", "full_name", "slug","accepted_terms",
            "whatsapp_click_count", "whatsapp_daily_click_count",
        ]

    def get_slug(self, obj):
        return f"{slugify(obj.first_name)}-{slugify(obj.last_name)}"
    
    def get_seller_created_events(self, obj):
        if obj.user_type != 'seller':
            return []
        events = Event.objects.filter(seller=obj, is_active=True)
        return SellerEventSerializer(events, many=True, context=self.context).data




class UserUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            "first_name", "last_name", "profile_image", "location",
            "phone_number", "whatsapp_number", "password", "confirm_password"
        ]

    def validate(self, data):
        if data.get("password") or data.get("confirm_password"):
            if data.get("password") != data.get("confirm_password"):
                raise serializers.ValidationError({"password": "Passwords must match."})
        return data

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        validated_data.pop("confirm_password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance


# ---------- password reset  ----------

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def _base_email_context(self, email):
        user = User.objects.filter(email=email).first()
        return {
            "site_name": getattr(settings, "SITE_NAME", ""),
            "user": user,
        }

    def _build_reset_url(self, email, otp):
        request = self.context.get("request")
        if request:
            path = "/password-reset/confirm/"
            base = request.build_absolute_uri(path)
            sep = "&" if "?" in base else "?"
            return f"{base}{sep}email={email}&otp={otp}"
        return "#"

    def send_reset_email(self, otp):
        """
        Compose and send a multipart/alternative email (text + HTML).
        Do NOT override Content-Type; EmailMultiAlternatives handles this.
        """
        try:
            email = self.validated_data["email"]
            ctx = self._base_email_context(email)
            ctx.update({
                "otp": otp,
                "reset_url": self._build_reset_url(email, otp),
            })

            subject = "Password Reset Request"
            from_email = settings.DEFAULT_FROM_EMAIL
            to_email = [email]

            html_template = "email/password_reset_email.html"
            text_template = "email/password_reset_email.txt"

            html_content = render_to_string(html_template, ctx)
            text_content = text_fallback_from_html(html_content, text_template, ctx)

            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,      
                from_email=from_email,
                to=to_email,
            )
            msg.attach_alternative(html_content, "text/html") 

            msg.send()

            logger.info(f"Password reset email sent to {email} (HTML + text).")
        except Exception as e:
            logger.error(f"Error sending password reset email: {str(e)}")
            raise


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError({"password": "Passwords must match."})
        return data


# ---------- OTP verify ----------

class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

    def send_otp_email(self, otp):
        """
        Compose and send a multipart/alternative email (text + HTML).
        Do NOT override Content-Type; EmailMultiAlternatives handles this.
        """
        try:
            email = self.validated_data["email"]
            user = User.objects.filter(email=email).first()

            ctx = {
                "site_name": getattr(settings, "SITE_NAME", "Our Site"),
                "otp": otp,
                "user": user or {"first_name": ""},
            }

            subject = "Your Verification OTP"
            from_email = settings.DEFAULT_FROM_EMAIL
            to_email = [email]

            html_template = "email/otp_email.html"
            text_template = "email/otp_email.txt"

            html_content = render_to_string(html_template, ctx)
            text_content = text_fallback_from_html(html_content, text_template, ctx)

            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,     
                from_email=from_email,
                to=to_email,
            )
            msg.attach_alternative(html_content, "text/html")  
            msg.send()

            logger.info(f"OTP email sent to {email} (HTML + text).")
        except Exception as e:
            logger.error(f"Error sending OTP email: {str(e)}")
            raise


# --------dashboard-------
class SellerUserEventDashboardSerializer(serializers.Serializer):
    id = serializers.CharField()
    slug = serializers.SlugField()
    brand_name = serializers.CharField()
    title = serializers.CharField()
    logo = serializers.URLField(allow_null=True)

    total_views = serializers.IntegerField()
    today_views = serializers.SerializerMethodField()

    review_stats = serializers.SerializerMethodField()

    def get_today_views(self, obj):
        today_key = timezone.now().date().isoformat()
        return int((obj.daily_views or {}).get(today_key, 0))

    def get_review_stats(self, obj):
        """Use Review model dashboard utilities"""
        return Review.get_dashboard_stats(event_id=obj.id)