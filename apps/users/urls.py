from django.urls import path, re_path
from .views import (
    RegisterView,
    LoginView,
    VerifyOtpView,
    ResendOtpView,
    ForgotPasswordView,
    ResetPasswordView,
    GetProfileView,
    UpdateProfileView,
    SellerUserEventDashboardView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('verify-otp/', VerifyOtpView.as_view(), name='verify-otp'),
    path('resend-otp/', ResendOtpView.as_view(), name='resend-otp'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    
    re_path(r"^profile/(?P<slug>[-a-z0-9]+)/$", GetProfileView.as_view(), name="public-profile"),
    re_path(r"^profile/(?P<slug>[-a-z0-9_]+)/edit/$", UpdateProfileView.as_view(), name="update-profile"),
    re_path(r"^profile/(?P<slug>[-a-z0-9_]+)/dashboard/$", SellerUserEventDashboardView.as_view(), name="seller-user-event-dashboard"),
]
