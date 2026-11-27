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

## Visuels (captures d'écran PNG des vrais écrans — s'affichent directement dans ce README)

Régénération : lancer l'app, capturer les pages HTML, puis
`python3 tools/render_screenshots.py <dossier_pages_html> docs/screenshots` (SVG)
puis `python3 tools/svg2png.py docs/screenshots` (PNG).

- [01 — Connexion](docs/screenshots/01-connexion.png)
- [02 — Tableau de bord admin](docs/screenshots/02-tableau-de-bord-admin.png)
- [03 — Liste des dossiers](docs/screenshots/03-dossiers.png)
- [04 — Détail d'un dossier](docs/screenshots/04-dossier-detail.png)
- [05 — Registre des certificats OFDTI](docs/screenshots/05-certificats.png)
- [06 — Certificat imprimable](docs/screenshots/06-certificat-imprimable.png)
- [07 — Factures](docs/screenshots/07-factures.png)
- [08 — Notifications](docs/screenshots/08-notifications.png)
- [09 — Administration (utilisateurs)](docs/screenshots/09-admin-utilisateurs.png)
- [10 — Tableau de bord candidat](docs/screenshots/10-tableau-de-bord-candidat.png)
- [11 — Statistiques (graphiques SVG)](docs/screenshots/11-statistiques.png)
- [12 — Nouveau dossier (domaines × types de formation)](docs/screenshots/12-nouveau-dossier.png)
- [13 — Documents de référence](docs/screenshots/13-documents.png)
- [14 — Profil de l'organisme de formation](docs/screenshots/14-profil-organisme.png)
- [15 — Phase audit : écarts constatés (vue auditeur)](docs/screenshots/15-audit-ecarts.png)

## Phase audit (documents V003/V004/V009/V002 + plan V006)

- **Plan d'audit V006** : `/dossiers/{id}/plan-audit` → Word original pré-rempli (identité OF, responsable d'audit, domaines×types cochés) — utilisable tel quel sur la tablette de l'auditeur.
- **Ordre de mission auditeurs V003** : `/dossiers/{id}/ordre-mission` (Word rempli).
- **Fiches d'écart V004** : l'auditeur constate les écarts depuis le CRM (formulaire tablette sur le dossier) ; chaque écart a sa fiche Word remplie `/ecarts/{id}/fiche` (référence EC-YYYY-NNNN, gravité cochée ☒, statut ouvert/traité/clos).
- **Rapport d'audit V009** : `/dossiers/{id}/rapport-audit-document` (Word rempli) + `/rapport-audit.pdf` (PDF incluant la liste des écarts).
- **Revue d'audit (Excel V002)**, **réunions de clôture** (V003 intermédiaire, V001 finale) : servis tels quels dans `/documents` et liés depuis le dossier.
- À la planification de l'audit, les auditeurs sont notifiés automatiquement (ordre de mission + plan disponibles).

## Documents officiels envoyés à l'OF (fichiers originaux éditables)

Les documents transmis aux organismes de formation sont **vos fichiers Word originaux** (`templates/documents/`),
remplis programmatiquement (`docx_fill.py`) — jamais des copies approchées :

- **Élément technique de demande de certification V0010** : pré-rempli avec l'identité de l'OF
  (profil `/profil`), à compléter et signer par l'OF. Téléchargement : `/dossiers/{id}/demande-document` (.docx)
  + aperçu PDF `/dossiers/{id}/demande.pdf`. Bouton admin « Envoyer la demande à l'OF » (notification + e-mail,
  envoi tracé dans `dossiers.demande_envoyee_at`). Le retour signé se dépose en pièce jointe de catégorie
  « demande signée » et **bloque la recevabilité** tant qu'il n'est pas reçu (procédure V016).
- **Certificat OFDTI V007** : rempli à partir du dossier (n°, organisme, SIREN, n° d'enregistrement, dates,
  et cases ☒ cochées dans le tableau domaines × types de formation selon la portée certifiée).
  Téléchargement : `/certificats/{id}/document` (.docx original rempli) + `/certificats/{id}/pdf` (PDF signé RSA-2048).
- Pièces justificatives classées par catégorie (demande signée, K-bis, Qualiopi, capacités, moyens, facture…).

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
- **Déploiement HTTPS / production** : pack complet dans [`deploy/`](deploy/PRODUCTION.md) —
  `deploy.sh <tag>` (sauvegarde + déploiement + healthcheck), `rollback.sh <tag> [stamp]` (retour arrière
  code + base), `backup.sh` (sauvegardes horodatées SQLite + clés de signature), `Dockerfile` +
  `docker-compose.yml` + Caddy (HTTPS automatique Let's Encrypt), unité systemd, `.env.example`
  (BASE_URL, SMTP_*). Garde-fou : `--reset` refusé si `CRM_LCP_PROD=1`. Checklist complète (DNS, pare-feu,
  changement des mots de passe démo, cron de sauvegarde, RGPD) dans `deploy/PRODUCTION.md`.
  **Déploiement guidé pas à pas sur Infomaniak Public Cloud** (VPS `lcpofdti.lcp-certification.fr`,
  DNS, SMTP Infomaniak, HTTPS automatique, sauvegardes) : [`deploy/INFOMANIAK.md`](deploy/INFOMANIAK.md).

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
