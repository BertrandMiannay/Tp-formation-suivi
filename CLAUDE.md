# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Django 5.2 web application for tracking diving students (élèves) through their training: weekly sessions,
attendance, skills worked/validated per session and per student, and notes. Managed with Poetry (Python 3.13).
Forked from TP-manager; students are created directly in the app (no external import).

## Commands

```bash
poetry install
python manage.py migrate
python manage.py runserver
python manage.py init_dev_db          # reset dev DB + superuser (DJANGO_SUPERUSER_*, default admin/admin) ; DEBUG=True only
python manage.py makemigrations userManagement formation suivi
python manage.py test
```

Settings require `SECRET_KEY` unless `DEBUG=True` (dev). `DATABASE_URL` is optional (SQLite by default ; PostgreSQL would need a driver such as `psycopg` added back to the dependencies).

Migrations: a single `0001_initial` per app (squashed before the first deployment); add new migrations on top from now on.
`userManagement/0002_create_initial_admin` creates the first superuser (group `admin`) from `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` / `_EMAIL` when set and the account does not exist; skipped during `manage.py test` (`settings.TESTING`).

## Git conventions

- Commit messages, PR titles and PR descriptions are written in **English** (the UI and code comments stay in French).
- Never commit directly to `main`: work on a branch, open a pull request, and merge it with **squash and merge** so that each PR is a single commit on `main` (title = PR title, body = summary of the change).
- `main` history = one initial commit (snapshot of TP-manager at the fork) followed by one commit per merged PR. Do not rewrite `main` (no force push) unless explicitly asked. The history before the rewrite is kept in the `archive/main-before-rewrite` branch.
- Commit messages: imperative subject line under ~72 characters, blank line, then a short bullet list of what changed and why.

## Docker / déploiement

