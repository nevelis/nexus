import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-only-change-in-production")
DEBUG = os.environ.get("DEBUG", "True") == "True"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# CSRF — list every origin that may POST to this app (scheme+host, no trailing slash)
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CSRF_TRUSTED_ORIGINS",
        "https://nexus.lab.amazingland.live",
    ).split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "pgvector.django",
    # MCP server (django-mcp-server package)
    "mcp_server",
    # Nexus apps
    "documents",
    "search",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"

# Database — PostgreSQL with pgvector
# dj_database_url handles sslmode and all URL edge cases reliably
DATABASES = {
    "default": dj_database_url.config(
        default="postgresql://nexus:nexus@localhost:5432/nexus",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Django 5.2+ uses STORAGES instead of the deprecated STATICFILES_STORAGE setting
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# django-silk profiler — opt-in via SILK_ENABLED env var
SILK_ENABLED = os.environ.get("SILK_ENABLED", "False") == "True"
if SILK_ENABLED:
    INSTALLED_APPS.append("silk")
    # Insert SilkyMiddleware after AuthenticationMiddleware so user info is available
    _auth_idx = MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware")
    MIDDLEWARE.insert(_auth_idx + 1, "silk.middleware.SilkyMiddleware")
    # Require staff/superuser login to access silk UI
    SILKY_AUTHENTICATION = True
    SILKY_AUTHORISATION = True

# Embedding settings — remote API via EmbeddingClient (search.embeddings)
# Dimensions must match VectorField in models.py and the remote model (all-MiniLM-L6-v2)
EMBEDDING_DIMENSIONS = 384

# django-mcp-server config
DJANGO_MCP_ENDPOINT = "mcp/"
# Set DJANGO_MCP_AUTHENTICATION_CLASSES to require auth in production
# e.g. ["rest_framework.authentication.TokenAuthentication"]
DJANGO_MCP_AUTHENTICATION_CLASSES = []
