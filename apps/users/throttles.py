from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """5 attempts per minute on /login/."""
    scope = 'login'


class OtpRateThrottle(AnonRateThrottle):
    """10 attempts per hour on /verify-otp/."""
    scope = 'otp'


class PasswordResetRateThrottle(AnonRateThrottle):
    """5 attempts per hour on /reset-password/ and /forgot-password/."""
    scope = 'password_reset'