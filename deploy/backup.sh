#!/bin/bash
# Sauvegarde la base SQLite + les clés de signature + les paramètres.
# Usage : sudo -u www-data bash deploy/backup.sh [répertoire_backup]
set -euo pipefail
APP_DIR="${APP_DIR:-/opt/crm-lcp}"
BACKUP_DIR="${1:-/var/backups/crm-lcp}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
sqlite3 "$APP_DIR/crm_lcp.db" ".backup '$BACKUP_DIR/crm_lcp-$STAMP.db'"
cp -r "$APP_DIR/data" "$BACKUP_DIR/data-$STAMP" 2>/dev/null || true
tar -czf "$BACKUP_DIR/code-$STAMP.tar.gz" -C "$APP_DIR" --exclude=data --exclude=crm_lcp.db --exclude=__pycache__ .
# garder les 10 dernières sauvegardes
ls -1t "$BACKUP_DIR"/crm_lcp-*.db 2>/dev/null | tail -n +11 | xargs -r rm -f
echo "Sauvegarde OK : $BACKUP_DIR (stamp $STAMP)"
