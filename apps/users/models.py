from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinLengthValidator
from django.apps import apps
from django.utils.crypto import get_random_string
from .managers import UserManager
from django.utils.text import slugify
from django.utils import timezone

def _generate_unique_id():
    import sys
    if 'makemigrations' in sys.argv or 'migrate' in sys.argv:
        return get_random_string(12)
    
    UserModel = apps.get_model('users', 'User')
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    while True:
        new_id = get_random_string(12, allowed_chars=alphabet)
        if not UserModel._default_manager.filter(pk=new_id).exists():
            return new_id

class User(AbstractUser):
    USER_TYPE_CHOICES = (
        ('customer', 'Customer'),
        ('seller', 'Seller'),
        ('admin', 'Admin'),
    )

    id = models.CharField(
        primary_key=True,
        default=_generate_unique_id,
        editable=False,
        max_length=12,
        validators=[MinLengthValidator(12)]
    )
    username = None

    email = models.EmailField(_('email address'), unique=True, db_index=True)
    first_name = models.CharField(_('first name'), max_length=150)
    last_name = models.CharField(_('last name'), max_length=150)
    profile_image = models.URLField(blank=True, null=True, )
    location = models.CharField(max_length=20, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    whatsapp_number = models.CharField(max_length=20, blank=True, null=True)
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='customer')
    
    is_verified = models.BooleanField(default=False)

    accepted_terms = models.BooleanField(
        default=False,
        verbose_name="I accept the terms and conditions",
        help_text="You must accept our terms and conditions to register"
    )

    # Email OTP verification
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_expiry = models.DateTimeField(blank=True, null=True)

    # Password reset (custom token approach)
    verification_token = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    token_created_at = models.DateTimeField(null=True, blank=True)
    
    # --- WhatsApp click tracking ---
    whatsapp_click_count = models.BigIntegerField(default=0)
    whatsapp_daily_click_count = models.IntegerField(default=0)
    whatsapp_daily_click_date = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def get_profile_slug(self):
        return f"{slugify(self.first_name)}-{slugify(self.last_name)}"

    def bump_whatsapp_clicks(self):
        """
        Safe-increment method for views to use under select_for_update().
        Resets the daily counter if the stored day != today.
        """
        today = timezone.localdate()
        if self.whatsapp_daily_click_date != today:
            self.whatsapp_daily_click_date = today
            self.whatsapp_daily_click_count = 0

        self.whatsapp_click_count += 1
        self.whatsapp_daily_click_count += 1

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
