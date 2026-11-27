# CRM LCP — Certification OFDTI

Prototype fonctionnel d'un CRM pour **LCP**, pour piloter la **certification OFDTI de services** :
cycle de candidature → instruction → audit → décision → certificat → facturation, avec toute la
gestion administrative automatisée (relances, échéances, notifications, e-mails, exports).

Zéro dépendance externe : Python 3.12 standard library + SQLite.

## Démarrage

```bash
python3 app.py            # http://127.0.0.1:8000
python3 app.py --reset    # réinitialise la base avec les données de démonstration
PORT=9000 python3 app.py  # port personnalisé
```

Comptes de démonstration :

| Rôle     | E-mail                  | Mot de passe |
|----------|-------------------------|--------------|
| admin    | admin@lcp.fr            | admin123     |
| auditeur | auditeur@lcp.fr         | audit123     |
| candidat | candidat@exemple.fr     | demo123      |
| candidat | candidat@novaservices.fr| demo123      |

## Tests

```bash
python3 tests.py   # démarre une instance isolée et joue 15 scénarios de bout en bout
```

## Fonctionnalités du prototype

- **Authentification** : sessions cookie (HttpOnly, SameSite=Lax), hash PBKDF2, jeton CSRF sur tous les formulaires, 3 rôles (admin / auditeur / candidat) avec contrôle d'accès par route.
- **Dossiers de certification OFDTI** : création par le candidat, dépôt, workflow de statuts
  (`brouillon → déposé → en instruction → en audit → certifié / non conforme / refusé`, puis `suspendu / retiré / expiré`),
  historique complet et traçable de chaque transition.
- **Pièces justificatives** : téléversement (multipart, max 10 Mo), téléchargement, suppression, stockage en base.
- **Échanges** : commentaires candidat ↔ staff, commentaires internes visibles uniquement par le staff LCP.
- **Certificats OFDTI** : numéro automatique `OFDTI-YYYY-NNNN`, durée de validité configurable (36 mois par défaut),
  page certificat imprimable, registre des certifiés, statuts (valide / suspendu / retiré / expiré).
- **Facturation** : facture automatique à la certification (`FAC-YYYY-NNNN`, montant configurable),
  échéance configurable, statut émise → payée / en retard, relances automatiques.
- **Automatisations** (tournent toutes les 60 s + bouton « Exécuter maintenant ») :
  - passage des factures en retard + relance quotidienne (notification + e-mail simulé dans l'outbox),
  - alertes d'expiration des certificats aux seuils configurables (90/30/7 jours) pour le candidat et les admins,
  - alerte quand un dossier reste trop longtemps en instruction,
  - passage automatique des certificats expirés au statut « expiré ».
- **Notifications in-app** avec compteur dans l'en-tête et page dédiée.
- **E-mails simulés** : table `outbox` consultable dans l'administration (à brancher sur un vrai SMTP en production).
- **Administration** : gestion des utilisateurs (création, activation/désactivation), paramètres de la certification,
  journal d'audit complet (qui a fait quoi, quand), boîte d'envoi.
- **Exports CSV** : dossiers, registre des certifiés OFDTI, factures.

## Modèle de données (SQLite)

`users`, `sessions`, `dossiers`, `historique`, `pieces`, `commentaires`, `certificats`,
`factures`, `notifications`, `outbox`, `audit_log`, `parametres` — voir `db.py`.

## Limites connues du prototype (à traiter pour la production)

- Pas d'envoi d'e-mail réel (SMTP à brancher), pas de PDF signé (page imprimable HTML),
- pas de réinitialisation de mot de passe, pas de 2FA,
- stockage des pièces en base (préférer un stockage objet S3 chiffré),
- serveur HTTP embarqué : prévoir un déploiement derrière un reverse proxy (HTTPS) avec un vrai serveur d'application (WSGI/ASGI),
- RGPD : prévoir registre des traitements, durées de conservation configurables, droit à l'effacement,
- hébergement : données à héberger chez un hébergeur conforme (ex. certifié HDS si données de santé).

## Structure

```
app.py          serveur HTTP, routes, auth, CSRF, handlers
 db.py          schéma SQLite, seed, helpers (audit, notifications, e-mails)
 workflow.py    statuts et transitions du cycle de certification OFDTI
 automations.py relances, échéances, alertes (tâche de fond 60 s)
 templates.py   vues HTML (français)
 tests.py       tests de bout en bout
```
