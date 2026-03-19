import os
import dj_database_url
from .settings import *
from .settings import BASE_DIR

# Ensure no None values in ALLOWED_HOSTS
# Read from environment, split by comma
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")
# Ensure no None or empty values in ALLOWED_HOSTS
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS if host.strip()]

CSRF_TRUSTED_ORIGINS = os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in CSRF_TRUSTED_ORIGINS if origin.strip()]

DEBUG = False
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ALLOWED_ORIGINS if origin.strip()]

# Configure storage - use Azure if configured, otherwise use local file storage
# In production (deployment_settings), always use Azure if configured
print(f"\n{'='*70}")
print("[PRODUCTION] STORAGE CONFIGURATION CHECK")
print(f"{'='*70}")

AZURE_ACCOUNT_NAME = os.environ.get("AZURE_ACCOUNT_NAME")
AZURE_ACCOUNT_KEY = os.environ.get("AZURE_ACCOUNT_KEY")
AZURE_CONTAINER = os.environ.get("AZURE_CONTAINER", "media")

print(f"AZURE_ACCOUNT_NAME from env: {AZURE_ACCOUNT_NAME if AZURE_ACCOUNT_NAME else 'NOT SET'}")
print(f"AZURE_ACCOUNT_KEY from env: {'SET' if AZURE_ACCOUNT_KEY else 'NOT SET'}")
print(f"AZURE_CONTAINER from env: {AZURE_CONTAINER}")
print(f"WEBSITE_SITE_NAME: {os.environ.get('WEBSITE_SITE_NAME', 'NOT SET')}")

if AZURE_ACCOUNT_NAME and AZURE_ACCOUNT_KEY:
    # Azure Blob Storage is configured, use it for production
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.azure_storage.AzureStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
    # Update MEDIA_URL for Azure
    MEDIA_URL = f"https://{AZURE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_CONTAINER}/"
    print(f"\n[PRODUCTION] ✅ Azure Blob Storage ENABLED")
    print(f"   Account: {AZURE_ACCOUNT_NAME}")
    print(f"   Container: {AZURE_CONTAINER}")
    print(f"   Media URL: {MEDIA_URL}")
    print(f"{'='*70}\n")
else:
    # No Azure configuration, use local file storage (fallback)
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
    print(f"\n[PRODUCTION] ⚠️  Azure Blob Storage NOT configured - using local file storage")
    print(f"   Reason: {'AZURE_ACCOUNT_NAME missing' if not AZURE_ACCOUNT_NAME else 'AZURE_ACCOUNT_KEY missing'}")
    print(f"\n💡 To enable Azure Blob Storage in production:")
    print(f"   1. Go to Azure Portal → Your App Service → Configuration")
    print(f"   2. Add Application Settings:")
    print(f"      - AZURE_ACCOUNT_NAME=grademedia")
    print(f"      - AZURE_ACCOUNT_KEY=<your-key>")
    print(f"      - AZURE_CONTAINER=media")
    print(f"   3. Save and restart the app")
    print(f"{'='*70}\n")

# CONNECTION = os.environ['AZURE_POSTGRESQL_CONNECTIONSTRING']
# CONNECTION_STR = {pair.split('=')[0]:pair.split('=')[1] for pair in CONNECTION.split(' ')}

# DATABASES = {
#     "default": dj_database_url.config(
#         default=os.environ["DATABASE_URL"], conn_max_age=600
#     )
# }

# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": CONNECTION_STR['dbname'],
#         "HOST": CONNECTION_STR['host'],
#         "USER": CONNECTION_STR['user'],
#         "PASSWORD": CONNECTION_STR['password'],
#     }
# }

#Add connection string from Azure PostgreSQL
CONNECTION_STRING = os.environ.get("AZURE_POSTGRESQL_CONNECTIONSTRING")

if CONNECTION_STRING:
    # Parse "key=value" pairs split by spaces
    parts = [p for p in CONNECTION_STRING.split(" ") if p]
    kv = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            kv[k] = v

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": kv.get("dbname"),
            "HOST": kv.get("host"),
            "PORT": kv.get("port", "5432"),
            "USER": kv.get("user"),
            "PASSWORD": kv.get("password"),
            # Force SSL unless explicitly disabled
            "OPTIONS": {"sslmode": kv.get("sslmode", "require")},
        }
    }
else:
    # Fallback
    # e.g. postgres://user:pass@host:5432/dbname
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        DATABASES = {"default": dj_database_url.config(default=db_url, conn_max_age=600)}
        # Ensure SSL if not set
        if "OPTIONS" not in DATABASES["default"]:
            DATABASES["default"]["OPTIONS"] = {}
        DATABASES["default"]["OPTIONS"].setdefault("sslmode", "require")
    else:
        # Final fallback (not recommended for production)
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }
        }


# Session and CSRF settings
SESSION_COOKIE_SAMESITE = "None"
CSRF_COOKIE_SAMESITE = "None"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_AGE = 1209600  # 2 weeks, in seconds
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

FRONTEND_URL = os.environ.get(
    "FRONTEND_URL",
    "https://blue-wave-0d3d03b00.2.azurestaticapps.net",
)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}


# Number of log backups to keep (default value, can be overridden by LogSetting)
LOG_BACKUP_COUNT = 10

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} [{levelname}] {name}: {message}',
            'style': '{',
        },
        'simple': {
            'format': '[{levelname}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'executor': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'authentication': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'grade': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}

# Admin Email Settings - read from environment
ADMIN_EMAILS = os.environ.get("ADMIN_EMAILS", "").split(",")
ADMIN_EMAILS = [email.strip() for email in ADMIN_EMAILS if email.strip()]

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
ORGANIZATION_ID = os.environ.get("MYDJANGOAPP_ORGANIZATION_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Gmail SMTP Configuration (for Production)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)
SERVER_EMAIL = EMAIL_HOST_USER

# Razorpay Payment Gateway
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
RAZORPAY_KEY = os.environ.get("RAZORPAY_KEY")
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY")

# CORS Settings for production
CORS_ALLOW_CREDENTIALS = True
# Note: CORS_ALLOW_ALL_ORIGINS should be False in production (we use CORS_ALLOWED_ORIGINS instead)
CORS_ALLOW_ALL_ORIGINS = False

# Celery Configuration with Redis
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
