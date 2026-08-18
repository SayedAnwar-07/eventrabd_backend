from django.urls import path

from .views import (
    AdminCustomerListView,
    AdminLoginView,
    AdminProfileView,
    AdminSellerListView,
    AdminUserDeleteView,
    CookieTokenRefreshView,
    CsrfTokenView,
    ForgotPasswordView,
    LoginView,
    LogoutAllView,
    LogoutView,
    MyProfileView,
    ProfileView,
    RegisterView,
    ResetPasswordView,
    UpdateProfileView,
    VerifyOtpView,
)


urlpatterns = [
    # =========================================================================
    # CSRF
    # =========================================================================

    path(
        "csrf/",
        CsrfTokenView.as_view(),
        name="csrf-token",
    ),

    # =========================================================================
    # Authentication
    # =========================================================================

    path(
        "register/",
        RegisterView.as_view(),
        name="register",
    ),

    path(
        "verify-otp/",
        VerifyOtpView.as_view(),
        name="verify-otp",
    ),

    path(
        "login/",
        LoginView.as_view(),
        name="login",
    ),

    path(
        "amar-admin/login/",
        AdminLoginView.as_view(),
        name="admin-login",
    ),

    # =========================================================================
    # HttpOnly Cookie Token Refresh
    #
    # Final API:
    # POST /users/token/refresh/
    #
    # Both normal users and admins use this same refresh endpoint.
    # =========================================================================

    path(
        "token/refresh/",
        CookieTokenRefreshView.as_view(),
        name="token-refresh",
    ),

    # =========================================================================
    # Logout
    # =========================================================================

    path(
        "logout/",
        LogoutView.as_view(),
        name="logout",
    ),

    path(
        "logout/all/",
        LogoutAllView.as_view(),
        name="logout-all",
    ),

    # =========================================================================
    # Password
    # =========================================================================

    path(
        "forgot-password/",
        ForgotPasswordView.as_view(),
        name="forgot-password",
    ),

    path(
        "reset-password/",
        ResetPasswordView.as_view(),
        name="reset-password",
    ),

    # =========================================================================
    # Admin
    # =========================================================================

    path(
        "amar-admin/me/",
        AdminProfileView.as_view(),
        name="admin-profile",
    ),

    path(
        "amar-admin/sellers/",
        AdminSellerListView.as_view(),
        name="admin-sellers",
    ),

    path(
        "amar-admin/customers/",
        AdminCustomerListView.as_view(),
        name="admin-customers",
    ),

    path(
        "amar-admin/<str:id>/delete/",
        AdminUserDeleteView.as_view(),
        name="admin-user-delete",
    ),

    # =========================================================================
    # Current User
    # =========================================================================

    path(
        "me/",
        MyProfileView.as_view(),
        name="my-profile",
    ),

    # =========================================================================
    # Dynamic Slug Routes
    #
    # Must remain LAST so values such as:
    # csrf
    # login
    # token
    # amar-admin
    #
    # are not accidentally interpreted as a user slug.
    # =========================================================================

    path(
        "<slug:slug>/settings/",
        UpdateProfileView.as_view(),
        name="update-profile",
    ),

    path(
        "<slug:slug>/",
        ProfileView.as_view(),
        name="public-profile",
    ),
]