"""Configuración para pruebas: usa DATABASE_URL si existe (PostgreSQL) o SQLite."""
import os

os.environ.setdefault("DEBUG", "true")

from .settings import *  # noqa: E402,F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
