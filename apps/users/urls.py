from django.urls import path
from .views import (
    RegisterView, VerifyOtpView, LoginView,
    ProfileView, UpdateProfileView,
    ForgotPasswordView, ResetPasswordView,
    LogoutView, LogoutAllView,
)


urlpatterns = [
    path("register/",    RegisterView.as_view()),
    path("verify-otp/",  VerifyOtpView.as_view()),
    path("login/",       LoginView.as_view()),
    path("logout/",      LogoutView.as_view()),
    path("logout/all/",  LogoutAllView.as_view()),

    path("forgot-password/", ForgotPasswordView.as_view()),
    path("reset-password/",  ResetPasswordView.as_view()),

    path("<slug:slug>/",          ProfileView.as_view()),
    path("<slug:slug>/settings/", UpdateProfileView.as_view()),
]