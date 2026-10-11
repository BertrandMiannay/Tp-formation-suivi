# Conformité RGPD — Tp-formation-suivi

## Contexte

Tp-formation-suivi est une application web utilisée par un club de plongée pour suivre ses élèves en formation : séances, présences, compétences travaillées et validées, exercices et remarques de l'équipe encadrante. Toutes les données sont saisies directement dans l'application par l'encadrement ; aucune donnée n'est importée d'un service tiers.

**Responsable de traitement :** Le club de plongée (à compléter : nom, adresse, contact du référent RGPD).

---

## 1. Inventaire des données personnelles traitées

### 1.1 Comptes utilisateurs (`CustomUser`)

| Champ | Nature | Obligatoire |
|---|---|---|
| `username` | Identifiant de connexion | Oui |
| `email` | Adresse e-mail | Oui |
| `first_name` / `last_name` | Nom et prénom | Non |
| `password` | Mot de passe (hashé PBKDF2) | Oui |
| `date_joined` / `last_login` | Dates de création et de dernière connexion | Auto |
| `invite_token` / `invite_expires_at` | Jeton d'invitation et son expiration | Temporaire |
| `groups` | Rôle : élève (`student`), encadrant (`instructor`), administrateur (`admin`) | Oui |

**Source :** invitation par un administrateur, ou création de la fiche élève par un encadrant.
**Accès :** administrateurs (`/users/`, Django admin).

### 1.2 Élèves (`Member`)

| Champ | Nature | Obligatoire |
|---|---|---|
| `first_name` / `last_name` | Nom et prénom | Oui |
| `user` | Compte rattaché (porte l'e-mail) | Non |
| `birthdate` | Date de naissance | Non |
| `medical_certificate_date` | Date du certificat médical | Non |
| `emergency_contact_name` / `emergency_contact_phone` | Contact d'urgence | Non |
| `formations` / `seasons` | Niveaux préparés, saisons | Non |

**Source :** saisie par l'encadrement.
**Accès :** encadrants et administrateurs ; l'élève ne voit pas ces champs dans « Mon suivi ».

> **Donnée de santé :** la date du certificat médical relève de l'article 9 RGPD (voir section 2).

### 1.3 Suivi pédagogique

| Modèle | Contenu | Visible par l'élève |
|---|---|---|
| `Attendance` | Présence à une séance (présent / absent / excusé) + commentaire | Oui |
| `WorkedSkill` | Compétence travaillée en séance, évaluation du jour, commentaire, auteur | Oui |
| `MemberSkill` / `SkillEvaluation` | Statut courant et historique des évaluations, commentaire, évaluateur | Oui |
| `Exercise` | Exercice réalisé, résultat, commentaire | Oui |
| `StudentNote` | Remarque libre de l'encadrement | Seulement si visibilité « élève » |
| `TrainingSession` | Séance : date, lieu, encadrants, déroulé | Non |

**Source :** saisie par l'encadrement. **Accès :** encadrants et administrateurs ; l'élève consulte sa propre fiche en lecture seule.

---

## 2. Finalités et bases légales

| Finalité | Données | Base légale (art. 6) |
|---|---|---|
| Suivi pédagogique des élèves | Présences, compétences, exercices, notes | Exécution du contrat d'adhésion / formation (6.1.b) |
| Vérification de l'aptitude médicale | `medical_certificate_date` | Obligation réglementaire fédérale (6.1.c) |
| Contact d'urgence | `emergency_contact_*` | Intérêt vital (6.1.d) |
| Gestion des accès à l'application | `CustomUser` | Intérêt légitime du club (6.1.f) |

> **Données de santé (art. 9) :** le traitement de la date de certificat médical doit reposer sur une dérogation explicite, typiquement la nécessité pour les activités d'une association sportive (9.2.d) ou le consentement explicite (9.2.a). **Action requise :** documenter la base retenue au registre des traitements.

---

## 3. Sous-traitants

Aucun service tiers ne reçoit les données. L'hébergeur du serveur est sous-traitant au sens de l'art. 28 : **action requise** — vérifier ses conditions (localisation UE, DPA).

---

## 4. Durées de conservation

Aucune purge automatique n'est implémentée.

| Catégorie | Durée recommandée |
|---|---|
| Comptes inactifs | 3 ans après la dernière connexion (recommandation CNIL) |
| Fiches et suivi pédagogique | Durée de la formation + 3 ans (à valider par le club) |
| Certificat médical | Durée de validité + 1 saison |
| Jetons d'invitation | 7 jours (implémenté) |

---

## 5. Droits des personnes

Accès, rectification, effacement, limitation, portabilité, opposition (art. 15 à 22). L'élève consulte déjà ses données de suivi via « Mon suivi » ; l'export PDF de l'évaluation peut servir de réponse partielle à une demande d'accès.

**Contact pour exercer ces droits :** (à compléter).

---

## 6. Sécurité

Voir `SECURITY_CHECK.md` : rôles et gardes d'accès, SECRET_KEY obligatoire, cookies sécurisés, invitations à durée limitée, journalisation des actions sensibles, limitation des tentatives de connexion.

À renforcer : chiffrement des sauvegardes, revue annuelle des comptes et des rôles.

---

## 7. Actions à mener

- [ ] Registre des traitements (art. 30) à partir de l'inventaire ci-dessus.
- [ ] Base légale du traitement de la date de certificat médical (art. 9).
- [ ] Notice d'information aux élèves (art. 13) lors de la création de leur fiche.
- [ ] Procédure interne de réponse aux demandes de droits (délai d'un mois).
- [ ] Purge ou anonymisation des données au-delà des durées de conservation (`manage.py purge_old_data`).
- [ ] Désigner un référent RGPD au sein du club.

---

## 8. Références

- CNIL : [cnil.fr](https://www.cnil.fr) — [les associations et le RGPD](https://www.cnil.fr/fr/les-associations-et-le-rgpd)

*À réviser lors de toute évolution significative du traitement des données.*
