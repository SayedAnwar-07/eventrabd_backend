from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Fields shown in list view
    list_display = (
        "email", "first_name", "last_name", "user_type",
        "is_verified", "accepted_terms", "created_at", "updated_at"
    )
    list_filter = ("user_type", "is_verified", "accepted_terms", "created_at")
    search_fields = ("email", "first_name", "last_name", "phone_number", "whatsapp_number")
    ordering = ("-created_at",)

    # Read-only fields in admin
    readonly_fields = ("id", "created_at", "updated_at", "otp_expiry", "token_created_at")

    # Fieldsets for editing a user
    fieldsets = (
        (_("Account Info"), {
            "fields": ("email", "password")
        }),
        (_("Personal Info"), {
            "fields": (
                "first_name", "last_name", "profile_image",
                "phone_number", "whatsapp_number", "user_type"
            )
        }),
        (_("Verification & Security"), {
            "fields": (
                "is_verified", "accepted_terms",
                "otp", "otp_expiry",
                "verification_token", "token_created_at"
            )
        }),
        (_("Permissions"), {
            "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")
        }),
        (_("Important Dates"), {
            "fields": ("last_login", "created_at", "updated_at")
        }),
    )

    # Fieldsets for creating a user in the admin panel
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "user_type", "password1", "password2", "accepted_terms"),
        }),
    )
