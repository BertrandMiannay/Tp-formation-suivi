# Analyse de sécurité — Tp-formation-suivi

**Dernière mise à jour :** 2026-10-11
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
| S12 | Limitation des tentatives de connexion | ✅ (défaut allauth) |
| S13 | Réinitialisation de mot de passe sans email | ✅ |
| S14 | HSTS | 🟡 à activer après bascule (`SECURE_HSTS_SECONDS`) |

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
Limites par défaut d'allauth (`login_failed` : 10/min par IP, 5 échecs par compte). Elles reposent sur le cache Django (mémoire locale par processus gunicorn) : suffisant pour un club, à renforcer (cache partagé, django-axes) si besoin.

### ✅ S13 — Réinitialisation de mot de passe sans email
Lien généré par un administrateur (tout compte actif) ou un encadrant (comptes élèves uniquement, jamais le sien), via `default_token_generator` :
valable 7 jours (`PASSWORD_RESET_TIMEOUT`), invalidé dès que le mot de passe change ou que l'utilisateur se connecte. Logs `PASSWORD_RESET_LINK` / `PASSWORD_RESET_DONE`.

### 🟡 S14 — HSTS
Réglable par `SECURE_HSTS_SECONDS` (0 par défaut). À passer à 31536000 une fois le HTTPS vérifié en production. La redirection HTTP → HTTPS est faite par nginx (`security.W008` ignoré).

---

## Périmètre non couvert

- **Chiffrement des données personnelles en base** (date de naissance, certificat médical, contact d'urgence) — à considérer si la base est sauvegardée hors du serveur.
