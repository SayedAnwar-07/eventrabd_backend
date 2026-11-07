
import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured
from corsheaders.defaults import default_headers

import cloudinary
import dj_database_url


# ============================================================
# BASE CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)


def env_bool(name, default=False):
    value = os.getenv(name, str(default))
    return value.strip().lower() in ("true", "1", "yes", "on")


def required_env(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"{name} is not set in environment variables."
        )
    return value


# ============================================================
# SECRET KEY AND DEBUG
# ============================================================

SECRET_KEY = required_env("SECRET_KEY")

DEBUG = env_bool("DEBUG", False)


# ============================================================
# ALLOWED HOSTS
# ============================================================

raw_hosts = os.getenv(
    "ALLOWED_HOSTS",
    "api.eventrabd.com,eventrabd.com,www.eventrabd.com,localhost,127.0.0.1"
)

ALLOWED_HOSTS = (
    ["*"]
    if raw_hosts.strip() == "*"
    else [
        host.strip()
        for host in raw_hosts.split(",")
        if host.strip()
    ]
)


# ============================================================
# CORS CONFIGURATION
# ============================================================


CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOWED_ORIGINS = [
    # Production
    "https://eventrabd.com",
    "https://www.eventrabd.com",
    "https://eventra-bd.vercel.app",
    "https://eventra-bd-admin.netlify.app",
    "https://eventrabd-test.netlify.app",

    # Local
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

CSRF_TRUSTED_ORIGINS = [
    # Production
    "https://eventrabd.com",
    "https://www.eventrabd.com",
    "https://eventra-bd.vercel.app",
    "https://eventra-bd-admin.netlify.app",
    "https://eventrabd-test.netlify.app",

    # Local
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]



# ============================================================
# INSTALLED APPS
# ============================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",

    # Third-party apps
    "rest_framework",
    "channels",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "imagekit",
    "cloudinary",
    "corsheaders",
    "anymail",

    # Local apps
    "apps.core",
    "apps.users",
    "apps.event_planner",
    "apps.event_services",
    "apps.hires",
    "apps.invoices",
    "apps.notifications",
    "apps.reviews",
    "apps.packages",
    "apps.reports",
    "apps.membership",
]


# ============================================================
# MIDDLEWARE
# ============================================================

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",

    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "apps.core.middleware.GlobalErrorMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    "allauth.account.middleware.AccountMiddleware",
    "apps.users.middleware.TokenVersionMiddleware",
]

# ============================================================
# URL AND APPLICATION CONFIGURATION
# ============================================================

ROOT_URLCONF = "backend.urls"

WSGI_APPLICATION = "backend.wsgi.application"

ASGI_APPLICATION = "backend.asgi.application"


# ============================================================
# TEMPLATES
# ============================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ============================================================
# REDIS CONFIGURATION
# ============================================================

REDIS_URL = os.getenv("REDIS_URL", "").strip()

if not REDIS_URL:
    if DEBUG:
        REDIS_URL = "redis://localhost:6379/1"
    else:
        raise ImproperlyConfigured(
            "REDIS_URL is required in production."
        )


# Separate Redis URL for cache (optional)
REDIS_CACHE_URL = os.getenv(
    "REDIS_CACHE_URL",
    REDIS_URL
).strip()


# ============================================================
# DJANGO CHANNELS / WEBSOCKETS
# ============================================================

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
            "capacity": 1500,
            "expiry": 10,
        },
    },
}


# ============================================================
# DJANGO CACHE
# ============================================================

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
    }
}



# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Dokploy internal PostgreSQL connections do not require SSL.
# Set DATABASE_SSL_REQUIRE=True only when your database provider
# explicitly requires SSL.
DATABASE_SSL_REQUIRE = env_bool("DATABASE_SSL_REQUIRE", False)


if DATABASE_URL:

    # --------------------------------------------------------
    # DATABASE URL CONFIGURATION
    # --------------------------------------------------------

    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=0,
            ssl_require=DATABASE_SSL_REQUIRE,
        )
    }

    # Explicitly configure SSL mode.
    # This also overrides sslmode=require if it exists in DATABASE_URL.
    DATABASE_OPTIONS = DATABASES["default"].get("OPTIONS") or {}

    DATABASE_OPTIONS["sslmode"] = (
        "require" if DATABASE_SSL_REQUIRE else "disable"
    )

    DATABASE_OPTIONS.setdefault("connect_timeout", 10)

    DATABASES["default"]["OPTIONS"] = DATABASE_OPTIONS

    # Connection settings
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True


else:

    # --------------------------------------------------------
    # INDIVIDUAL DATABASE ENVIRONMENT VARIABLES
    # --------------------------------------------------------

    if DEBUG:

        DB_NAME = os.getenv("DB_NAME", "eventraBD")
        DB_USER = os.getenv("DB_USER", "postgres")
        DB_PASSWORD = os.getenv("DB_PASSWORD", "")
        DB_HOST = os.getenv("DB_HOST", "localhost")
        DB_PORT = os.getenv("DB_PORT", "5432")

    else:

        DB_NAME = required_env("DB_NAME")
        DB_USER = required_env("DB_USER")
        DB_PASSWORD = required_env("DB_PASSWORD")
        DB_HOST = required_env("DB_HOST")
        DB_PORT = os.getenv("DB_PORT", "5432")

    # --------------------------------------------------------
    # FINAL DATABASE SETTINGS
    # --------------------------------------------------------

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",

            "NAME": DB_NAME,
            "USER": DB_USER,
            "PASSWORD": DB_PASSWORD,

            "HOST": DB_HOST,
            "PORT": DB_PORT,

            "CONN_MAX_AGE": 0,
            "CONN_HEALTH_CHECKS": True,

            "DISABLE_SERVER_SIDE_CURSORS": True,

            "OPTIONS": {
                "connect_timeout": 10,

                "sslmode": (
                    "require" if DATABASE_SSL_REQUIRE else "disable"
                ),
            },
        }
    }

