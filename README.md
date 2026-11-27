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
python3 tests.py   # démarre une instance isolée et joue 20 scénarios de bout en bout
```

## Visuels (captures d'écran SVG des vrais écrans)

Régénération : lancer l'app, capturer les pages HTML, puis
`python3 tools/render_screenshots.py <dossier_pages_html> docs/screenshots`.

- [01 — Connexion](docs/screenshots/01-connexion.svg)
- [02 — Tableau de bord admin](docs/screenshots/02-tableau-de-bord-admin.svg)
- [03 — Liste des dossiers](docs/screenshots/03-dossiers.svg)
- [04 — Détail d'un dossier](docs/screenshots/04-dossier-detail.svg)
- [05 — Registre des certificats OFDTI](docs/screenshots/05-certificats.svg)
- [06 — Certificat imprimable](docs/screenshots/06-certificat-imprimable.svg)
- [07 — Factures](docs/screenshots/07-factures.svg)
- [08 — Notifications](docs/screenshots/08-notifications.svg)
- [09 — Administration (utilisateurs)](docs/screenshots/09-admin-utilisateurs.svg)
- [10 — Tableau de bord candidat](docs/screenshots/10-tableau-de-bord-candidat.svg)
- [11 — Statistiques (graphiques SVG)](docs/screenshots/11-statistiques.svg)
- [12 — Nouveau dossier (domaines × types de formation)](docs/screenshots/12-nouveau-dossier.svg)
- [13 — Documents de référence](docs/screenshots/13-documents.svg)

## Conformité à la procédure de certification OFDTI (V016)

Le workflow du CRM reprend la procédure fournie (`templates/documents/Procedure_certification_OFDTI_V016.docx`) :

- **Cycle de certification : 5 ans (60 mois)** (`duree_certification_mois=60`), certificats `OFDTI-YYYY-NNNN`.
- Statuts : brouillon → **demande déposée** → **revue de recevabilité** → **recevable / non recevable** →
  **audit initial** → certifié / non conforme / refusé, puis **surveillance**, **renouvellement**,
  suspendu / retiré / expiré / abandonné.
- **Alertes de délais réglementaires** : recevabilité sous 15 jours (`delai_recevabilite_jours`),
  décision sous 9 mois après recevabilité (`delai_decision_mois`), **abandon automatique après 4 mois**
  sans pièces complémentaires (`delai_complement_mois`), avec notification et e-mail.
- **Renouvellement** : dossier auto-créé en brouillon à J-360 (`seuil_renouvellement_jours`), fenêtre
  48e mois → expiration, conformément à la procédure.
- **Portée de certification** : 11 domaines DTI (amiante, DPE, électricité, gaz, plomb, termites, termites O-M,
  audit énergétique — avec/sans mention) × 5 types de formation (FIP, FID, FCP, FCD, FPT), comme la table
  du modèle de certificat.
- **Charte graphique** : couleur de marque **#F0980C** (celle du certificat) appliquée à l'interface web,
  au certificat PDF (bordure et titres) et aux visuels.
- **Modèle de certificat** : `templates/documents/Modele_certificat_OFDTI_V007.docx` (référence) ; le PDF
  généré reprend sa structure (attestation, organisme/adresse/SIREN/n° d'enregistrement, table domaines ×
  formations, arrêtés cités, « Édien à Pessac, par le Responsable de certification » — tous ces éléments sont
  des paramètres admin) et est **signé électroniquement (RSA-2048)** avec vérification en ligne.
- **Documents de référence** servis par l'app : page `/documents` (procédure V016, modèle de certificat,
  mentions légales `certificat_mentions.txt` à remplacer par vos textes officiels).

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
- **Certificats PDF signés** : génération PDF (pur Python, sans dépendance) + signature électronique
  RSA-2048 (PSS/SHA-256) via `pdf.py` ; clé privée générée dans `data/` (hors dépôt), clé publique servie
  sur `/api/pubkey`, page de vérification `/certificats/{id}/verify` qui recalcule l'empreinte et contrôle
  la signature. Les mentions légales du certificat sont éditables dans `templates/documents/certificat_mentions.txt`
  (remplacez par votre modèle de certificat officiel).
- **Rapport d'audit PDF** : `/dossiers/{id}/rapport-audit.pdf` (observations internes, pour staff LCP).
- **Rappels de renouvellement** : à J-90 (paramètre `seuil_renouvellement_jours`), un dossier de
  renouvellement est créé automatiquement en brouillon + notification + e-mail ; bouton « Demander le
  renouvellement » sur le certificat.
- **Vrai envoi d'e-mails (SMTP)** : `emailer.py` envoie réellement via SMTP si `SMTP_HOST` etc. sont
  définis (voir `deploy/.env.example`) ; sinon repli sécurisé en simulation journalisée (table `outbox`,
  statut « envoyé (SMTP) » / « simulé »).
- **Tableau de bord avancé** : page `/stats` (admin/auditeur) — KPI (délai moyen dépôt→décision, taux de
  certification, montants en retard, certificats actifs/expirant), graphiques SVG (dossiers par statut,
  par mois, factures par statut).
- **Déploiement HTTPS** : voir `deploy/` (Caddyfile Let's Encrypt automatique, exemple nginx+certbot,
  unité systemd, `.env.example`).

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
 db.py          schéma SQLite, migrations, seed, helpers (audit, notifications, e-mails)
 workflow.py    statuts et transitions du cycle de certification OFDTI
 automations.py relances, échéances, alertes, renouvellements (tâche de fond 60 s)
 templates.py   vues HTML (français)
 emailer.py     envoi SMTP réel (repli simulation si non configuré)
 pdf.py         génération PDF + signature RSA-2048 + vérification
 charts.py      graphiques SVG pour /stats
 tests.py       tests de bout en bout (26 scénarios)
 tools/         render_screenshots.py (visuels SVG des écrans)
 deploy/        Caddyfile, nginx, systemd, .env.example, guide HTTPS
 templates/documents/  modèle de mentions du certificat (à remplacer par le vôtre)
```
