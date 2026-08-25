#!/usr/bin/env bash

cd /c/Users/willi/Desktop/diggy || exit 1

LOG=/c/tmp/embed_full.log
CANDID=worker/embedding_backfill/data/candidates.csv

after=$(ssh diggy-vps "cd /root/diggy && docker compose exec -T postgres sh -c 'psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -q -tAc \"SELECT coalesce(max(catalog_id),0) FROM track_embeddings\"'")

echo "=== REPRISE keyset after-id=$after @ $(date '+%F %T') ===" >> "$LOG"

fails=0

while true; do
    python worker/embedding_backfill/backfill_embeddings.py \
        --apply \
        --workers 6 \
        --limit 2000 \
        --after-id "$after" \
        >> "$LOG" 2>&1

    if [ $? -ne 0 ]; then
        fails=$((fails+1))

        if [ "$fails" -ge 3 ]; then
            echo "=== STOP: 3 ECHECS CONSECUTIFS ===" >> "$LOG"
            break
        fi

        sleep 60
        continue
    fi

    fails=0

    newmax=$(tail -n +2 "$CANDID" 2>/dev/null | cut -d, -f1 | sort -n | tail -1)

    if [ -z "$newmax" ]; then
        echo "=== ALL DONE ===" >> "$LOG"
        break
    fi

    if [ "$newmax" -le "$after" ] 2>/dev/null; then
        echo "=== ALL DONE ===" >> "$LOG"
        break
    fi

    after="$newmax"
done
