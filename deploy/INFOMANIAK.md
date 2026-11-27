# Déploiement pas à pas sur Infomaniak (Public Cloud) — CRM LCP OFDTI

Procédure pour héberger le CRM sur un VPS Infomaniak avec HTTPS automatique.
Le site existant `www.lcp-certification.fr` n'est **pas modifié** : le CRM est servi
sur le domaine dédié **`lcp-certification-ofdti.fr`**.

## 0. Nom de domaine retenu

- **Domaine dédié : `lcp-certification-ofdti.fr`** — à réserver dans le Manager Infomaniak
  (Domaines, ~10 €/an). Vérifier la disponibilité à la réservation ; si indisponible :
  `lcp-certification-ofdti.com`, ou repli gratuit en sous-domaine `lcpofdti.lcp-certification.fr`.
- Rappel AFNIC : le `.fr` est ouvert aux personnes morales/physiques ayant un lien avec
  l'UE/France — LCP Certification (Pessac) est éligible, et le nom correspond à votre marque.
- Le site existant `www.lcp-certification.fr` (ton CRM actuel) reste intact et séparé.

## 1. Prérequis et budget indicatif

- Compte Infomaniak (carte bancaire + n° de téléphone demandés). Le **Public Cloud
  offre CHF 300 de crédit valables 3 mois** : les premiers tests sont gratuits.