- `Dockerfile` (python:3.13-slim en deux étapes : Poetry installe les dépendances dans `/app/.venv`, seule cette venv est copiée dans l'image finale ; `collectstatic` au build, utilisateur non-root, SQLite dans le volume `/data`).
- `docker/entrypoint.sh` : `migrate` à chaque démarrage, puis gunicorn.
- `docker-compose.yml` : service `web`, image `ghcr.io/bertrandmiannay/tp-formation-suivi:${IMAGE_TAG:-latest}`, port `127.0.0.1:${APP_PORT:-8000}`, nginx sur l'hôte (`deploy/nginx.conf`).
- `.github/workflows/docker-publish.yml` (manuel) publie `latest` + `sha-<commit>` et passe `APP_VERSION` (n° d'exécution, commit court, date) en build-arg, affichés sur la page Utilisateurs (admin ; « dev » en local) ; `ci.yml` : tests, check migrations, build image.
- Production : https://botouraineplongee.ddns.net (remplace helloAssoManager sur le même serveur). `HEALTHCHECK` sur `/health/`, mise à jour automatique `deploy/update.sh` (cron hôte toutes les 5 min : pull, redémarrage si l'image a changé), SQLite en WAL.
- Mise à jour serveur : `docker compose pull && docker compose up -d`. Voir `deploy/DEPLOY.md`.

## Architecture

### Django Apps

- **`formation/`** — Référentiel : `Season`, `Cursus` → `CursusCategory` → `Skill`. `Formation` (instance d'un cursus : nom, dates, `managers`, statut en cours / terminée ; indépendante des saisons), `Enrollment` (inscription élève × formation, statut `active` / `completed` / `dropped`), `Member` (élève : OneToOne facultatif vers le compte `user` ; `cursus_ids()` = cursus de ses inscriptions hors abandon), `MemberSkill` (statut courant d'une compétence pour un élève), `SkillEvaluation` (historique, avec `author`). Vues : saisons et cursus (admin, `/gestion/` ; import JSON et export en fichier `.json` réimportable, `saison-cursus-export` ; suppression définitive `saison-cursus-supprimer`, avec ses formations, seulement si aucun élève n'y est inscrit — même abandon — ni n'a de suivi sur ses compétences, `Cursus.is_deletable` / `in_use_ids`), formations et inscriptions (`/formations/` : liste/détail staff, création/modification/clôture admin), création/modification d'élève, page d'évaluation et export PDF (`/eleves/`). L'email de l'élève est facultatif : renseigné, il crée un compte inactif avec lien d'invitation (`formation.views.attach_account` → `create_invited_user`, groupe `student`) ; il ne peut plus être retiré ensuite. Création à partir d'un compte existant sans fiche (champ « À partir d'un compte existant » de `StudentForm`, ou `/eleves/nouveau/?user=<pk>`) : prénom / nom repris du compte, email verrouillé, fiche rattachée directement au compte. Création rapide sans compte (`QuickStudentForm`) depuis une formation ou une séance. Import de plusieurs élèves (`/eleves/importer/`, `StudentImportForm`) : une ligne « Nom ; Prénom ; Email » (email facultatif, séparateurs `;` `,` ou tabulation, en-tête ignoré), inscription facultative à une formation, tout ou rien en cas d'erreur. Suppression d'une fiche depuis son formulaire de modification (`eleve-delete`, staff) : supprime tout le suivi et le compte rattaché s'il est élève (`deletes_student_account`) ; un compte encadrant / admin est conservé.
- **`suivi/`** — `TrainingSession` (séance : date, saison, `formations` travaillées, encadrants), `Attendance` (présent / absent / excusé, unique par séance × élève), `WorkedSkill` (compétence travaillée par un élève lors d'une séance, unique par séance × élève × compétence, évaluation du jour optionnelle, `author`), `StudentNote` (visibilité `staff` ou `student`). Élèves attendus à une séance (`roster`) = inscrits `active` à l'une de ses formations + présences déjà saisies ; « en formation » = inscription `active` à une formation en cours. La saison ne sert qu'à regrouper les séances. Une évaluation saisie en séance met à jour `MemberSkill` et crée une `SkillEvaluation` (date = date de la séance). « Mon suivi » (`/suivi/mon-suivi/`, consultation uniquement) affiche la fiche rattachée au compte connecté (`user.student_profile`) et n'affiche que les notes `student`.
- **`userManagement/`** — `CustomUser` (`role`, `role_label`, `is_administrator`, `is_club_staff`), `Role` (3 rôles = 3 groupes, créés en `post_migrate`), inscription uniquement sur invitation (lien généré, pas d'email envoyé ; le rôle est choisi à l'invitation ; `userManagement.adapters.InvitationOnlyAccountAdapter` ferme l'inscription allauth). Seules les pages allauth de connexion / déconnexion sont servies (`config/urls.py`) ; la connexion à l'admin Django passe par elles (limitation des tentatives, compteurs dans le cache fichier `CACHE_DIR`). Un superutilisateur n'est géré (rôle, suppression, réinitialisation) que par un superutilisateur (`can_manage_account`). Une fiche élève rattachée à un compte encadrant / admin ne modifie pas l'email de ce compte (`StudentForm.manages_account_email`). Mot de passe oublié : lien de réinitialisation généré par un admin (tout compte) ou un encadrant (comptes élèves, depuis la fiche) — `default_token_generator`, 7 jours, usage unique.
- **`config/`** — settings, URLs, ASGI/WSGI.

### Interface

- Navigation encadrants : Séances · Élèves · Formations (barre du haut ; sur mobile, barre d'onglets en bas d'écran avec « Plus » pour le reste du menu). `active_tab` dans le contexte marque l'onglet actif.
- Présences : vue « Présences » de la liste des élèves (`/suivi/eleves/?vue=presences`, l'ancienne `/suivi/presences/` y redirige) et section « Présences » du détail de formation ; gabarit partagé `suivi/_attendance_matrix.html` (tableau sur ordinateur, cartes à pastilles sur mobile), données via `suivi.views.attendance_matrix`.
- Fiche élève (`/suivi/eleves/<pk>/`, `suivi/student_detail.html`) : onglet par défaut « Vue d'ensemble » (statistiques de présence, résumé par formation, pastilles et dernières séances), puis Présences · Compétences · Notes · Informations (onglets par ancre `#resume`, `#presences`…).
- CSS dans `static/app.css` (chargé par `templates/base.html`, pas de `<style>` dans les gabarits). Valeurs saisies dans un attribut `onclick` / `onsubmit` : toujours `|escapejs`.
- Application installable (PWA légère, sans service worker) : `static/manifest.webmanifest`, icônes dans `static/` (`STATICFILES_DIRS`).

### Role System

| Groupe | Label | Accès |
|--------|-------|-------|
| `student` | Élève | « Mon suivi » en lecture seule |
| `instructor` | Encadrant | Séances, élèves, évaluations (`club_staff_required`) |
| `admin` | Administrateur | Tout + saisons/formations + utilisateurs |

`admin_required` / `AdminRequiredMixin` → groupe `admin` (ou superuser) ; `club_staff_required` / `ClubStaffRequiredMixin` → `instructor`, `admin` (`STAFF_ROLES`).

### URL Structure

| Prefix | Contenu |
|---|---|
| `/` | Accueil |
| `/suivi/` | séances, présences, liste et fiche élève (staff) ; `mon-suivi/` (élève) |
| `/formations/` | formations et inscriptions (staff ; création / modification admin) |
| `/eleves/` | création / import / modification / suppression d'élève, évaluation, export PDF (staff) |
| `/gestion/` | saisons et cursus (admin) |
| `/users/` | utilisateurs et invitations (admin) |
| `/accounts/`, `/admin/` | allauth (connexion / déconnexion), Django admin |
