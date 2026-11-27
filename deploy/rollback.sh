#!/bin/bash
# Rollback vers un tag précédent (code) + restauration optionnelle de la base.
# Usage : sudo bash deploy/rollback.sh v0.5-prototype [backup_stamp]
set -euo pipefail
TAG="${1:?usage: rollback.sh <tag> [backup_stamp]}"
STAMP="${2:-}"
APP_DIR="${APP_DIR:-/opt/crm-lcp}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/crm-lcp}"
cd "$APP_DIR"
if [ -n "$STAMP" ]; then
    sqlite3 "$APP_DIR/crm_lcp.db" ".restore '$BACKUP_DIR/crm_lcp-$STAMP.db'" 2>/dev/null || \
        cp "$BACKUP_DIR/crm_lcp-$STAMP.db" "$APP_DIR/crm_lcp.db"
    rm -rf "$APP_DIR/data"; cp -r "$BACKUP_DIR/data-$STAMP" "$APP_DIR/data" 2>/dev/null || true
fi
git checkout "$TAG"
systemctl restart crm-lcp
sleep 2
curl -fsS http://127.0.0.1:8000/health && echo " -> rollback $TAG OK"
