# Tp-formation-suivi

Suivi des élèves en formation plongée : séances hebdomadaires, présences, compétences travaillées
et validées par élève, exercices, notes (équipe encadrante ou visibles par l'élève).

Issu de [TP-manager](https://github.com/BertrandMiannay/TP-manager) ; les élèves sont créés directement dans l'application.

## Démarrage

```
poetry install
DEBUG=True poetry run python manage.py init_dev_db   # base neuve + superutilisateur admin/admin
DEBUG=True poetry run python manage.py runserver
```

Puis :
1. **Saisons et cursus** → créer une saison (la marquer active) et un cursus (référentiel de compétences).
2. **Formations** → **+ Nouvelle formation** (ex. « N2 promo 2026 ») à partir d'un cursus.
3. Inscrire les élèves depuis la formation (création rapide sans compte) ou **Élèves** → **+ Nouvel élève**.
4. **Séances** → **+ Nouvelle séance**, en choisissant les formations travaillées ; un élève peut aussi être créé directement pendant l'appel.

## Fonctionnement

- **Cursus** : référentiel (catégories, compétences), réutilisé d'une formation à l'autre.
- **Formation** : instance d'un cursus (nom, dates, responsables), indépendante des saisons ; en cours ou terminée.
- **Inscription** : élève × formation, statut en formation / terminée / abandon.
- **Élève** : fiche (`formation.Member`). Le compte utilisateur (rôle `student`) est facultatif :
  il est créé quand on renseigne l'email, avec un lien d'invitation. Un élève sans compte peut être inscrit,
  noté présent et évalué normalement.
- **Saison** : regroupe les séances (la saison active est celle des nouvelles séances et des statistiques de présence).
- **Séance** : date, formations travaillées, encadrants. Les élèves attendus sont ceux inscrits (en formation) à l'une de ces formations.
- **Appel** : présent / absent / absent excusé, avec commentaire.
- **Compétences** : saisies par élève et par séance (travaillée, évaluation du jour, commentaire).
  Une évaluation met à jour le statut de l'élève et est historisée avec son auteur.
- **Exercices et notes** : sur la fiche élève ; chaque note est réservée à l'équipe ou visible par l'élève.
- **Mon suivi** (consultation uniquement) : l'élève connecté voit ses formations, présences, compétences, exercices et les notes qui lui sont destinées.
- **Export PDF** de l'évaluation par cursus.
- **Vue mobile** : menu repliable, tableaux affichés en cartes, appel avec gros boutons présent / absent /
  excusé et bouton d'enregistrement collé en bas d'écran, saisie des compétences adaptée au tactile
  (styles dans `templates/base.html` et `suivi/templates/suivi/base.html`, breakpoint 640px).

## Importer une formation (JSON)

**Saisons et cursus → Cursus → Importer** permet de créer un cursus complet en collant du JSON.

```json
{
  "name": "Cursus Niveau 2",
  "date": "2024-09-01",
  "categories": [
    {
      "name": "Équipement",
      "skills": [
        {"name": "Montage du détendeur"},
        {"name": "Gréement du gilet"}
      ]
    },
    {
      "name": "Techniques subaquatiques",
      "skills": [
        {"name": "Équilibrage"},
        {"name": "Palmage en surface"}
      ]
    }
  ]
}
```

Champs :
- `name` *(requis)* — nom du cursus
- `date` *(requis)* — date de version, format `AAAA-MM-JJ`
- `categories` — liste de catégories, chacune avec un `name` et une liste `skills` (objets `{"name": "..."}`)

## Rôles utilisateurs

Trois niveaux de compte (groupes Django, définis dans `userManagement.models.Role`) :

| Rôle | Label | Accès |
|------|-------|-------|
| `student` | Élève | « Mon suivi » (lecture seule) |
| `instructor` | Encadrant | Séances, présences, élèves, évaluations |
| `admin` | Administrateur | Tout, dont saisons/formations et utilisateurs |

Les comptes élèves sont créés depuis **Élèves → + Nouvel élève** ; les encadrants et administrateurs
via **Utilisateurs → + Inviter** (le rôle est choisi à l'invitation et modifiable ensuite).

## Migrations

Une seule migration initiale par application (`0001_initial`), régénérée avant la première mise en
production. Toute évolution du modèle ajoute désormais une nouvelle migration.

## Commandes utiles

```
python manage.py makemigrations userManagement formation suivi
python manage.py migrate
python manage.py test
python manage.py createsuperuser
```

## Docker

Image publiée sur GHCR par le workflow **Publish Docker image** (déclenchement manuel) :
`ghcr.io/bertrandmiannay/tp-formation-suivi:latest`.

Sur le serveur : `docker compose pull && docker compose up -d` (migrations appliquées au démarrage,
base SQLite dans un volume). Détails : `deploy/DEPLOY.md`.

La CI (`.github/workflows/ci.yml`) lance les tests, vérifie les migrations et construit l'image à chaque push sur `main` et sur les PR.
