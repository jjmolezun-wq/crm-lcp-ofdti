# Déploiement en production (HTTPS)

**Procédure guidée Infomaniak Public Cloud (VPS Suisse, domaine `lcp-certificationofdti.fr`,
SMTP Infomaniak, HTTPS auto) : voir [INFOMANIAK.md](INFOMANIAK.md).**

Le prototype tourne en HTTP local. Pour la production derrière HTTPS :

## 1. Prérequis

- Un serveur chez un hébergeur conforme (ex. certifié HDS si des données de santé sont traitées),
  avec nom de domaine (ex. `crm-lcp.exemple.fr`) pointant vers le serveur (DNS A).
- Python 3.12+, le code du dépôt, et un reverse proxy (Caddy recommandé, ou nginx + certbot).

## 2. Installation

```bash
sudo mkdir -p /opt/crm-lcp
sudo cp -r . /opt/crm-lcp/
cd /opt/crm-lcp
sudo cp deploy/.env.example deploy/.env   # éditer : BASE_URL + SMTP_*
sudo -u www-data python3 -c "import db; db.init_db()"   # crée la base + données de démo
sudo systemctl enable --now crm-lcp        # service systemd (deploy/crm-lcp.service)
```

## 3. HTTPS automatique avec Caddy

```bash
sudo apt install caddy
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile   # éditer le domaine
sudo systemctl reload caddy                  # certificat Let's Encrypt automatique
```

## 4. Alternative nginx + certbot

Voir `deploy/nginx-crm-lcp.conf` : site 80 → redirection 443, certificat via
`certbot --nginx -d crm-lcp.exemple.fr`.

## 5. Points de vigilance production

- Changer les mots de passe de démonstration, désactiver le `--reset` en prod.
- La clé de signature RSA est générée dans `data/` (jamais commitée) : sauvegarder `data/lcp_signing_key.pem`.
- Base SQLite : prévoir des sauvegardes régulières (`sqlite3 crm_lcp.db ".backup backup.db"`),
  ou migrer vers PostgreSQL.
- RGPD : registre des traitements, durées de conservation, droit à l'effacement, DPO.
- Journaux : surveiller les erreurs 500 (traceback dans les logs du service).
