from django.urls import path

from .views import (
    AdminCustomerListView,
    AdminLoginView,
    AdminProfileView,
    AdminSellerListView,
    AdminUserDeleteView,
    ClientTokenRefreshView,
    AdminTokenRefreshView,
    CsrfTokenView,
    ForgotPasswordView,
    LoginView,
    LogoutAllView,
    LogoutView,
    AdminLogoutView,
    AdminLogoutAllView,
    MyProfileView,
    ProfileView,
    RegisterView,
    ResetPasswordView,
    UpdateProfileView,
    VerifyOtpView,
    AdminProfileUpdateView,
    AdminForgotPasswordView,
    AdminResetPasswordView,
)


urlpatterns = [

    # CSRF
    path(
        "csrf/",
        CsrfTokenView.as_view(),
        name="csrf-token",
    ),


    # Authentication
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


    # ─────────────────────────────
    # Token Refresh
    # ─────────────────────────────

    # Client (customer + seller)
    path(
        "token/refresh/",
        ClientTokenRefreshView.as_view(),
        name="client-token-refresh",
    ),


    # Admin
    path(
        "amar-admin/token/refresh/",
        AdminTokenRefreshView.as_view(),
        name="admin-token-refresh",
    ),



    # Logout
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

    path(
        "amar-admin/logout/",
        AdminLogoutView.as_view(),
        name="admin-logout",
    ),

    path(
        "amar-admin/logout/all/",
        AdminLogoutAllView.as_view(),
        name="admin-logout-all",
    ),


    # Password
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



    # Admin
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
    
    path(
        "amar-admin/profile/update/",
        AdminProfileUpdateView.as_view(),
        name="admin-profile-update",
    ),


    path(
        "amar-admin/forgot-password/",
        AdminForgotPasswordView.as_view(),
        name="admin-forgot-password",
    ),


    path(
        "amar-admin/reset-password/",
        AdminResetPasswordView.as_view(),
        name="admin-reset-password",
    ),



    # Current user
    path(
        "me/",
        MyProfileView.as_view(),
        name="my-profile",
    ),



    # Public profile
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