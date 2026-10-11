# Déploiement sur le serveur (Docker)

URL de production : **https://botouraineplongee.ddns.net**

L'application tourne dans un conteneur Docker construit par GitHub Actions et publié sur
GitHub Container Registry : `ghcr.io/bertrandmiannay/tp-formation-suivi` (même principe que Juliettia).
Le serveur n'a besoin ni de Python ni du code source : seulement Docker, `docker-compose.yml`, un `.env` et nginx.

Elle **remplace helloAssoManager** (service systemd `helloasso` + gunicorn sur socket + site nginx `helloasso`),
sur le même domaine et avec le même certificat Let's Encrypt. Les données d'helloAssoManager ne sont pas reprises :
les élèves sont créés directement dans l'application.

## 1. Publier l'image

Sur GitHub : **Actions → Publish Docker image → Run workflow** (branche `main`).
Deux tags sont publiés : `latest` et `sha-<commit>`.

> Le dépôt est public : l'image peut l'être aussi, et le serveur la récupère alors sans login.
> Après la **première** publication, vérifier sur GitHub → Packages → `tp-formation-suivi` → Package settings
> que la visibilité est « Public » (sinon « Change visibility » → Public). Les publications suivantes la conservent.

## 2. Installer sur le serveur (sans couper helloAssoManager)

Prérequis : Docker avec le plugin compose (`docker compose version`). Nginx et certbot sont déjà en place.

```bash
mkdir -p ~/tp-formation-suivi && cd ~/tp-formation-suivi
BASE=https://raw.githubusercontent.com/BertrandMiannay/Tp-formation-suivi/main
curl -fsSLO $BASE/docker-compose.yml
curl -fsSLO $BASE/.env.example
curl -fsSL  $BASE/deploy/nginx.conf -o nginx.conf
curl -fsSL  $BASE/deploy/backup.sh  -o backup.sh && chmod +x backup.sh
cp .env.example .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # → SECRET_KEY
nano .env   # SECRET_KEY, premier administrateur (DJANGO_SUPERUSER_*)
docker compose pull
docker compose up -d
docker compose ps           # STATUS « healthy » au bout de ~30 s
curl -s -H 'Host: botouraineplongee.ddns.net' http://127.0.0.1:8000/health/   # → ok
```

Au démarrage, le conteneur applique les migrations ; sur une base neuve, une migration crée l'administrateur défini
dans `.env` s'il n'existe pas encore. **Retirer ensuite `DJANGO_SUPERUSER_PASSWORD` du fichier.**

L'application écoute sur `127.0.0.1:8000` (modifiable via `APP_PORT`, à reporter dans `nginx.conf`), uniquement en local.
Vérifier avant que le port est libre : `ss -ltnp | grep 8000`.

## 3. Bascule : helloAssoManager → Tp-formation-suivi

```bash
# a. Archiver l'ancienne base (chemin : DATABASE_URL dans /etc/helloasso/env)
grep DATABASE_URL /etc/helloasso/env
sudo cp <chemin>/db.sqlite3 ~/helloasso-db-$(date +%F).sqlite3

# b. Arrêter l'ancien service
sudo systemctl disable --now helloasso

# c. Remplacer le site nginx (le certificat existant est réutilisé)
sudo cp /etc/nginx/sites-available/helloasso ~/helloasso-nginx.conf.bak
sudo rm /etc/nginx/sites-enabled/helloasso
sudo cp nginx.conf /etc/nginx/sites-available/tp-formation-suivi
sudo ln -s /etc/nginx/sites-available/tp-formation-suivi /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Vérifier : https://botouraineplongee.ddns.net/health/ → `ok`, puis connexion avec l'administrateur.

Les chemins `/etc/letsencrypt/options-ssl-nginx.conf` et `ssl-dhparams.pem` ont été créés par `certbot --nginx` ;
s'ils n'existent pas, retirer les deux lignes correspondantes de `nginx.conf`.
Le renouvellement du certificat (timer certbot) continue de fonctionner avec le nouveau site.

**Retour arrière** (si besoin) :

```bash
sudo rm /etc/nginx/sites-enabled/tp-formation-suivi
sudo ln -s /etc/nginx/sites-available/helloasso /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl enable --now helloasso
```

**Nettoyage** (une fois la nouvelle application validée, quelques semaines plus tard) :

```bash
sudo rm /etc/systemd/system/helloasso.service && sudo systemctl daemon-reload
sudo rm /etc/nginx/sites-available/helloasso
sudo rm -r /etc/helloasso ~/helloAssoManager      # garder l'archive de la base
```

## 4. Après la bascule

- **HSTS** : une fois le HTTPS vérifié, ajouter `SECURE_HSTS_SECONDS=31536000` dans `.env` puis `docker compose up -d`.
  Les navigateurs refuseront ensuite tout accès en HTTP pendant un an : ne l'activer que si le HTTPS est durable.
- **Sauvegardes** : `crontab -e` puis
  `15 3 * * * cd ~/tp-formation-suivi && ./backup.sh >> backups/backup.log 2>&1`
  (copie quotidienne dans `~/tp-formation-suivi/backups/`, 30 dernières conservées). Penser à copier ce dossier hors du serveur.

## Comptes et mots de passe

Aucun email n'est envoyé par l'application.

- **Invitation** : lien généré à la création du compte (Utilisateurs → Inviter, ou fiche élève), valable 7 jours.
- **Mot de passe oublié** : un administrateur (Utilisateurs → « Réinitialiser le mot de passe ») ou un encadrant
  (fiche élève, comptes élèves uniquement) génère un lien à transmettre. Valable 7 jours, une seule fois.

## Mise à jour

1. Publier une nouvelle image (étape 1).
2. Sur le serveur :

```bash
cd ~/tp-formation-suivi
./backup.sh                  # conseillé avant une mise à jour
docker compose pull && docker compose up -d
docker image prune -f        # facultatif : supprime les anciennes images
```

Les migrations sont appliquées automatiquement au redémarrage du conteneur.

**Revenir à une version précédente** : `IMAGE_TAG=sha-<commit> docker compose up -d`
(attention : une migration déjà appliquée n'est pas annulée → restaurer la sauvegarde si besoin).

## Données et sauvegarde

La base SQLite est dans le volume Docker `tp-formation-suivi_data` (monté sur `/data`).
Elle survit aux mises à jour et aux `docker compose down` (mais pas à `down -v`).

Sauvegarde manuelle : `./backup.sh` (voir le script). Restauration :

```bash
docker compose stop
docker compose cp backups/db-<date>.sqlite3 web:/data/db.sqlite3
docker compose run --rm --entrypoint sh web -c 'rm -f /data/db.sqlite3-wal /data/db.sqlite3-shm'
docker compose up -d
```

## Commandes utiles

```bash
docker compose logs -f                                   # logs
docker compose ps                                        # état (healthy / unhealthy)
docker compose restart                                   # redémarrer
docker compose exec web python manage.py createsuperuser # créer un administrateur
docker compose exec web python manage.py changepassword <utilisateur>
docker compose exec web python manage.py shell           # shell Django
```

## Construire l'image localement

```bash
docker compose build && docker compose up -d
```
