#!/bin/sh
# Copie quotidienne de la base, puis récupère la dernière image publiée sur GHCR et redémarre
# le conteneur si elle a changé (le redémarrage applique les migrations, après une copie de la base).
# À placer à côté du docker-compose.yml, en cron (comme Juliettia) :
#   */5 * * * * cd ~/tp-formation-suivi && ./update.sh >> update.log 2>&1
set -eu
cd "$(dirname "$0")"

# Une copie par jour (premier passage de la journée) ; un échec n'empêche pas la mise à jour.
if [ -n "$(docker compose ps -q web)" ]; then
    docker compose exec -T web python manage.py backup_db --daily \
        || echo "$(date '+%F %T') échec de la sauvegarde quotidienne"
fi

docker compose pull -q web
IMAGE=$(docker compose config --images | head -n 1)
NEW=$(docker image inspect -f '{{.Id}}' "$IMAGE")
CONTAINER=$(docker compose ps -q web)
RUNNING=$(if [ -n "$CONTAINER" ]; then docker inspect -f '{{.Image}}' "$CONTAINER"; fi)

[ "$NEW" = "$RUNNING" ] && exit 0

echo "$(date '+%F %T') nouvelle image $IMAGE ($NEW)"
docker compose up -d
docker image prune -f > /dev/null
