#!/usr/bin/env bash
#
# Postgres backup for the interpretit deployment.
#
# Runs `pg_dump` inside the postgres container (so we don't need
# pg_dump installed on the host) and writes a gzipped dump to
# $BACKUP_DIR. Keeps the last 14 days; older files are deleted.
#
# Production cron entry (add via `crontab -e` on the VPS):
#   0 3 * * * /home/deploy/interpretit/scripts/backup_postgres.sh
#
# Restore is symmetric:
#   gunzip -c /backups/pgdump-2026-05-29.sql.gz \
#     | docker compose -p phase5 exec -T postgres psql -U interpretit interpretit
#
# Untested backups are not backups. Run a restore drill on first
# install and again after any schema change.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
PROJECT="${COMPOSE_PROJECT:-phase5}"
SERVICE="${POSTGRES_SERVICE:-postgres}"
DB_USER="${POSTGRES_USER:-interpretit}"
DB_NAME="${POSTGRES_DB:-interpretit}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"

STAMP=$(date -u +%F)
OUT="$BACKUP_DIR/pgdump-$STAMP.sql.gz"

docker compose -p "$PROJECT" exec -T "$SERVICE" \
    pg_dump -U "$DB_USER" -Fp --no-owner --no-acl "$DB_NAME" \
    | gzip > "$OUT"

# Refuse a suspiciously small dump — empty dumps usually mean a
# silent connection failure rather than an actually empty DB.
SIZE=$(stat -c %s "$OUT" 2>/dev/null || stat -f %z "$OUT")
if [ "$SIZE" -lt 1024 ]; then
    echo "backup_postgres: dump suspiciously small ($SIZE bytes) — keeping but flagging" >&2
fi

find "$BACKUP_DIR" -name 'pgdump-*.sql.gz' -mtime "+$RETENTION_DAYS" -delete

echo "backup_postgres: wrote $OUT ($SIZE bytes)"
