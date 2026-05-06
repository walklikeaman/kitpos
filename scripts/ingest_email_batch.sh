#!/usr/bin/env bash
# KIT POS — Email ingestion batch runner
# Runs ingest_email.py in batches of BATCH_SIZE emails.
# Each batch runs in a fresh process → avoids OOM on large mailboxes.
#
# Usage:
#   chmod +x ingest_email_batch.sh
#   ./ingest_email_batch.sh /path/to/Inbox.mbox
#   ./ingest_email_batch.sh /path/to/Inbox.mbox --start=500   # resume

MBOX="${1:-/Users/walklikeaman/Downloads/Takeout/Mail/Inbox.mbox}"
BATCH_SIZE=80          # emails per subprocess batch
TOTAL_EMAILS=2404      # approximate total in mbox
LOG="/tmp/email_batch_$(date +%Y%m%d_%H%M%S).log"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$SCRIPT_DIR/ingest_email.py"

# Parse --start= from remaining args
START=0
for arg in "${@:2}"; do
    if [[ "$arg" == --start=* ]]; then
        START="${arg#--start=}"
    fi
done

echo "📬  Batch ingest: $MBOX"
echo "    start=$START  batch=$BATCH_SIZE  log=$LOG"
echo "    Each batch = fresh Python process (prevents OOM)"
echo ""

CURRENT=$START
BATCH_NUM=0

while [ "$CURRENT" -lt "$TOTAL_EMAILS" ]; do
    BATCH_NUM=$((BATCH_NUM + 1))
    echo "━━━ Batch $BATCH_NUM  (start=$CURRENT limit=$BATCH_SIZE) ━━━" | tee -a "$LOG"

    python3 -u "$SCRIPT" "$MBOX" \
        --start="$CURRENT" \
        --limit="$BATCH_SIZE" \
        2>&1 | tee -a "$LOG"

    EXIT=$?
    if [ $EXIT -ne 0 ] && [ $EXIT -ne 137 ]; then
        echo "❌  Script exited with code $EXIT — stopping." | tee -a "$LOG"
        exit $EXIT
    fi
    if [ $EXIT -eq 137 ]; then
        echo "⚠️   OOM kill in batch $BATCH_NUM (start=$CURRENT) — trying smaller batch..." | tee -a "$LOG"
        BATCH_SIZE=$((BATCH_SIZE / 2))
        if [ "$BATCH_SIZE" -lt 10 ]; then
            echo "❌  Batch size too small, giving up." | tee -a "$LOG"
            exit 1
        fi
        echo "    Retrying with BATCH_SIZE=$BATCH_SIZE" | tee -a "$LOG"
        continue
    fi

    # Advance start by BATCH_SIZE (script may have processed fewer due to skips — that's fine)
    CURRENT=$((CURRENT + BATCH_SIZE))
    echo "" | tee -a "$LOG"
    sleep 2  # brief pause between batches
done

echo "" | tee -a "$LOG"
echo "✅  All batches complete. Full log: $LOG" | tee -a "$LOG"
