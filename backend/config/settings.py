"""
Configuration Django de la plateforme DCUHAT.

Direction Communale de l'Urbanisme, de l'Habitat et de l'Amenagement
du Territoire de Lambayin.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return str(env(key, str(default))).lower() in ("1", "true", "yes", "oui", "on")


def env_list(key, default=""):
    raw = env(key, default) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


# --------------------------------------------------------------------------
# Base
# --------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-uniquement-a-remplacer-en-production")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.contrib.gis",
    # tiers
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # applications DCUHAT
    "apps.common",
    "apps.accounts",
    "apps.storage",
    "apps.geo",
    "apps.sharing",
    "apps.sync",
    "apps.audit",
    "apps.search",
    "apps.notifications",
]

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
    "apps.audit.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

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

# --------------------------------------------------------------------------
# Base de donnees : PostgreSQL + PostGIS
# --------------------------------------------------------------------------
def _base_depuis_url(url: str) -> dict:
    """Decompose une URL `postgresql://...`, telle que la fournissent Supabase,
    Render ou Neon. Recopier cinq variables a la main est une source d'erreurs
    de trop ; une seule chaine se colle sans se tromper."""
    from urllib.parse import unquote, urlparse

    morceaux = urlparse(url)
    return {
        "NAME": (morceaux.path or "/postgres").lstrip("/"),
        "USER": unquote(morceaux.username or "postgres"),
        "PASSWORD": unquote(morceaux.password or ""),
        "HOST": morceaux.hostname or "127.0.0.1",
        "PORT": str(morceaux.port or 5432),
    }


_url_base = env("DATABASE_URL", "")
_reglages_base = (
    _base_depuis_url(_url_base)
    if _url_base
    else {
        "NAME": env("POSTGRES_DB", "dcuhat"),
        "USER": env("POSTGRES_USER", "postgres"),
        "PASSWORD": env("POSTGRES_PASSWORD", "postgres"),
        "HOST": env("POSTGRES_HOST", "127.0.0.1"),
        "PORT": env("POSTGRES_PORT", "5432"),
    }
)

# Les bases hebergees exigent TLS ; en local on ne l'impose pas.
_sslmode = env("POSTGRES_SSLMODE", "") or (
    "require" if not _reglages_base["HOST"] in ("127.0.0.1", "localhost", "db") else ""
)

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "CONN_MAX_AGE": int(env("POSTGRES_CONN_MAX_AGE", "60")),
        "OPTIONS": {"sslmode": _sslmode} if _sslmode else {},
        **_reglages_base,
    }
}

# Le pooler « transaction » de Supabase (port 6543) ne garde pas la session
# entre deux requetes : les curseurs cote serveur y sont inutilisables. Le
# pooler « session » (port 5432) n'a pas cette limite et reste preferable pour
# Django ; on s'adapte tout de meme si le port 6543 est configure.
DISABLE_SERVER_SIDE_CURSORS = _reglages_base["PORT"] == "6543"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# --------------------------------------------------------------------------
# Authentification et mots de passe
# --------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_MAX_FAILED_ATTEMPTS = int(env("LOGIN_MAX_FAILED_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(env("LOGIN_LOCKOUT_MINUTES", "15"))

# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.CursorPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "apps.common.exceptions.dcuhat_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "1200/min", "login": "10/min"},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "API DCUHAT",
    "DESCRIPTION": (
        "Plateforme collaborative de gestion documentaire et geospatiale de la "
        "Direction Communale de l'Urbanisme, de l'Habitat et de l'Amenagement "
        "du Territoire de Lambayin."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
CORS_ALLOW_CREDENTIALS = False

# --------------------------------------------------------------------------
# Stockage objet
# --------------------------------------------------------------------------
OBJECT_STORAGE_BACKEND = env("OBJECT_STORAGE_BACKEND", "local")  # local | s3
OBJECT_STORAGE_LOCAL_ROOT = Path(
    env("OBJECT_STORAGE_LOCAL_ROOT", str(BASE_DIR.parent / "var" / "objets"))
)
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", "http://minio:9000")
S3_ACCESS_KEY = env("S3_ACCESS_KEY", "dcuhat")
S3_SECRET_KEY = env("S3_SECRET_KEY", "dcuhat-secret")
S3_BUCKET = env("S3_BUCKET", "dcuhat")
S3_REGION = env("S3_REGION", "us-east-1")
S3_PRESIGNED_TTL = int(env("S3_PRESIGNED_TTL", "300"))

MAX_UPLOAD_SIZE_MB = int(env("MAX_UPLOAD_SIZE_MB", "2048"))
UPLOAD_CHUNK_SIZE_MB = int(env("UPLOAD_CHUNK_SIZE_MB", "5"))
SIMPLE_UPLOAD_MAX_MB = int(env("SIMPLE_UPLOAD_MAX_MB", "10"))
DEFAULT_SERVICE_QUOTA_GB = int(env("DEFAULT_SERVICE_QUOTA_GB", "50"))
TRASH_RETENTION_DAYS = int(env("TRASH_RETENTION_DAYS", "30"))
VERSION_RETENTION_COUNT = int(env("VERSION_RETENTION_COUNT", "20"))

# --------------------------------------------------------------------------
# Edition dans l'application
# --------------------------------------------------------------------------
#: Taille maximale d'un document modifiable directement (caracteres).
EDITION_MAX_CARACTERES = int(env("EDITION_MAX_CARACTERES", "2000000"))
#: Au-dela de ce delai depuis la derniere version, la sauvegarde automatique
#: publie d'elle-meme une version : une panne de courant en fin de journee ne
#: doit pas couter plus que ce laps de temps.
EDITION_INTERVALLE_VERSION_MINUTES = int(
    env("EDITION_INTERVALLE_VERSION_MINUTES", "15")
)

DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# --------------------------------------------------------------------------
# Geospatial
# --------------------------------------------------------------------------
GEO_STORAGE_SRID = 4326
GEO_DEFAULT_SRIDS = [int(s) for s in env_list("GEO_DEFAULT_SRIDS", "4326,32628,32629")]
GEO_SIMPLIFY_TOLERANCE = float(env("GEO_SIMPLIFY_TOLERANCE", "0.00005"))
GEO_MAX_FEATURES_INLINE = int(env("GEO_MAX_FEATURES_INLINE", "5000"))
# GDAL et GEOS sont localisees automatiquement : variable d'environnement si
# elle est fournie, sinon bundle PostGIS sous Windows, sinon bibliotheques
# embarquees dans les roues PyPI (rasterio, shapely) — ce dernier cas rend le
# deploiement possible sur un hebergement sans acces systeme, donc sans Docker.
# Si rien n'est trouve, on laisse Django mener sa propre recherche.
from apps.common.geolibs import trouver_gdal, trouver_geos  # noqa: E402

GDAL_LIBRARY_PATH = trouver_gdal()
GEOS_LIBRARY_PATH = trouver_geos()

# --------------------------------------------------------------------------
# Celery / Redis
# --------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
    if env_bool("USE_REDIS_CACHE", False)
    else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}

# --------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
SEARCH_LANGUAGE = "french"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR.parent / "var" / "media"

# --------------------------------------------------------------------------
# Securite (active hors DEBUG)
# --------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"}
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
