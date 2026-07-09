#!/bin/sh
set -eu

# --------------------------------------------------------------------------
# Diggy — Backup freshness check
#
# Verifies that the most recent PostgreSQL dump is no older than
# BACKUP_MAX_AGE_HOURS (default 26h), both in the local backups volume and,
# when RCLONE_REMOTE is set, on the offsite remote. Prints an "ALERT:" line
# and exits non-zero when backups are missing or stale, so a cron wrapper can
# forward the message to its notification channel. The local and offsite
# checks run independently: either one can trigger the alert.
#
# Expected layout (produced by backup.sh):
#   /backups/postgres/diggy_YYYYmmdd_HHMMSS.sql.gz[.gpg]      (local)
#   $RCLONE_REMOTE/postgres/diggy_YYYYmmdd_HHMMSS.sql.gz.gpg  (offsite)
#
# Env vars (optional):
#   BACKUP_DIR            backup root (default: /backups)
#   BACKUP_MAX_AGE_HOURS  staleness threshold in hours (default: 26)
#   RCLONE_REMOTE         rclone remote holding offsite dumps
#                         (e.g. gdrive:diggy-backups); unset = local check only
#
# Usage (from host, with docker compose — needs the backups volume mounted):
#   docker compose run --rm --entrypoint /freshness.sh backup
# --------------------------------------------------------------------------

BACKUP_DIR="${BACKUP_DIR:-/backups}"
PG_DIR="$BACKUP_DIR/postgres"
MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-26}"
MAX_AGE_SECONDS=$((MAX_AGE_HOURS * 3600))
NOW=$(date +%s)
STATUS=0

# ------------------------------- Local -------------------------------------
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
  STATUS=1
else
  MTIME=${NEWEST%% *}
  FILE=${NEWEST#* }
  AGE=$((NOW - MTIME))
  AGE_HOURS=$((AGE / 3600))
  if [ "$AGE" -gt "$MAX_AGE_SECONDS" ]; then
    echo "[$(date -Iseconds)] ALERT: latest local backup is ${AGE_HOURS}h old (> ${MAX_AGE_HOURS}h): $FILE"
    STATUS=1
  else
    echo "[$(date -Iseconds)] OK: latest local backup is ${AGE_HOURS}h old: $FILE"
  fi
fi

# ------------------------------ Offsite ------------------------------------
if [ -z "${RCLONE_REMOTE:-}" ]; then
  echo "[$(date -Iseconds)] Offsite check skipped (RCLONE_REMOTE not set)."
else
  OFFSITE_DIR="$RCLONE_REMOTE/postgres"

  # The backup container is bare Alpine: the compose command installs rclone
  # before running backup.sh, but this script replaces the entrypoint, so
  # install rclone here when missing.
  if ! command -v rclone >/dev/null 2>&1; then
    apk add --no-cache rclone >/dev/null 2>&1 || true
  fi

  if ! command -v rclone >/dev/null 2>&1; then
    echo "[$(date -Iseconds)] ALERT: rclone unavailable, cannot check offsite backups in $OFFSITE_DIR"
    STATUS=1
  elif ! LISTING=$(rclone lsf --files-only "$OFFSITE_DIR"); then
    echo "[$(date -Iseconds)] ALERT: offsite remote unreachable: $OFFSITE_DIR"
    STATUS=1
  else
    # Newest dump by name: names embed the timestamp, so lexicographic
    # order == chronological order. Age comes from that timestamp (no
    # reliable mtime over rclone remotes).
    NEWEST_OFFSITE=$(printf '%s\n' "$LISTING" | grep '^diggy_' | sort -r | head -n 1)
    if [ -z "$NEWEST_OFFSITE" ]; then
      echo "[$(date -Iseconds)] ALERT: no PostgreSQL dump found offsite in $OFFSITE_DIR"
      STATUS=1
    else
      TS=${NEWEST_OFFSITE#diggy_}
      TS=${TS%%.*}
      if ! OFFSITE_MTIME=$(date -D '%Y%m%d_%H%M%S' -d "$TS" +%s 2>/dev/null); then
        echo "[$(date -Iseconds)] ALERT: cannot parse timestamp of offsite dump: $NEWEST_OFFSITE"
        STATUS=1
      else
        OFFSITE_AGE=$((NOW - OFFSITE_MTIME))
        OFFSITE_AGE_HOURS=$((OFFSITE_AGE / 3600))
        if [ "$OFFSITE_AGE" -gt "$MAX_AGE_SECONDS" ]; then
          echo "[$(date -Iseconds)] ALERT: latest offsite backup is ${OFFSITE_AGE_HOURS}h old (> ${MAX_AGE_HOURS}h): $NEWEST_OFFSITE"
          STATUS=1
        else
          echo "[$(date -Iseconds)] OK: latest offsite backup is ${OFFSITE_AGE_HOURS}h old: $NEWEST_OFFSITE"
        fi
      fi
    fi
  fi
fi

exit $STATUS
