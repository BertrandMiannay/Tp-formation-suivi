#!/bin/sh
set -e

# Copie de la base avant d'appliquer de nouvelles migrations (retour arrière possible si
# une migration se passe mal) ; rien n'est fait quand la base est déjà à jour.
if ! python manage.py migrate --check > /dev/null 2>&1; then
    python manage.py backup_db --label avant-migration --keep 5
fi

# Applique les migrations à chaque démarrage (idempotent) : une nouvelle image
# met donc la base à jour automatiquement. Sur une base neuve, la migration
# userManagement 0002 crée le premier administrateur (DJANGO_SUPERUSER_*).
python manage.py migrate --noinput

exec "$@"
