# Appli Django : gunicorn, sans privilèges root. Les fichiers statiques et media sont
# servis par le conteneur Nginx voisin (voir docker-compose.yml de sites-infra).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_STATIC_ROOT=/static \
    DJANGO_MEDIA_ROOT=/data/media \
    DJANGO_DB_PATH=/data/db.sqlite3

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod 755 docker-entrypoint.sh \
    && useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data /static \
    && chown app:app /data /static

USER app
EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
# WSGI_APP est fourni par docker-compose (osculte.wsgi:application, pizzeria.wsgi:application).
CMD ["sh", "-c", "exec gunicorn --workers 3 --bind 0.0.0.0:8000 --worker-tmp-dir /dev/shm --access-logfile - \"$WSGI_APP\""]
