#!/bin/sh
set -e

# Applique les migrations à chaque démarrage (idempotent) : une nouvelle image
# met donc la base à jour automatiquement.
python manage.py migrate --noinput

# Création optionnelle du premier administrateur (ignorée s'il existe déjà).
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py createsuperuser --noinput 2>/dev/null \
        && echo "Superutilisateur $DJANGO_SUPERUSER_USERNAME créé." \
        || echo "Superutilisateur $DJANGO_SUPERUSER_USERNAME déjà présent."
fi

exec "$@"
