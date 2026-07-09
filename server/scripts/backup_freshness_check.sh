#!/bin/sh
set -eu

# --------------------------------------------------------------------------
# Diggy — Backup freshness check
#
# Verifies that the most recent PostgreSQL dump is no older than
# BACKUP_MAX_AGE_HOURS (default 26h). Prints an "ALERT:" line and exits
# non-zero when backups are missing or stale, so a cron wrapper can forward
# the message to its notification channel.
#
# Expected layout (produced by backup.sh):
#   /backups/postgres/diggy_YYYYmmdd_HHMMSS.sql.gz[.gpg]
#
# Env vars (optional):
#   BACKUP_DIR            backup root (default: /backups)
#   BACKUP_MAX_AGE_HOURS  staleness threshold in hours (default: 26)
#
# Usage (from host, with docker compose — needs the backups volume mounted):
#   docker compose run --rm --entrypoint /freshness.sh backup
# --------------------------------------------------------------------------

BACKUP_DIR="${BACKUP_DIR:-/backups}"
PG_DIR="$BACKUP_DIR/postgres"
MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-26}"
MAX_AGE_SECONDS=$((MAX_AGE_HOURS * 3600))

# Most recently modified dump (regular files only; the latest.* symlinks are
# type "l" and are skipped by -type f).
NEWEST=$(find "$PG_DIR" -type f -name 'diggy_*.sql.gz*' 2>/dev/null \
  | while IFS= read -r f; do
      printf '%s %s\n' "$(stat -c %Y "$f")" "$f"
    done \
  | sort -nr \
  | head -n 1)

if [ -z "$NEWEST" ]; then
  echo "[$(date -Iseconds)] ALERT: no PostgreSQL dump found in $PG_DIR"
  exit 1
fi

MTIME=${NEWEST%% *}
FILE=${NEWEST#* }
NOW=$(date +%s)
AGE=$((NOW - MTIME))
AGE_HOURS=$((AGE / 3600))

if [ "$AGE" -gt "$MAX_AGE_SECONDS" ]; then
  echo "[$(date -Iseconds)] ALERT: latest backup is ${AGE_HOURS}h old (> ${MAX_AGE_HOURS}h): $FILE"
  exit 1
fi

echo "[$(date -Iseconds)] OK: latest backup is ${AGE_HOURS}h old: $FILE"
exit 0