- Public Cloud facturé **à l'heure** : instance 2 vCPU / 4 Go RAM / 50 Go SSD
  ≈ CHF 8–16/mois selon la taille exacte (arrêter l'instance = on ne paie plus le calcul).
- **Service Mail** Infomaniak sur `lcp-certification.fr` pour la boîte `ofdti@…` (SMTP du CRM).
- Budget global indicatif : ~10 CHF/mois (VPS) + ~2 CHF/mois (boîte mail) + ~10 €/an (domaine).

## 2. Créer l'instance (console Infomaniak)

1. Manager → **Public Cloud** → « Nouveau projet » → région **Suisse** (Genève).
2. « Créer une instance » : image **Ubuntu 24.04 LTS**, taille **2 vCPU / 4 Go RAM / 50 Go SSD**
   (redimensionnable à chaud plus tard).
3. Clé SSH : enregistrer la paire de clés proposée et télécharger la **clé privée**.
4. **Groupe de sécurité** (pare-feu cloud), règles entrantes TCP :
   - port **22** depuis **ton IP uniquement** (SSH),
   - ports **80** et **443** depuis `0.0.0.0/0` (HTTP/HTTPS publics).
5. Attacher une **IP flottante** à l'instance → c'est l'IP fixe du CRM. La noter : `IP_VPS`.

## 3. Réserver le domaine et faire le DNS

1. Manager → **Domaines** → commander `lcp-certification-ofdti.fr` (si disponible).
2. Dans la zone DNS du domaine, ajouter :
   - enregistrement **A** `@` → `IP_VPS`,
   - enregistrement **A** `www` → `IP_VPS` (ou CNAME `www` → `@`),
   - TTL 300 pendant les tests.
3. Vérifier depuis ton poste : `ping lcp-certification-ofdti.fr` doit répondre sur `IP_VPS`.

## 4. Boîte mail OFDTI (SMTP du CRM)

- Activer le **Service Mail** sur `lcp-certification.fr`, créer la boîte
  `ofdti@lcp-certification.fr` (mot de passe fort, à conserver dans un coffre).
- SMTP Infomaniak : hôte `mail.infomaniak.com`, port **587**, **STARTTLS**,
  identifiant = adresse e-mail complète, mot de passe = celui de la boîte.

## 5. Connexion et installation de base

```bash
ssh ubuntu@IP_VPS
sudo apt update && sudo apt upgrade -y
sudo apt install -y git sqlite3 caddy ufw fail2ban unattended-upgrades python3-cryptography
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
```

Dépendance Python : seule `cryptography` est requise (paquet `python3-cryptography`),
le reste de l'app est la bibliothèque standard. `python3-bs4` n'est utile que pour
régénérer les visuels (`tools/`) sur le serveur — facultatif.

## 6. Déployer le code

```bash
sudo mkdir -p /opt/crm-lcp
sudo git clone https://github.com/jjmolezun-wq/crm-lcp-ofdti.git /opt/crm-lcp
cd /opt/crm-lcp
sudo git checkout vibe/crm-lcp-ofdti-5b6e68      # ou un tag : v0.6-deploy-ready
sudo chown -R www-data:www-data /opt/crm-lcp
```

## 7. Configuration

```bash
cd /opt/crm-lcp
sudo cp deploy/.env.example deploy/.env
sudo nano deploy/.env
```

Contenu complet (à adapter si autre domaine) :

```ini
BASE_URL=https://lcp-certification-ofdti.fr
CRM_LCP_PROD=1
SMTP_HOST=mail.infomaniak.com
SMTP_PORT=587
SMTP_USER=ofdti@lcp-certification.fr
SMTP_PASSWORD=********
SMTP_FROM="LCP Certification OFDTI <ofdti@lcp-certification.fr>"
SMTP_TLS=1
```

Le `Caddyfile` du dépôt contient déjà le bon domaine — il suffit de le copier :

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile   # contient lcp-certification-ofdti.fr (modifier si autre domaine)
sudo cp deploy/crm-lcp.service /etc/systemd/system/
sudo systemctl daemon-reload
```

## 8. Premier démarrage

```bash
cd /opt/crm-lcp
sudo -u www-data python3 -c "import db; db.init_db()"   # base + données de démo
sudo systemctl enable --now crm-lcp
sudo systemctl enable --now caddy
sleep 8
curl -fsS https://lcp-certification-ofdti.fr/health && echo " -> OK"
```

Ouvrir `https://lcp-certification-ofdti.fr` → page de connexion
(`admin@lcp.fr` / `admin123` en démo). Le certificat TLS est délivré et renouvelé
automatiquement par Caddy (ports 80/443 ouverts + DNS OK requis).

## 9. Sécurisation immédiate (obligatoire)

- Se connecter en admin → **changer tous les mots de passe de démonstration**
  (admin, auditeur, candidats) et supprimer les comptes inutiles.
- Vérifier l'envoi réel d'un e-mail : admin → outbox (colonne « envoyé » = oui).
- `CRM_LCP_PROD=1` est en place : `--reset` est refusé (garde-fou anti-effacement).
- fail2ban actif sur SSH, pare-feu UFW : 22/80/443 uniquement, le port 8000 reste
  en `127.0.0.1` (non exposé publiquement).

## 10. Sauvegardes (cron quotidien + copie externe)

```bash
sudo crontab -e
# ajouter :
0 3 * * * sudo -u www-data bash /opt/crm-lcp/deploy/backup.sh /var/backups/crm-lcp
```

`backup.sh` produit : dump SQLite horodaté + copie de `data/` (clés de signature RSA)
+ archive du code, en gardant les 10 dernières. Copie externe chiffrée recommandée :
**Swiss Backup** Infomaniak, ou stockage objet Public Cloud (compatible S3) via `rclone`.
Tester une restauration de temps en temps.

## 11. Mises à jour et rollback

```bash
cd /opt/crm-lcp
sudo bash deploy/deploy.sh v0.6-deploy-ready          # sauvegarde + tag + migrations + restart + healthcheck
sudo bash deploy/rollback.sh v0.5-prototype <stamp>   # retour arrière code (+ base si stamp donné)
```

Tags disponibles : `v0.5-prototype`, `v0.6-deploy-ready` (voir `git tag`).

## 12. Surveillance

- Healthcheck externe : surveiller `https://lcp-certification-ofdti.fr/health`
  (ex. UptimeRobot, gratuit).
- Logs : `sudo journalctl -u crm-lcp -f` et `sudo journalctl -u caddy -f`.
- Mises à jour de sécurité automatiques : `unattended-upgrades` (déjà installé).

## 13. Variante Docker (alternative à systemd)

```bash
sudo apt install -y docker.io docker-compose-plugin
cd /opt/crm-lcp/deploy
sudo docker compose up -d --build     # app sur 127.0.0.1:8000 + Caddy sur 80/443 (HTTPS auto)
```

Dans ce cas la base vit dans le volume Docker `crm-data` (`/data/crm_lcp.db` dans le
conteneur) : sauvegarder le volume, ou adapter `APP_DIR`/chemin dans `backup.sh`.

## 14. Checklist go-live

- [ ] Domaine `lcp-certification-ofdti.fr` réservé, DNS A `@`/`www` → IP flottante ; HTTPS OK (cadenas vert), certificat renouvelé auto
- [ ] Mots de passe de démo changés ; comptes inutiles supprimés
- [ ] SMTP testé (outbox « envoyé » = oui) ; e-mails reçus sur ofdti@lcp-certification.fr
- [ ] Cron de sauvegarde en place + restauration testée
- [ ] Pare-feu : 22 limité à ton IP, 80/443 ouverts, 8000 non exposé
- [ ] Clé de signature `data/lcp_signing_key.pem` copiée hors serveur (coffre-fort)
- [ ] Supervision du `/health` branchée ; alertes en cas d'erreur 500
- [ ] RGPD : sous-traitance hébergeur (Infomaniak, Suisse — DPA), registre des traitements,
      durées de conservation, droit à l'effacement, notification de violation sous 72 h

> Rappel : seul ce VPS Infomaniak est exposé publiquement. L'environnement de
> développement local (bac à sable) ne doit jamais être rendu accessible sur Internet.
