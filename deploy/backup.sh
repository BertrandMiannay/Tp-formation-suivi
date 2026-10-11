#!/bin/sh
# Sauvegarde à chaud de la base SQLite du conteneur, copiée sur l'hôte.
# À lancer depuis le dossier du docker-compose.yml (ex. ~/tp-formation-suivi), par exemple en cron :
#   15 3 * * * cd ~/tp-formation-suivi && ./backup.sh >> backup.log 2>&1
# Garde les KEEP dernières sauvegardes (30 par défaut).
set -eu

KEEP="${KEEP:-30}"
DEST="${DEST:-backups}"
mkdir -p "$DEST"
FILE="$DEST/db-$(date +%F-%H%M).sqlite3"

docker compose exec -T web python -c "import sqlite3; s=sqlite3.connect('/data/db.sqlite3'); d=sqlite3.connect('/data/backup.sqlite3'); s.backup(d); d.close()"
docker compose cp web:/data/backup.sqlite3 "$FILE"
docker compose exec -T web rm -f /data/backup.sqlite3

ls -1t "$DEST"/db-*.sqlite3 | tail -n +"$((KEEP + 1))" | xargs -r rm -f
echo "$(date '+%F %T') sauvegarde : $FILE"