# ============================================================
# AUTHENTICATION
# ============================================================

AUTH_USER_MODEL = "users.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SITE_ID = int(os.getenv("SITE_ID", "1"))


# ============================================================
# PASSWORD VALIDATION
# ============================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME":
        "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME":
        "django.contrib.auth.password_validation.MinimumLengthValidator"
    },
    {
        "NAME":
        "django.contrib.auth.password_validation.CommonPasswordValidator"
    },
    {
        "NAME":
        "django.contrib.auth.password_validation.NumericPasswordValidator"
    },
]


# ============================================================
# INTERNATIONALIZATION
# ============================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Dhaka")

USE_I18N = True

USE_TZ = True


# ============================================================
# STATIC AND MEDIA FILES
# ============================================================
STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },

    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ============================================================
# DJANGO REST FRAMEWORK
# ============================================================

REST_FRAMEWORK = {
    "DEFAULT_EXCEPTION_HANDLER":
        "apps.core.exceptions.custom_exception_handler",

    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],

    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],

    "DEFAULT_PAGINATION_CLASS":
        "rest_framework.pagination.PageNumberPagination",

    "PAGE_SIZE": 20,

    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],

    "DEFAULT_THROTTLE_RATES": {
        "login": "5/minute",
        "otp": "10/hour",
        "password_reset": "5/hour",
        "token_refresh": "20/minute",
        "public_brand": "300/hour",
    },
}


# ============================================================
# SIMPLE JWT
# ============================================================

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),

    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),

    "ROTATE_REFRESH_TOKENS": True,

    "BLACKLIST_AFTER_ROTATION": True,

    "UPDATE_LAST_LOGIN": True,

    "ALGORITHM": "HS256",

    "SIGNING_KEY": SECRET_KEY,

    "AUTH_HEADER_TYPES": ("Bearer",),

    "USER_ID_FIELD": "id",

    "USER_ID_CLAIM": "user_id",
}


# ============================================================
# REFRESH TOKEN COOKIES
# ============================================================

CLIENT_REFRESH_TOKEN_COOKIE_NAME = (
    "eventrabd_client_site_refresh"
)

ADMIN_REFRESH_TOKEN_COOKIE_NAME = (
    "eventrabd_admin_site_refresh"
)

REFRESH_TOKEN_COOKIE_PATH = "/"

REFRESH_TOKEN_COOKIE_DOMAIN = None

REFRESH_TOKEN_COOKIE_HTTPONLY = True

REFRESH_TOKEN_COOKIE_SECURE = not DEBUG

REFRESH_TOKEN_COOKIE_SAMESITE = (
    "Lax" if DEBUG else "None"
)

REFRESH_TOKEN_COOKIE_MAX_AGE = int(
    SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()
)


# ============================================================
# CSRF COOKIE
# ============================================================

CSRF_COOKIE_NAME = "csrftoken"

CSRF_HEADER_NAME = "HTTP_X_CSRFTOKEN"

CSRF_COOKIE_HTTPONLY = False

CSRF_COOKIE_SECURE = not DEBUG

CSRF_COOKIE_SAMESITE = (
    "Lax" if DEBUG else "None"
)

CSRF_COOKIE_PATH = "/"


# ============================================================
# BREVO EMAIL CONFIGURATION
# ============================================================

EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"

BREVO_API_KEY = required_env("BREVO_API_KEY")

ANYMAIL = {
    "BREVO_API_KEY": BREVO_API_KEY,
}

DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    "eventrabdofficial@gmail.com"
)

SERVER_EMAIL = os.getenv(
    "SERVER_EMAIL",
    DEFAULT_FROM_EMAIL
)

EMAIL_SUBJECT_PREFIX = os.getenv(
    "EMAIL_SUBJECT_PREFIX",
    "[Eventra BD]"
)

SITE_NAME = os.getenv(
    "SITE_NAME",
    "Eventra BD"
)


# ============================================================
# CLOUDINARY CONFIGURATION
# ============================================================

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


# ============================================================
# CELERY CONFIGURATION
# ============================================================

CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    REDIS_URL
)

CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND",
    REDIS_URL
)

CELERY_TASK_SERIALIZER = "json"

CELERY_RESULT_SERIALIZER = "json"

CELERY_ACCEPT_CONTENT = ["json"]

CELERY_TIMEZONE = TIME_ZONE


# ============================================================
# OTP CONFIGURATION
# ============================================================

OTP_VALIDITY_SECONDS = int(
    os.getenv("OTP_VALIDITY", "600")
)


# ============================================================
# PRODUCTION SECURITY
# ============================================================

if not DEBUG:

    # HTTPS
    SECURE_SSL_REDIRECT = True

    SECURE_PROXY_SSL_HEADER = (
        "HTTP_X_FORWARDED_PROTO",
        "https"
    )

    # Secure cookies
    SESSION_COOKIE_SECURE = True

    SESSION_COOKIE_HTTPONLY = True

    CSRF_COOKIE_SECURE = True

    CSRF_COOKIE_HTTPONLY = False

    # Security headers
    SECURE_CONTENT_TYPE_NOSNIFF = True

    X_FRAME_OPTIONS = "DENY"

    # HSTS: enable after all relevant domains have valid HTTPS.
    SECURE_HSTS_SECONDS = int(
        os.getenv("SECURE_HSTS_SECONDS", "0")
    )

    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
        "SECURE_HSTS_INCLUDE_SUBDOMAINS",
        False
    )

    SECURE_HSTS_PRELOAD = env_bool(
        "SECURE_HSTS_PRELOAD",
        False
    )

    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
