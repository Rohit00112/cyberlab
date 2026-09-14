#!/usr/bin/env bash
set -euo pipefail

# IIC CyberLab restore (PRD §52). Usage:  ./infrastructure/backup/restore.sh <backup-dir>
#
# Restores the CyberLab database and platform configuration. The Keycloak
# database is restored by Docker on next boot from realm-export.json; use the
# Keycloak admin UI/API if you need user-level state from the dump.

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

SRC="${1:?usage: restore.sh <backup-dir>}"
[ -f "$SRC/cyberlab.dump" ] || { echo "cyberlab.dump not found in $SRC"; exit 1; }

echo "-> restoring cyberlab database"
docker compose exec -T postgres pg_restore -U cyberlab -d cyberlab --clean --if-exists "$SRC/cyberlab.dump"

if [ -f "$SRC/config.tgz" ]; then
    echo "-> restoring configuration"
    tar -xzf "$SRC/config.tgz" -C "$REPO_ROOT" .env docker-compose.yml docker-compose.prod.yml \
        infrastructure keycloak challenges 2>/dev/null || true
    echo "   note: review restored .env secrets before booting."
fi

echo "-> done. Rebuild and boot:"
echo "   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build"
echo "   keycloak state: re-import realm-export.json if needed."