FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    DJANGO_SETTINGS_MODULE=drakon.infraestructura.django_config.settings

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN SECRET_KEY=solo-para-collectstatic python manage.py collectstatic --noinput -v0 \
    && useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
# Migra, inicializa (idempotente) y arranca. Render inyecta $PORT.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py inicializar && gunicorn drakon.infraestructura.django_config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60"]
