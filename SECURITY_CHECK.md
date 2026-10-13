# Analyse de sécurité — Tp-formation-suivi

**Dernière mise à jour :** 2026-10-13
**Application :** Django 5.2 — suivi des élèves en formation plongée (données saisies dans l'application)
**Périmètre :** Code source, configuration, templates

---

## Légende

| Symbole | Signification |
|---------|--------------|
| ✅ | En place |
| 🟠 | Haute — à corriger rapidement |
| 🟡 | Moyenne — à planifier |
| 🟢 | Faible — à traiter si le temps le permet |

---

## Tableau de bord

| ID | Titre | Statut |
|----|-------|--------|
| S01 | Accès restreint par rôle (élève / encadrant / admin) | ✅ |
| S02 | SECRET_KEY obligatoire en production | ✅ |
| S04 | Cookies de session et CSRF sécurisés en production | ✅ |
| S08 | Jetons d'invitation à durée limitée | ✅ |
| S09 | Journalisation des actions sensibles | ✅ |
| S10 | URL d'invitation non stockée en base | ✅ |
| S12 | Limitation des tentatives de connexion (admin Django compris) | ✅ |
| S13 | Réinitialisation de mot de passe sans email | ✅ |
| S14 | HSTS | ✅ (1 an par défaut en production) |
| S15 | Échappement des données dans le JavaScript des gabarits | ✅ |
| S16 | Règles de robustesse des mots de passe appliquées partout | ✅ |
| S17 | Pages allauth limitées à la connexion / déconnexion | ✅ |
| S18 | Email d'un compte encadrant / admin non modifiable depuis une fiche élève | ✅ |
| S19 | `init_dev_db` refusé hors développement | ✅ |
| S20 | Compte superutilisateur protégé des administrateurs | ✅ |
| S21 | Invitation encadrant / admin en attente inaccessible aux encadrants | ✅ (corrigé le 2026-10-13) |
| S22 | Nom d'utilisateur validé à l'acceptation d'invitation | ✅ (corrigé le 2026-10-13) |
| S23 | Dépendances sans vulnérabilité connue (`pip-audit`) | ✅ (pillow 12.3.0, sqlparse 0.6.0) |
| S24 | Content-Security-Policy | 🟢 absente |
| S25 | Durcissement de la CI GitHub Actions | 🟢 |

---

## Éléments en place

### ✅ S01 — Accès restreint par rôle
Trois rôles, chacun porté par un groupe Django (`userManagement.models.Role`) :

| Groupe | Rôle | Garde |
|--------|------|-------|
| `student` | Élève | « Mon suivi » seulement (fiche rattachée au compte, notes `student` uniquement) |
| `instructor` | Encadrant | `@club_staff_required` / `ClubStaffRequiredMixin` |
| `admin` | Administrateur | `@admin_required` / `AdminRequiredMixin` (+ gardes encadrant) |

Un superutilisateur est traité comme administrateur. Un utilisateur sans rôle requis est redirigé vers l'accueil.

### ✅ S02 — SECRET_KEY obligatoire en production
En `DEBUG=False`, l'absence de `SECRET_KEY` lève une `RuntimeError` au démarrage. En `DEBUG=True` (dev), une clé locale est utilisée.

### ✅ S04 — Cookies sécurisés en production
```python
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE    = not DEBUG
SESSION_COOKIE_SAMESITE = 'Lax'
```
Derrière nginx, `SECURE_PROXY_SSL_HEADER` indique à Django que la requête d'origine était en HTTPS.

### ✅ S08 — Jetons d'invitation à durée limitée
`invite_expires_at` = création + 7 jours ; `AcceptInviteView` renvoie 404 au-delà. Le jeton est effacé après acceptation. Un encadrant peut régénérer le lien depuis la fiche élève.

### ✅ S09 — Journalisation des actions sensibles
Logs `INFO` : invitation envoyée / acceptée, changement de rôle, suppression de compte, création / modification d'élève, création / suppression de séance, suppression de saison, création / import / archivage de cursus.

### ✅ S10 — URL d'invitation non stockée en base
Seul le jeton (UUID) est stocké ; l'URL est reconstruite à l'affichage.

### ✅ S12 — Limitation des tentatives de connexion
Limites par défaut d'allauth (`login_failed` : 10/min par IP, 5 échecs par compte). Les compteurs sont dans un cache fichier
partagé par les workers gunicorn et conservé aux redémarrages (`CACHE_DIR`, `/data/cache` dans l'image).
La page de connexion de l'admin Django (sans limite) redirige vers celle d'allauth (`config/urls.py`, `admin_login`).

### ✅ S13 — Réinitialisation de mot de passe sans email
Lien généré par un administrateur (tout compte actif) ou un encadrant (comptes élèves uniquement, jamais le sien), via `default_token_generator` :
valable 7 jours (`PASSWORD_RESET_TIMEOUT`), invalidé dès que le mot de passe change ou que l'utilisateur se connecte. Logs `PASSWORD_RESET_LINK` / `PASSWORD_RESET_DONE`.

### ✅ S14 — HSTS
`SECURE_HSTS_SECONDS` vaut 31536000 (1 an) en production, 0 en développement ; `SECURE_HSTS_SECONDS=0` dans `.env` le coupe.
Sans `includeSubDomains` ni `preload` (domaine ddns partagé). La redirection HTTP → HTTPS est faite par nginx (`security.W008` ignoré).

### ✅ S15 — Échappement des données dans le JavaScript des gabarits
Dans un attribut `onclick` / `onsubmit`, l'échappement HTML ne suffit pas (le navigateur décode `&#x27;` avant d'exécuter le script) :
toute valeur saisie (email, nom de saison, de catégorie, de compétence, d'élève) y passe par `|escapejs`.
Un email valide comme `x'-alert`1`-'@a.fr` ne peut donc plus injecter de script dans la page Utilisateurs.

### ✅ S16 — Robustesse des mots de passe
`AUTH_PASSWORD_VALIDATORS` s'applique à l'acceptation d'invitation, au changement (`PasswordChangeForm`) et à la réinitialisation (`SetPasswordForm`).

### ✅ S17 — Pages allauth limitées
Seules `accounts/login/`, `accounts/logout/` et `accounts/inactive/` sont servies ; les autres pages allauth (inscription,
réinitialisation par email, gestion des emails…) répondent 404. L'inscription est fermée (`InvitationOnlyAccountAdapter`).
Le lien de retour de la page « lien de réinitialisation » n'accepte que des URL internes (`url_has_allowed_host_and_scheme`).

### ✅ S18 — Email des comptes encadrant / admin
Une fiche élève peut être rattachée au compte d'un encadrant ou d'un administrateur qui suit une formation, mais l'email
de ce compte n'est alors plus modifiable depuis la fiche (champ désactivé, ignoré côté serveur). Seuls les comptes élèves suivent l'email de leur fiche.

### ✅ S19 — `init_dev_db`
La commande efface la base : elle lève une erreur si `DEBUG` n'est pas activé.

### ✅ S20 — Compte superutilisateur
Un superutilisateur (accès à l'admin Django) n'est géré que par un superutilisateur (`can_manage_account`) : un administrateur ne peut
ni générer son lien de réinitialisation de mot de passe (ce qui lui donnerait l'accès à l'admin Django), ni changer son rôle, ni le supprimer.

### ✅ S21 — Invitation encadrant / admin en attente
**Faille corrigée (escalade de privilèges encadrant → administrateur).** Un compte invité par un administrateur reste
inactif et sans fiche jusqu'à l'acceptation. Un encadrant pouvait créer une fiche élève rattachée à ce compte (liste
« À partir d'un compte existant », ou saisie de son email), puis lire le lien d'invitation sur la fiche élève (ou le régénérer)
et l'accepter lui-même : il obtenait un compte du rôle de l'invitation, administrateur compris.
- `formation.forms.attachable_accounts()` : seuls les comptes actifs et les invitations élève en attente peuvent être rattachés à une fiche.
- L'email d'une invitation encadrant / admin en attente est refusé à la création, à la modification et à l'import d'élèves.
- `can_view_invitation` : un encadrant ne voit (ni ne régénère) que le lien d'invitation d'un compte élève ; un admin voit tous les liens.

### ✅ S22 — Nom d'utilisateur à l'acceptation d'invitation
Le nom d'utilisateur choisi suit les règles de Django (`UnicodeUsernameValidator`, 150 caractères au plus) et son unicité
est vérifiée sans tenir compte de la casse, comme la recherche du compte par allauth à la connexion (« Paul » / « paul »).

### ✅ S23 — Dépendances
`pip-audit` signalait des vulnérabilités dans pillow 12.2.0 (dépendance de reportlab ; aucune image fournie par
l'utilisateur n'est traitée) et sqlparse 0.5.3 (dépendance de Django) : mises à jour vers 12.3.0 et 0.6.0.
À relancer régulièrement : `poetry run pip install pip-audit && poetry run pip-audit`.

---

## Recommandations restantes

### 🟢 S24 — Content-Security-Policy
Aucun en-tête CSP. Les gabarits utilisent des scripts et attributs `onclick` en ligne : une CSP stricte demanderait de
les déplacer dans des fichiers `static/`. Les données sont échappées (S15), le risque XSS résiduel est faible.

### 🟢 S25 — CI GitHub Actions
Les actions sont référencées par version majeure (`@v4`…) plutôt que par SHA, et `ci.yml` ne restreint pas les
`permissions` du jeton (`contents: read` suffirait). Le serveur déploie automatiquement l'image `latest` (`deploy/update.sh`) :
le droit de lancer « Publish Docker image » équivaut à un accès production — à réserver au mainteneur.

---

## Périmètre non couvert

- **Chiffrement des données personnelles en base** (date de naissance, certificat médical, contact d'urgence) — à considérer si la base est sauvegardée hors du serveur.
