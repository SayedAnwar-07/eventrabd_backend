from django.urls import path

from .views import (
    AdminCustomerListView,
    AdminLoginView,
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

    # HttpOnly cookie refresh
    path(
        "token/refresh/",
        CookieTokenRefreshView.as_view(),
        name="token-refresh",
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

    # Admin features
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

    # Current user
    path(
        "me/",
        MyProfileView.as_view(),
        name="my-profile",
    ),

    # Dynamic slug routes must remain last
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