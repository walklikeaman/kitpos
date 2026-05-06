#!/usr/bin/env bash
# KIT POS — Batch email ingestion: one Python process per email
# Each process exits completely → OS reclaims ALL memory
#
# Usage:
#   ./ingest_eml_batch.sh /tmp/emails_split
#   ./ingest_eml_batch.sh /tmp/emails_split --start=100
#   ./ingest_eml_batch.sh /tmp/emails_split --start=100 --end=500

EML_DIR="${1:-/tmp/emails_split}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$SCRIPT_DIR/ingest_one_eml.py"
LOG="/tmp/eml_batch_$(date +%Y%m%d_%H%M%S).log"

START=0
END=99999
for arg in "${@:2}"; do
    [[ "$arg" == --start=* ]] && START="${arg#--start=}"
    [[ "$arg" == --end=* ]]   && END="${arg#--end=}"
done

PYTHON=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3

echo "📂  Dir: $EML_DIR" | tee -a "$LOG"
echo "    start=$START end=$END" | tee -a "$LOG"
echo "    log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

processed=0; skipped=0; errors=0; chunks=0

for fpath in "$EML_DIR"/[0-9]*.eml; do
    fname=$(basename "$fpath")
    idx="${fname%.eml}"
    idx=$((10#$idx))   # strip leading zeros

    [[ $idx -lt $START ]] && continue
    [[ $idx -gt $END ]]   && break

    OUT=$("$PYTHON" -u "$SCRIPT" "$fpath" 2>&1)
    EXIT=$?

    case $EXIT in
        0) skipped=$((skipped+1)) ;;
        2) processed=$((processed+1))
           echo "$OUT" | tee -a "$LOG"
           ;;
        *) errors=$((errors+1))
           echo "❌  [$idx] exit=$EXIT $OUT" | tee -a "$LOG"
           ;;
    esac

    # Progress every 50 processed
    if (( processed > 0 && processed % 50 == 0 )); then
        echo "  → processed=$processed skipped=$skipped errors=$errors" | tee -a "$LOG"
    fi
done

echo "" | tee -a "$LOG"
echo "══════════════════════════════════════════" | tee -a "$LOG"
echo "Processed: $processed" | tee -a "$LOG"
echo "Skipped:   $skipped"   | tee -a "$LOG"
echo "Errors:    $errors"    | tee -a "$LOG"
echo "Log:       $LOG"       | tee -a "$LOG"
