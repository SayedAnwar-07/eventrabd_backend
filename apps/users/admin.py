from django.contrib import admin

from django.contrib.sites.models import Site
from django.contrib.auth.models import Group
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):

    model = User

    # ---------------------------
    # IMAGE PREVIEW
    # ---------------------------
    def profile_image_preview(self, obj):
        if obj.profile_image_url:
            return format_html(
                '<img src="{}" style="width:40px; height:40px; border-radius:50%; object-fit:cover;" />',
                obj.profile_image_url
            )
        return "—"
    profile_image_preview.short_description = "Profile"

    def profile_image_tag(self, obj):
        if obj.profile_image_url:
            return format_html(
                '<img src="{}" style="width:120px; height:120px; border-radius:50%; object-fit:cover;" />',
                obj.profile_image_url
            )
        return "No Image"

    readonly_fields = ("profile_image_tag", "slug", "username_last_changed")

    # ---------------------------
    # LIST PAGE
    # ---------------------------
    list_display = (
        "id",
        "profile_image_preview",
        "email",
        "username",
        "full_name",
        "role",
        "is_active",
        "is_verified",
        "terms_accept",
    )
    list_filter = ("role", "is_active", "is_verified")
    search_fields = ("email", "full_name", "username", "id")
    ordering = ("-date_joined",)

    # ---------------------------
    # EDIT USER PAGE
    # ---------------------------
    fieldsets = (
        ("Account Info", {
            "fields": ("email", "password", "full_name", "username", "slug", "role")
        }),
        ("Profile Image", {
            "fields": ("profile_image_tag", "profile_image_url"),
        }),
        ("Personal Info", {
            "fields": ("contact_number", "whatsapp_number", "office_address", "service_area",
                       "bio")
        }),
        ("Status", {
            "fields": ("is_active", "is_verified", "is_staff", "is_superuser"),
        }),
        ("Tokens", {
            "fields": ("access_token", "refresh_token", "terms_accept"),
        }),
        ("Important Dates", {
            "fields": ("last_login", "date_joined", "username_last_changed"),
        }),
        ("Permissions", {
            "fields": ("groups", "user_permissions"),
        }),
    )

    # ---------------------------
    # CREATE USER PAGE
    # ---------------------------
    add_fieldsets = (
        ("Create User", {
            "classes": ("wide",),
            "fields": (
                "email",
                "full_name",
                "username",
                "password1",
                "password2",
                "role",
            ),
        }),
    )

    # Disable admin logs
    def log_addition(self, request, object, message):
        pass

    def log_change(self, request, object, message):
        pass

    def log_deletion(self, request, object, object_repr):
        pass


# ------------------------------------
# REMOVE UNNECESSARY MODELS FROM ADMIN
# ------------------------------------
admin.site.unregister(Site)
admin.site.unregister(Group)
admin.site.unregister(EmailAddress)
admin.site.unregister(SocialAccount)
admin.site.unregister(SocialApp)
admin.site.unregister(SocialToken)
admin.site.unregister(BlacklistedToken)
admin.site.unregister(OutstandingToken)
