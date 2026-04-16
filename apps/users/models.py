from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import TimeStampedModel, UIDMixin


class UserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", "admin")

        if not password:
            raise ValueError("Superuser must have a password")

        return self.create_user(email, password, **extra)


class User(UIDMixin, TimeStampedModel, AbstractBaseUser, PermissionsMixin):

    ROLE_CHOICES = (
        ("admin", "Admin"),
        ("seller", "Seller"),
        ("customer", "Customer"),
    )

    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=255, db_index=True)

    username = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Allowed: lowercase letters, numbers, hyphens",
        null=True,   # ← migration safe
        blank=True
    )

    slug = models.SlugField(
        max_length=255,
        unique=True,
        db_index=True,
        null=True,
        blank=True
    )

    username_last_changed = models.DateTimeField(null=True, blank=True)

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="customer")

    profile_image_url = models.URLField(blank=True, null=True)
    bio = models.TextField(blank=True, null=True)

    contact_number = models.CharField(max_length=30, blank=True, null=True)
    whatsapp_number = models.CharField(max_length=30, blank=True, null=True)

    office_address = models.TextField(blank=True, null=True)
    service_area = models.CharField(max_length=255, blank=True, null=True)

    # Auth tokens
    access_token = models.TextField(blank=True, null=True)
    refresh_token = models.TextField(blank=True, null=True)

    otp_expires_at = models.DateTimeField(null=True, blank=True)

    token_version = models.PositiveIntegerField(default=0)

    terms_accept = models.BooleanField(default=False)

    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        indexes = [
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["username"]),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.username})"

    def generate_username(self):
        base = self.email.split("@")[0].lower().replace(".", "-")
        username = base
        counter = 1

        while User.objects.filter(username=username).exists():
            username = f"{base}-{counter}"
            counter += 1

        return username

    def save(self, *args, **kwargs):

        if not self.username:
            self.username = self.generate_username()

        new_slug = slugify(self.username)

        if self.pk:
            old = User.objects.filter(pk=self.pk).first()

            if old and old.username != self.username:
                if old.username_last_changed:
                    diff = timezone.now() - old.username_last_changed
                    if diff.days < 60:
                        raise ValueError("Username can only be changed every 60 days")

                self.username_last_changed = timezone.now()

        else:
            self.username_last_changed = timezone.now()

        self.slug = new_slug

        super().save(*args, **kwargs)