#!/usr/bin/env bash
set -euo pipefail

# IIC CyberLab backup (PRD §51). Backs up the PostgreSQL databases, platform
# configuration, challenge definitions, and research artifacts. Lab instances
# are disposable and deliberately NOT backed up.
#
# Run from the repo root:  ./infrastructure/backup/backup.sh
# Archives land in infrastructure/backup/archives/<timestamp>/.

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$(dirname "$0")/archives/$STAMP"
mkdir -p "$DEST"

cd "$REPO_ROOT"

echo "-> dumping PostgreSQL databases"
docker compose exec -T postgres pg_dump -U cyberlab -Fc cyberlab >"$DEST/cyberlab.dump"
docker compose exec -T postgres pg_dump -U cyberlab -Fc keycloak >"$DEST/keycloak.dump"

echo "-> configuration & challenge definitions"
tar -czf "$DEST/config.tgz" \
    .env docker-compose.yml docker-compose.prod.yml \
    infrastructure/keycloak/realm-export.json \
    infrastructure/caddy \
    challenges apps/api/research 2>/dev/null || true

if [ -d data/research ]; then
    echo "-> research artifacts"
    tar -czf "$DEST/research.tgz" -C "$REPO_ROOT" data/research 2>/dev/null || true
fi

echo "-> done: $DEST"
echo "   rotate these archives off-host (encrypted) for a complete backup."