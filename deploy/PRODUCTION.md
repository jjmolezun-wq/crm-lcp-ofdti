# Mise en production réelle (checklist)

## 0. Ce que fait ce pack

- `deploy.sh <tag>` : sauvegarde + checkout du tag + migrations + restart + healthcheck
- `rollback.sh <tag> [stamp]` : retour arrière code (+ base si stamp donné)
- `backup.sh` : sauvegarde horodatée (SQLite + clés de signature + code)
- `Dockerfile` / `docker-compose.yml` : déploiement conteneurisé + Caddy (HTTPS auto)
- `Caddyfile` / `nginx-crm-lcp.conf` : reverse proxy HTTPS
- `crm-lcp.service` : unité systemd
- `.env.example` : variables d'environnement (BASE_URL, SMTP_*)

## 1. Serveur

- Hébergeur conforme (certifié HDS si données de santé), Ubuntu/Debian récent
- Enregistrement DNS A : `crm-lcp.votredomaine.fr` → IP du serveur
- Pare-feu : 80/443 ouverts, 8000 non exposé publiquement (bind 127.0.0.1)

## 2. Installation (5 commandes)

```bash
sudo mkdir -p /opt/crm-lcp && sudo cp -r . /opt/crm-lcp/
cd /opt/crm-lcp
sudo cp deploy/.env.example deploy/.env      # éditer : BASE_URL, SMTP_*
sudo cp deploy/crm-lcp.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now crm-lcp
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile # éditer le domaine, puis reload caddy
```

Variante Docker : `cd deploy && docker compose up -d` (Caddy inclus, HTTPS auto).

## 3. Mise en production initiale

```bash
cd /opt/crm-lcp
echo 'CRM_LCP_PROD=1' >> deploy/.env     # interdit --reset
sudo -u www-data bash deploy/backup.sh    # première sauvegarde
sudo bash deploy/deploy.sh v0.5-prototype
```

## 4. Sécurité à faire impérativement

- Changer les mots de passe de démonstration (admin@lcp.fr, auditeur@lcp.fr, candidats) via l'admin
- Ne jamais lancer avec `--reset` en prod (bloqué si `CRM_LCP_PROD=1`)
- Sauvegarder `data/lcp_signing_key.pem` (clé de signature) hors serveur aussi
- SMTP réel : remplir `SMTP_*` dans `deploy/.env` (les e-mails partiront vraiment)
- Certbot/Caddy renouvelle automatiquement le certificat TLS

## 5. Surveillance & rollback

- Healthcheck : `curl http://127.0.0.1:8000/health` (à brancher sur votre supervision)
- Logs : `journalctl -u crm-lcp -f`
- Rollback : `sudo bash deploy/rollback.sh v0.5-prototype <stamp_sauvegarde>`
- Cron de sauvegarde : `0 3 * * * sudo -u www-data bash /opt/crm-lcp/deploy/backup.sh`

## 6. RGPD

Registre des traitements, durées de conservation configurables, droit à l'effacement,
sous-traitance hébergeur (DPA), notification de violation sous 72 h.
