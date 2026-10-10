# Déploiement sur un serveur (Docker)

L'application tourne dans un conteneur Docker construit par GitHub Actions et publié sur
GitHub Container Registry : `ghcr.io/bertrandmiannay/tp-formation-suivi`.
Le serveur n'a besoin ni de Python ni du code source : seulement Docker, `docker-compose.yml`, un `.env` et nginx.

## 1. Publier l'image

Sur GitHub : **Actions → Publish Docker image → Run workflow** (branche `main`).
Deux tags sont publiés : `latest` et `sha-<commit>`.

> Le dépôt étant privé, le package GHCR l'est aussi. Deux options :
> - le rendre public (GitHub → Packages → tp-formation-suivi → Package settings → Change visibility) :
>   aucun login nécessaire sur le serveur, comme pour Juliettia ;
> - ou le laisser privé et se connecter une fois sur le serveur avec un token GitHub
>   (classic PAT, scope `read:packages`) :
>   `echo <TOKEN> | docker login ghcr.io -u BertrandMiannay --password-stdin`

## 2. Installer sur le serveur

Prérequis : Docker (avec le plugin compose) et nginx.

```bash
mkdir -p ~/tp-formation-suivi && cd ~/tp-formation-suivi
# récupérer docker-compose.yml et .env.example depuis le dépôt (scp, ou copier-coller)
cp .env.example .env
nano .env   # SECRET_KEY, ALLOWED_HOSTS, premier administrateur
docker compose pull
docker compose up -d
docker compose logs -f      # « Listening at: http://0.0.0.0:8000 »
```

Au démarrage, le conteneur applique les migrations puis crée l'administrateur défini dans `.env`
s'il n'existe pas encore (retirer ensuite `DJANGO_SUPERUSER_PASSWORD` du fichier).

L'application écoute sur `127.0.0.1:8000` (modifiable via `APP_PORT`), uniquement en local.

## 3. Nginx et HTTPS

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/tp-formation-suivi   # adapter server_name
sudo ln -s /etc/nginx/sites-available/tp-formation-suivi /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d <domaine>
```

Les cookies de session sont en mode `Secure` dès que `DEBUG=False` : l'application doit être servie en HTTPS.

## Mise à jour

1. Publier une nouvelle image (étape 1).
2. Sur le serveur :

```bash
cd ~/tp-formation-suivi
docker compose pull && docker compose up -d
docker image prune -f        # facultatif : supprime les anciennes images
```

Les migrations sont appliquées automatiquement au redémarrage du conteneur.

**Revenir à une version précédente** : `IMAGE_TAG=sha-<commit> docker compose up -d`
(attention : une migration déjà appliquée n'est pas annulée).

## Données et sauvegarde

La base SQLite est dans le volume Docker `tp-formation-suivi_data` (monté sur `/data`).
Elle survit aux mises à jour et aux `docker compose down` (mais pas à `down -v`).

```bash
# sauvegarde à chaud, copiée sur l'hôte
docker compose exec web python -c "import sqlite3; s=sqlite3.connect('/data/db.sqlite3'); d=sqlite3.connect('/data/backup.sqlite3'); s.backup(d)"
docker compose cp web:/data/backup.sqlite3 ./backup-$(date +%F).sqlite3
```

## Commandes utiles

```bash
docker compose logs -f                                   # logs
docker compose ps                                        # état
docker compose restart                                   # redémarrer
docker compose exec web python manage.py createsuperuser # créer un administrateur
docker compose exec web python manage.py shell           # shell Django
```

## Construire l'image localement

```bash
docker compose build && docker compose up -d
```
