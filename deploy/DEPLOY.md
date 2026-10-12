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
curl -fsSL  $BASE/deploy/update.sh  -o update.sh && chmod +x update.sh
cp .env.example .env && chmod 600 .env
# SECRET_KEY obligatoire (sinon le conteneur s'arrête au démarrage → 502) ; ne plus la changer ensuite
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')|" .env
nano .env   # premier administrateur (DJANGO_SUPERUSER_*)
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
# a. Archiver l'ancienne base : DATABASE_URL de /etc/helloasso/env si défini,
#    sinon db.sqlite3 à la racine du dossier de l'app (WorkingDirectory du service)
grep DATABASE_URL /etc/helloasso/env || grep WorkingDirectory /etc/systemd/system/helloasso.service
cp ~/helloAssoManager/db.sqlite3 ~/helloasso-db-$(date +%F).sqlite3

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

- **HSTS** : actif par défaut en production (1 an, envoyé uniquement sur les réponses HTTPS). Les navigateurs refusent
  ensuite tout accès en HTTP au domaine : garder le renouvellement Let's Encrypt en place. Pour le couper,
  `SECURE_HSTS_SECONDS=0` dans `.env` puis `docker compose up -d`.
- **Mise à jour automatique** (comme Juliettia) : `crontab -e` puis
  ```cron
  */5 * * * * cd ~/tp-formation-suivi && ./update.sh >> update.log 2>&1
  ```

## Comptes et mots de passe

Aucun email n'est envoyé par l'application.

- **Invitation** : lien généré à la création du compte (Utilisateurs → Inviter, ou fiche élève), valable 7 jours.
- **Mot de passe oublié** : un administrateur (Utilisateurs → « Réinitialiser le mot de passe ») ou un encadrant
  (fiche élève, comptes élèves uniquement) génère un lien à transmettre. Valable 7 jours, une seule fois.

## Mise à jour

Publier une nouvelle image (étape 1) : dans les 5 minutes, le cron lance `update.sh`, qui récupère l'image et,
si elle a changé, redémarre le conteneur (les migrations s'appliquent) et supprime les anciennes images.
Suivi : `tail update.log` et `docker compose ps`. Pour forcer sans attendre : `./update.sh`.

Il n'y a pas de retour arrière automatique : si le conteneur ne passe pas `healthy`, voir `docker compose logs`.

**Revenir à une version précédente** : mettre `IMAGE_TAG=sha-<commit>` dans `.env` puis `./update.sh`
(le cron reste alors sur cette version ; remettre `latest` ensuite). Une migration déjà appliquée n'est pas annulée.

## Données

La base SQLite est dans le volume Docker `tp-formation-suivi_data` (monté sur `/data`).
Elle survit aux mises à jour et aux `docker compose down` (mais pas à `down -v`).

### Sauvegardes

`python manage.py backup_db` copie la base à chaud (API de sauvegarde SQLite) dans `/data/backups`
(`BACKUP_DIR` pour changer de dossier) et ne garde que les 14 copies les plus récentes (`--keep`).

- **Avant chaque migration** : le conteneur fait lui-même une copie `…-avant-migration.sqlite3` (5 conservées)
  quand une nouvelle image apporte des migrations.
- **Chaque nuit** : `crontab -e` sur l'hôte, puis
  ```cron
  17 3 * * * cd ~/tp-formation-suivi && docker compose exec -T web python manage.py backup_db >> backup.log 2>&1
  ```
- **Hors du serveur** : les copies restent dans le volume Docker, sur le même disque. Les rapatrier régulièrement
  (données personnelles d'élèves : stockage chiffré), par exemple depuis un autre poste :
  ```bash
  ssh serveur 'cd ~/tp-formation-suivi && docker cp "$(docker compose ps -q web)":/data/backups -' | tar -x -C ~/sauvegardes-suivi
  ```

**Restaurer une copie** :

```bash
docker compose exec web ls /data/backups                         # choisir la copie
docker compose stop web
docker compose run --rm --no-deps --entrypoint sh web -c \
  'cp /data/db.sqlite3 /data/db-avant-restauration.sqlite3 && rm -f /data/db.sqlite3-wal /data/db.sqlite3-shm \
   && cp /data/backups/<copie>.sqlite3 /data/db.sqlite3'
docker compose up -d
```

Une copie `avant-migration` restaurée sur une image plus récente serait aussitôt re-migrée : remettre d'abord
`IMAGE_TAG=sha-<commit précédent>` dans `.env` (voir « Revenir à une version précédente »).

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
