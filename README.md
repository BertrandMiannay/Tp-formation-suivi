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

Puis : **Saisons et formations** → créer une saison (la marquer active) et un cursus,
**Élèves** → **+ Nouvel élève** (un lien d'invitation est généré pour qu'il choisisse son mot de passe),
**Séances** → **+ Nouvelle séance**.

## Fonctionnement

- **Élève** : fiche (`formation.Member`) rattachée à un compte utilisateur du rôle `student`.
  Il est inscrit à une ou plusieurs saisons et prépare un ou plusieurs niveaux (cursus).
- **Séance** : date, niveaux préparés, encadrants. Les élèves attendus sont ceux de la saison qui préparent l'un de ces niveaux.
- **Appel** : présent / absent / absent excusé, avec commentaire.
- **Compétences** : saisies par élève et par séance (travaillée, évaluation du jour, commentaire).
  Une évaluation met à jour le statut de l'élève et est historisée avec son auteur.
- **Exercices et notes** : sur la fiche élève ; chaque note est réservée à l'équipe ou visible par l'élève.
- **Mon suivi** : l'élève connecté voit ses présences, compétences, exercices et les notes qui lui sont destinées.
- **Export PDF** de l'évaluation par cursus.

## Importer une formation (JSON)

**Saisons et formations → Formations → Importer** permet de créer un cursus complet en collant du JSON.

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
