#!/bin/bash
set -euo pipefail

cd /Users/peter/github/burning-man-matchbot
SINCE=$(date -v-6d +%Y-%m-%d)
uv run python scripts/backfill_reddit_json.py --since-date "$SINCE" >> /tmp/matchbot-backfill.log 2>&1
