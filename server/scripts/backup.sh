#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------------------------------------
# Diggy — Daily backup: PostgreSQL (pg_dump) + MinIO (mc mirror)
#
# Expected env vars (from .env):
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
#   MINIO_USER, MINIO_PASSWORD
#
# Usage (from host, with docker compose):
#   docker compose run --rm backup
# --------------------------------------------------------------------------

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

PG_DIR="$BACKUP_DIR/postgres"
MINIO_DIR="$BACKUP_DIR/minio"

mkdir -p "$PG_DIR" "$MINIO_DIR"

# ----------------------------- PostgreSQL ---------------------------------
echo "[$(date -Iseconds)] Starting PostgreSQL backup..."

PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
  -h postgres \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  --no-owner \
  --no-acl \
  | gzip > "$PG_DIR/diggy_${DATE}.sql.gz"

echo "[$(date -Iseconds)] PostgreSQL backup done: diggy_${DATE}.sql.gz"

# Retention: remove dumps older than $RETENTION_DAYS days
find "$PG_DIR" -name "diggy_*.sql.gz" -mtime +$RETENTION_DAYS -delete
echo "[$(date -Iseconds)] Cleaned up PostgreSQL dumps older than ${RETENTION_DAYS} days."

# ------------------------------- MinIO ------------------------------------
echo "[$(date -Iseconds)] Starting MinIO backup..."

# Configure mc alias (quiet, idempotent)
mc alias set diggy http://minio:9000 "$MINIO_USER" "$MINIO_PASSWORD" --quiet

BUCKETS="artworks catalog-artworks artist-artworks"
for bucket in $BUCKETS; do
  echo "[$(date -Iseconds)] Mirroring bucket: $bucket"
  mc mirror --overwrite --quiet "diggy/$bucket" "$MINIO_DIR/$bucket"
done

echo "[$(date -Iseconds)] MinIO backup done."
echo "[$(date -Iseconds)] Backup complete."
