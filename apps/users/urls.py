from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterView, VerifyOtpView, LoginView, AdminLoginView,
    ProfileView, UpdateProfileView,
    ForgotPasswordView, ResetPasswordView,
    LogoutView, LogoutAllView,
    AdminSellerListView, AdminCustomerListView, AdminUserDeleteView,
)

urlpatterns = [
    path("register/", RegisterView.as_view()),
    path("verify-otp/", VerifyOtpView.as_view()),

    path("login/", LoginView.as_view()),
    path("amar-admin/login/", AdminLoginView.as_view()),
    
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path("logout/", LogoutView.as_view()),
    path("logout/all/", LogoutAllView.as_view()),

    path("forgot-password/", ForgotPasswordView.as_view()),
    path("reset-password/", ResetPasswordView.as_view()),

    # admin features
    path("amar-admin/sellers/", AdminSellerListView.as_view()),
    path("amar-admin/customers/", AdminCustomerListView.as_view()),
    path("amar-admin/<str:id>/delete/", AdminUserDeleteView.as_view()),

    path("<slug:slug>/", ProfileView.as_view()),
    path("<slug:slug>/settings/", UpdateProfileView.as_view()),
]