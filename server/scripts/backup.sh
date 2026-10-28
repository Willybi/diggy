#!/bin/sh
set -eu

# --------------------------------------------------------------------------
# Diggy — Daily backup: PostgreSQL (pg_dump) + MinIO (mc mirror)
#
# Expected env vars (from .env):
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
#   MINIO_USER, MINIO_PASSWORD
#
# Optional env vars:
#   BACKUP_ENCRYPTION_KEY    GPG symmetric passphrase (dumps are UNENCRYPTED
#                            and never copied offsite without it)
#   RCLONE_REMOTE            rclone remote for offsite copies of encrypted
#                            dumps (e.g. gdrive:diggy-backups); dumps land in
#                            $RCLONE_REMOTE/postgres/. Unset = local only.
#   OFFSITE_RETENTION_COUNT  dumps kept offsite (default: 14, minimum: 2)
#
# Usage (from host, with docker compose):
#   docker compose run --rm backup
# --------------------------------------------------------------------------

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
# Local dumps are a fast-restore convenience; the offsite copy (rclone,
# OFFSITE_RETENTION_COUNT=14) is the real history, so keep few local (STO1).
RETENTION_DAYS=2

PG_DIR="$BACKUP_DIR/postgres"
MINIO_DIR="$BACKUP_DIR/minio"

mkdir -p "$PG_DIR"

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
EXT="${PG_FILE#*.}"
ln -sf "$PG_DIR/$PG_FILE" "$PG_DIR/latest.$EXT"

# Retention: remove dumps older than $RETENTION_DAYS days
find "$PG_DIR" -name "diggy_*.sql.gz*" -mtime +$RETENTION_DAYS -delete
echo "[$(date -Iseconds)] Cleaned up PostgreSQL dumps older than ${RETENTION_DAYS} days."

# ------------------------------- MinIO ------------------------------------
# Local artwork mirror RETIRED (STO1, 2026-10-28). The ~49 GB local MinIO mirror
# (it only ever covered catalog + artist buckets) was freed from the VPS disk.
# The artwork backup now lives on the operator's PC external drive via a
# scheduled rclone SFTP pull of the whole MinIO volume (all buckets, incl. the
# previously-unbacked set/album) — see ROADMAP STO1. The offsite PG dump copy
# below is unchanged. Do NOT re-add a local `mc mirror` here (it refills the disk).
echo "[$(date -Iseconds)] MinIO local mirror retired (backup moved to operator PC, STO1)."

# --------------------------- Offsite (rclone) ------------------------------
# Only ENCRYPTED dumps ever leave the VPS. The MinIO mirror stays local-only
# by design (artworks are re-fetchable through enrichment).
if [ -z "${RCLONE_REMOTE:-}" ]; then
  echo "[$(date -Iseconds)] WARNING: RCLONE_REMOTE not set, dump NOT copied offsite!"
else
  case "$PG_FILE" in
    *.gpg)
      OFFSITE_DIR="$RCLONE_REMOTE/postgres"
      echo "[$(date -Iseconds)] Copying encrypted dump to $OFFSITE_DIR..."
      rclone copy "$PG_DIR/$PG_FILE" "$OFFSITE_DIR/"
      echo "[$(date -Iseconds)] Offsite copy done: $PG_FILE"

      # Offsite retention: keep the N most recent dumps. Names embed the
      # timestamp, so lexicographic order == chronological order.
      OFFSITE_KEEP="${OFFSITE_RETENTION_COUNT:-14}"
      if [ "$OFFSITE_KEEP" -lt 2 ]; then
        OFFSITE_KEEP=2
      fi
      rclone lsf --files-only "$OFFSITE_DIR" \
        | grep '^diggy_' \
        | sort -r \
        | tail -n +$((OFFSITE_KEEP + 1)) \
        | while IFS= read -r OLD; do
            echo "[$(date -Iseconds)] Offsite retention: deleting $OLD"
            rclone deletefile "$OFFSITE_DIR/$OLD"
          done
      echo "[$(date -Iseconds)] Offsite retention done (keeping the ${OFFSITE_KEEP} most recent dumps)."
      ;;
    *)
      echo "[$(date -Iseconds)] WARNING: dump is NOT encrypted, offsite copy skipped!"
      ;;
  esac
fi

echo "[$(date -Iseconds)] Backup complete."
