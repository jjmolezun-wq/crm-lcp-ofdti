#!/bin/bash
# Déploie une version taguée du CRM LCP en production.
# Usage : sudo bash deploy/deploy.sh v0.5-prototype
set -euo pipefail
TAG="${1:?usage: deploy.sh <tag-ex: v0.5-prototype>}"
APP_DIR="${APP_DIR:-/opt/crm-lcp}"
cd "$APP_DIR"
bash deploy/backup.sh
git fetch --tags origin
git checkout "$TAG"
sudo -u www-data python3 -c "import db; db.init_db()"   # migrations additives uniquement
systemctl restart crm-lcp
sleep 2
curl -fsS http://127.0.0.1:8000/health && echo " -> déploiement $TAG OK"
