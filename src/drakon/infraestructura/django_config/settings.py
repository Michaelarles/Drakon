"""Configuración de Django (adaptador). Todo lo sensible llega por variables de entorno."""
import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parents[4]          # raíz del repositorio
INFRA_DIR = Path(__file__).resolve().parents[1]


def env_bool(nombre: str, defecto: bool = False) -> bool:
    return os.environ.get(nombre, str(defecto)).lower() in ("1", "true", "yes", "si", "sí")


DEBUG = env_bool("DEBUG", False)
SECRET_KEY = os.environ.get("SECRET_KEY") or ("dev-inseguro-solo-local" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Defina la variable de entorno SECRET_KEY (o DEBUG=true en local).")

ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
# Dominio público que inyecta la plataforma (Railway o Render); también vale ALLOWED_HOSTS a mano
for variable in ("RAILWAY_PUBLIC_DOMAIN", "RENDER_EXTERNAL_HOSTNAME"):
    if os.environ.get(variable):
        ALLOWED_HOSTS.append(os.environ[variable])
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "drakon.infraestructura.persistencia",
    "drakon.infraestructura.web",
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

ROOT_URLCONF = "drakon.infraestructura.django_config.urls"
WSGI_APPLICATION = "drakon.infraestructura.django_config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Primero las plantillas de DRAKON, para personalizar también el admin de Django
        "DIRS": [INFRA_DIR / "web" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# PostgreSQL por DATABASE_URL (Neon en producción). Sin ella, SQLite solo para desarrollo.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=60,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
                    if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Límite de subida alineado con la regla de 5 MB por evidencia
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^salud/$"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
