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
python manage.py make_superadmin <username> [--remove]   # give / remove super-admin rights (refuses to remove the last one)
python manage.py makemigrations userManagement clubs formation suivi
python manage.py test
```

Settings require `SECRET_KEY` unless `DEBUG=True` (dev). `DATABASE_URL` is optional (SQLite by default ; PostgreSQL would need a driver such as `psycopg` added back to the dependencies).

Migrations: a single `0001_initial` per app (squashed before the first deployment); add new migrations on top from now on. `suivi/0008_comment` copies the former per-model comments (attendance, worked skill, student note, skill evaluation) into `Comment`; `suivi/0009` and `formation/0004` then drop the old fields and `StudentNote`.
`clubs/0002_default_club` crée le club par défaut « Club » (renommable dans l'admin Django) ; `formation/0005_club` et `suivi/0010_club` y rattachent les données existantes.
`clubs/0004_memberships_from_groups` turns the former role groups into memberships of the default club (superusers become its admins) and deletes the groups.
`userManagement/0002_create_initial_admin` creates the first superuser (super-admin) from `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` / `_EMAIL` when set and the account does not exist; skipped during `manage.py test` (`settings.TESTING`).

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

- **`clubs/`** — `Club` (organisation). Passage au multi-club en cours : `Season`, `Cursus`, `Formation`, `Member` et `TrainingSession` ont une clé `club` (suppression en cascade ; `Club.delete` supprime d'abord les formations, protégées par leur cursus). Les autres modèles en héritent par leurs relations. `Membership` (compte × club × rôle `Role`, unique) : rôle d'un compte dans chaque club ; un superutilisateur (super-admin) a accès à tous les clubs comme administrateur. Club actif : `request.club` et `request.user.active_club` (`clubs.middleware.ActiveClubMiddleware`, parmi `user.clubs()` : club de la session `club_id`, sinon `user.last_club`, sinon le premier par nom ; None si le compte n'a aucun club). Choix du club : `/clubs/choisir/` (`club-choose`, `set_active_club` : session + `last_club`), sélecteur dans la barre de navigation si le compte a plusieurs clubs (`clubs.context_processors.user_clubs`) ; l'accueil redirige vers le choix tant qu'aucun club n'a été choisi. `user.role` / `is_administrator` / `is_club_staff` / `student_profile` s'entendent dans le club actif ; pour un autre compte, `role_in(club)`. `only_in_club(club)` : compte qui ne sert dans aucun autre club — seul un tel compte est géré par le club (email modifiable depuis la fiche, mot de passe, lien d'invitation, suppression) ; un compte partagé avec un autre club passe par un super-admin. Le modèle `club` vaut par défaut le club par défaut (`get_default_club`) ; les vues passent toujours le club actif. Toutes les vues, formulaires (choix proposés) et exports filtrent sur `request.club` (objet d'un autre club → 404) et créent dans ce club ; les formulaires reçoivent le club par leur instance (`StudentForm(instance=Member(club=…))`, `FormationForm`, `TrainingSessionForm`) ou un argument (`StudentImportForm(club=…)`, `QuickStudentForm.save(club=…)`). Tests d'isolation : `clubs/tests.py` (`ClubIsolationTestCase`). Comptes : encadrants proposés (`staff_users(club)`), comptes rattachables (`attachable_accounts(club)`) et page Utilisateurs limités au club ; rôles par club : `MultiClubRolesTestCase`. Outil de test : `clubs.testing.add_role(user, role, club=None)`. Gestion des clubs (super-admin, `superadmin_required`) : `/clubs/` liste (élèves, équipe, formations en cours), création avec premier administrateur facultatif (`club-create` ; `add_club_admin` : compte existant promu administrateur, sinon invitation), page d'un club (`club-detail` : renommer, nommer / retirer des administrateurs avec liens d'invitation, ouvrir le club), suppression définitive en retapant le nom (`club-delete`), refusée pour le dernier club ou s'il reste des élèves en formation (`_deletion_blocker`) ; les comptes sont conservés. Lien « Clubs » et libellé « Super-admin » dans la navigation.
- **`formation/`** — Référentiel : `Season`, `Cursus` → `CursusCategory` → `Skill`. `Formation` (instance d'un cursus : nom, dates, `managers`, statut en cours / terminée ; indépendante des saisons), `Enrollment` (inscription élève × formation, statut `active` / `completed` / `dropped`), `Member` (élève d'un club : `user` facultatif, au plus une fiche par compte et par club, `related_name='student_profiles'` ; `cursus_ids()` = cursus de ses inscriptions hors abandon), `MemberSkill` (statut courant d'une compétence pour un élève), `SkillEvaluation` (historique des changements de statut, avec `author` ; sans commentaire, voir `suivi.Comment`). Vues : saisons et cursus (admin, `/gestion/` ; import JSON et export en fichier `.json` réimportable, `saison-cursus-export` ; suppression définitive `saison-cursus-supprimer`, avec ses formations, seulement si aucun élève n'y est inscrit — même abandon — ni n'a de suivi sur ses compétences, `Cursus.is_deletable` / `in_use_ids`), formations et inscriptions (`/formations/` : liste/détail staff, création/modification/clôture admin), création/modification d'élève, page d'évaluation et export PDF (`/eleves/`). Fiche d'évaluation vierge en PDF (cases à cocher par statut, à imprimer ; `_build_evaluation_pdf` sans élève) pour un cursus (`saison-cursus-fiche-vierge`) ou une formation (`formation-fiche-vierge`, avec nom et dates), ouverte aux encadrants. L'email de l'élève est facultatif : renseigné, il rattache le compte existant de cet email s'il n'a pas de fiche dans ce club (encadrant du club, élève d'un autre club : mêmes identifiants, message neutre qui ne révèle pas l'autre club, `shared_account_notice`), sinon crée un compte inactif avec lien d'invitation (`formation.views.attach_account` → `create_invited_user(email, club, role)`) ; le compte devient membre élève du club s'il ne l'était pas. L'email ne peut plus être retiré ensuite. Création à partir d'un compte existant sans fiche (champ « À partir d'un compte existant » de `StudentForm`, ou `/eleves/nouveau/?user=<pk>` ; `attachable_accounts()` = comptes actifs ou invitations élève : une invitation encadrant / admin en attente n'est jamais rattachable, et un encadrant ne voit que les liens d'invitation des comptes élèves, `can_view_invitation`) : prénom / nom repris du compte, email verrouillé, fiche rattachée directement au compte. Création rapide sans compte (`QuickStudentForm`) depuis une formation ou une séance. Import de plusieurs élèves (`/eleves/importer/`, `StudentImportForm`) : une ligne « Nom ; Prénom ; Email » (email facultatif, séparateurs `;` `,` ou tabulation, en-tête ignoré), inscription facultative à une formation, tout ou rien en cas d'erreur. Suppression d'une fiche depuis son formulaire de modification (`eleve-delete`, staff) : supprime tout le suivi et le compte rattaché s'il est élève de ce club seulement (`deletes_student_account`, `manages_account`) ; un compte encadrant / admin ou partagé avec un autre club est conservé (un élève perd alors son rôle dans le club).
- **`suivi/`** — `TrainingSession` (séance : date, saison, `formations` travaillées, encadrants), `Attendance` (présent / absent, unique par séance × élève), `WorkedSkill` (compétence travaillée par un élève lors d'une séance, unique par séance × élève × compétence, évaluation du jour optionnelle, `author`), `Comment` (voir ci-dessous). Élèves attendus à une séance (`roster`) = inscrits `active` à l'une de ses formations + présences déjà saisies ; « en formation » = inscription `active` à une formation en cours. La saison ne sert qu'à regrouper les séances. Une évaluation saisie en séance (changement de statut) met à jour `MemberSkill` et crée une `SkillEvaluation` (date = date de la séance). « Mon suivi » (`/suivi/mon-suivi/`, consultation uniquement) affiche la fiche du compte connecté dans le club actif (`user.student_profile`).
  - **Commentaires** : modèle unique `Comment` (`member`, `session` et `skill` facultatifs et indépendants, `date`, `content`, `staff_only`, `author`). `staff_only` = « 🔒 Note équipe », jamais montrée à l'élève (`Comment.objects.visible_to_student()` ; « Mon suivi » et export PDF). Plusieurs commentaires possibles par séance × élève × compétence. Saisie via le gabarit partagé `templates/_comment_fields.html` (champ visible + 🔒 déplié au clic, noms `<prefix>_<pk>_comment` / `_staff_comment`) : chaque champ rempli crée son propre commentaire (`suivi.forms.add_comments`). Points de saisie : appel (séance), compétences travaillées (séance + compétence ; un commentaire marque la compétence travaillée), page d'évaluation (compétence sans séance), onglet « Commentaires » de la fiche élève (`CommentForm`, séance et compétence au choix). Affichage : `templates/_comment.html` (boutons ✏️ modifier, 🔒/👁 et ✕ → `suivi-comment`, ouverts à tout encadrant, `?next=` pour le retour ; `in_form` = boutons `formaction` dans un formulaire englobant, sinon formulaire propre via l’attribut `form=`). Section « Compétences » (`suivi/_skills_progress.html`) : menu déroulant par compétence avec tous ses commentaires (séance ou hors séance, plus récents d'abord). Supprimer une séance conserve ses commentaires (`session` → NULL).
- **`userManagement/`** — `CustomUser` (`role`, `role_label`, `is_administrator`, `is_club_staff` dans le club actif, `role_in(club)`, `clubs()`, `only_in_club(club)`, `last_club`), `Role` (3 rôles, portés par `clubs.Membership`), inscription uniquement sur invitation (lien généré, pas d'email envoyé ; le rôle dans le club actif est choisi à l'invitation ; inviter l'email d'un compte existant l'ajoute au club sans lien d'invitation ; page Utilisateurs = membres du club actif, « Retirer du club » ne supprime que les comptes sans autre club ; `userManagement.adapters.InvitationOnlyAccountAdapter` ferme l'inscription allauth). Seules les pages allauth de connexion / déconnexion sont servies (`config/urls.py`) ; la connexion à l'admin Django passe par elles (limitation des tentatives, compteurs dans le cache fichier `CACHE_DIR`). Un superutilisateur n'est géré (rôle, suppression, réinitialisation) que par un superutilisateur (`can_manage_account`). Une fiche élève rattachée à un compte encadrant / admin ne modifie pas l'email de ce compte (`StudentForm.manages_account_email`). Mot de passe oublié : lien de réinitialisation généré par un admin du club (comptes du club seulement) ou un encadrant (comptes élèves du club seulement, depuis la fiche), ou par un super-admin (tout compte) — `can_reset_password(actor, target, club)`, `default_token_generator`, 7 jours, usage unique. Liens d'invitation : `can_view_invitation(actor, target, club)` (mêmes restrictions).
- **`config/`** — settings, URLs, ASGI/WSGI.

### Interface

- Navigation encadrants : Séances · Élèves · Formations (barre du haut ; sur mobile, barre d'onglets en bas d'écran avec « Plus » pour le reste du menu). `active_tab` dans le contexte marque l'onglet actif.
- Présences : vue « Présences » de la liste des élèves (`/suivi/eleves/?vue=presences`, l'ancienne `/suivi/presences/` y redirige) et section « Présences » du détail de formation ; gabarit partagé `suivi/_attendance_matrix.html` (tableau sur ordinateur, cartes à pastilles sur mobile), données via `suivi.views.attendance_matrix`.
- Fiche élève (`/suivi/eleves/<pk>/`, `suivi/student_detail.html`) : onglet par défaut « Vue d'ensemble » (statistiques de présence, résumé par formation, pastilles et dernières séances), puis Présences · Compétences · Commentaires · Informations (onglets par ancre `#resume`, `#presences`…).
- CSS dans `static/app.css` (chargé par `templates/base.html`, pas de `<style>` dans les gabarits). Valeurs saisies dans un attribut `onclick` / `onsubmit` : toujours `|escapejs`.
- Application installable (PWA légère, sans service worker) : `static/manifest.webmanifest`, icônes dans `static/` (`STATICFILES_DIRS`).

