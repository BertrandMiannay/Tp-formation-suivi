# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Django 5.2 web application for tracking diving students (élèves) through their training: weekly sessions,
attendance, skills worked/validated per session and per student, exercises and notes. Managed with Poetry (Python 3.13).
Forked from TP-manager; the HelloAsso integration has been removed — students are created directly in the app.

## Commands

```bash
poetry install
python manage.py migrate
python manage.py runserver
python manage.py init_dev_db          # reset dev DB + admin/admin superuser
python manage.py makemigrations formation suivi
python manage.py test
```

Settings require `SECRET_KEY` unless `DEBUG=True` (dev). `DATABASE_URL` is optional (SQLite by default).

## Architecture

### Django Apps

- **`formation/`** — Référentiel : `Season`, `Cursus` → `CursusCategory` → `Skill`, `Member` (élève : OneToOne vers le compte utilisateur `user`, M2M `formations` = cursus préparés, M2M `seasons`), `MemberSkill` (statut courant d'une compétence pour un élève), `SkillEvaluation` (historique, avec `author`). Vues : gestion des saisons et cursus (admin, `/gestion/`), création/modification d'élève, page d'évaluation et export PDF (`/eleves/`). Créer un élève crée un compte inactif avec lien d'invitation (`userManagement.views.create_invited_user`, groupe `member`).
- **`suivi/`** — `TrainingSession` (séance : date, saison, cursus préparés, encadrants), `Attendance` (présent / absent / excusé, unique par séance × élève), `WorkedSkill` (compétence travaillée par un élève lors d'une séance, unique par séance × élève × compétence, évaluation du jour optionnelle, `author`), `Exercise`, `StudentNote` (visibilité `staff` ou `student`). Les élèves d'une saison sont les `Member` ayant cette saison et au moins une formation. Une évaluation saisie en séance met à jour `MemberSkill` et crée une `SkillEvaluation` (date = date de la séance). « Mon suivi » (`/suivi/mon-suivi/`) affiche la fiche rattachée au compte connecté (`user.student_profile`) et n'affiche que les notes `student`.
- **`userManagement/`** — `CustomUser`, rôles par groupes, inscription uniquement sur invitation (lien généré, pas d'email envoyé).
- **`config/`** — settings, URLs, ASGI/WSGI.

### Role System

| Groupe | Label | Accès |
|--------|-------|-------|
| `admin` | Administrateur | Tout + saisons/formations + utilisateurs |
| `instructor` | Formateur | Séances, élèves, évaluations (`club_staff_required`) |
| `dive_director` | Directeur de plongée | idem formateur |
| `member` | Élève | « Mon suivi » en lecture seule |

`admin_required` / `AdminRequiredMixin` → groupe `admin` ; `club_staff_required` / `ClubStaffRequiredMixin` → admin, instructor, dive_director.

### URL Structure

| Prefix | Contenu |
|---|---|
| `/` | Accueil |
| `/suivi/` | séances, présences, liste et fiche élève (staff) ; `mon-suivi/` (élève) |
| `/eleves/` | création / modification d'élève, évaluation, export PDF (staff) |
| `/gestion/` | saisons et cursus (admin) |
| `/users/` | utilisateurs et invitations (admin) |
| `/accounts/`, `/admin/` | allauth, Django admin |
