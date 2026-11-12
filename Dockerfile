# DRAKON · imagen de producción
# Construir:  docker build -t drakon .
# Ejecutar:   docker compose up --build   (incluye PostgreSQL)

# ---------- Etapa 1: dependencias (se reutiliza en caché si requirements.txt no cambia)
FROM python:3.12-slim AS dependencias
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install -r requirements.txt

# ---------- Etapa 2: imagen final, liviana y sin herramientas de compilación
FROM python:3.12-slim
LABEL org.opencontainers.image.title="DRAKON" \
      org.opencontainers.image.description="Sistema de gestión de auditorías ISO/IEC 27002:2022 (arquitectura hexagonal)" \
      org.opencontainers.image.licenses="UNLICENSED"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    DJANGO_SETTINGS_MODULE=drakon.infraestructura.django_config.settings \
    PORT=8000

WORKDIR /app
COPY --from=dependencias /venv /venv
COPY . .

# Archivos estáticos con nombres versionados (WhiteNoise) y usuario sin privilegios
RUN SECRET_KEY=solo-para-collectstatic python manage.py collectstatic --noinput -v0 \
    && useradd --create-home --uid 1000 drakon && chown -R drakon /app
USER drakon

EXPOSE 8000

# Docker marca el contenedor como «unhealthy» si /salud/ deja de responder
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/salud/', timeout=4)" || exit 1

# Migra, inicializa (idempotente) y arranca. Render/Railway inyectan $PORT.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py inicializar && gunicorn drakon.infraestructura.django_config.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --timeout 60 --access-logfile -"]
