#!/bin/sh
set -e

mkdir -p "$DJANGO_MEDIA_ROOT"

echo "[db] migrations"
python manage.py migrate --noinput

# Copie les statiques dans le volume partagé avec le conteneur Nginx.
python manage.py collectstatic --noinput --clear -v 0

exec "$@"
