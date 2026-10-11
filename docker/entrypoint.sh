#!/bin/sh
set -e

# Applique les migrations à chaque démarrage (idempotent) : une nouvelle image
# met donc la base à jour automatiquement. Sur une base neuve, la migration
# userManagement 0002 crée le premier administrateur (DJANGO_SUPERUSER_*).
python manage.py migrate --noinput

exec "$@"
