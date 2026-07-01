#!/bin/sh
set -eu

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

if [ -n "${BACKUP_ENCRYPTION_KEY:-}" ]; then
  PG_FILE="diggy_${DATE}.sql.gz.gpg"
  PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    -h postgres \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --no-owner \
    --no-acl \
    | gzip \
    | gpg --batch --passphrase "$BACKUP_ENCRYPTION_KEY" --symmetric --cipher-algo AES256 \
    > "$PG_DIR/$PG_FILE"
  echo "[$(date -Iseconds)] PostgreSQL backup done (encrypted): $PG_FILE"
else
  PG_FILE="diggy_${DATE}.sql.gz"
  PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    -h postgres \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --no-owner \
    --no-acl \
    | gzip > "$PG_DIR/$PG_FILE"
  echo "[$(date -Iseconds)] PostgreSQL backup done (unencrypted): $PG_FILE"
  echo "[$(date -Iseconds)] WARNING: BACKUP_ENCRYPTION_KEY not set, backup is NOT encrypted!"
fi

# Symlink latest backup for easy verification
EXT="${PG_FILE#diggy_*_*}"
ln -sf "$PG_DIR/$PG_FILE" "$PG_DIR/latest.$EXT"

# Retention: remove dumps older than $RETENTION_DAYS days
find "$PG_DIR" -name "diggy_*.sql.gz*" -mtime +$RETENTION_DAYS -delete
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