### Role System

Rôles par club (`clubs.Membership.role`) ; un compte peut avoir un rôle différent dans chaque club.

| Rôle | Label | Accès (dans le club actif) |
|--------|-------|-------|
| `student` | Élève | « Mon suivi » en lecture seule |
| `instructor` | Encadrant | Séances, élèves, évaluations (`club_staff_required`) |
| `admin` | Administrateur | Tout + saisons/formations + utilisateurs du club |
| superutilisateur | Super-admin | Administrateur de tous les clubs, admin Django (clubs et membres) |

`admin_required` / `AdminRequiredMixin` → rôle `admin` dans le club actif (ou superuser) ; `club_staff_required` / `ClubStaffRequiredMixin` → `instructor`, `admin` (`STAFF_ROLES`).

### URL Structure

| Prefix | Contenu |
|---|---|
| `/` | Accueil |
| `/suivi/` | séances, présences, liste et fiche élève (staff) ; `mon-suivi/` (élève) |
| `/formations/` | formations et inscriptions (staff ; création / modification admin) |
| `/eleves/` | création / import / modification / suppression d'élève, évaluation, export PDF (staff) |
| `/gestion/` | saisons et cursus (admin) |
| `/users/` | utilisateurs et invitations du club (admin) |
| `/clubs/` | choix du club actif (`choisir/`) ; gestion des clubs (super-admin) |
| `/accounts/`, `/admin/` | allauth (connexion / déconnexion), Django admin |
