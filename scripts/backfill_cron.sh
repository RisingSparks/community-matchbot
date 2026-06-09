#!/bin/bash
set -euo pipefail

REPO_DIR="~/github/burning-man-matchbot"
LOG_FILE="$REPO_DIR/data/logs/matchbot.log"
BACKFILL_LOG="/tmp/matchbot-backfill.log"

if [ -f "$LOG_FILE" ]; then
    # Search for the completion log line
    last_line=$(grep -F "matchbot.backfill_reddit_json - Reddit JSON backfill complete" "$LOG_FILE" | tail -n 1 || true)
    
    if [ -n "$last_line" ]; then
        # The timestamp is the first 19 characters, e.g. "2026-06-09 11:00:46"
        timestamp_str="${last_line:0:19}"
        last_run_epoch=$(date -j -f "%Y-%m-%d %H:%M:%S" "$timestamp_str" "+%s" 2>/dev/null || echo 0)
        current_epoch=$(date +%s)
        
        if [ "$last_run_epoch" -ne 0 ]; then
            diff_seconds=$((current_epoch - last_run_epoch))
            if [ "$diff_seconds" -lt 86400 ]; then
                echo "$(date): Ran successfully $((diff_seconds / 3600)) hours ago. Skipping run." >> "$BACKFILL_LOG"
                exit 0
            fi
        fi
    fi
fi

# Otherwise, run the backfill
cd "$REPO_DIR"
SINCE=$(date -v-6d +%Y-%m-%d)
uv run python scripts/backfill_reddit_json.py --live --since-date "$SINCE" >> "$BACKFILL_LOG" 2>&1
