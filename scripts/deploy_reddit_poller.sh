#!/usr/bin/env bash
# Deploy the Reddit poller Fly app, then enforce machine count.
# Usage:
#   ./scripts/deploy_reddit_poller.sh
#   MACHINE_COUNT=1 ./scripts/deploy_reddit_poller.sh
#   ./scripts/deploy_reddit_poller.sh --remote-only
set -euo pipefail

APP_NAME="burning-man-matchbot-reddit-poller"
CONFIG_FILE="fly.reddit-poller.toml"
PROCESS_GROUP="poller"
MACHINE_COUNT="${MACHINE_COUNT:-1}"

if ! command -v fly >/dev/null 2>&1; then
  echo "Error: flyctl is not installed or not on PATH." >&2
  exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Error: $CONFIG_FILE not found in repo root." >&2
  exit 1
fi

echo "Validating $CONFIG_FILE for app $APP_NAME..."
fly config validate -c "$CONFIG_FILE"

echo "Deploying $APP_NAME using $CONFIG_FILE..."
fly deploy -c "$CONFIG_FILE" -a "$APP_NAME" "$@"

echo "Enforcing ${MACHINE_COUNT} machine(s) for process group ${PROCESS_GROUP}..."
fly scale count "$MACHINE_COUNT" --process-group "$PROCESS_GROUP" -c "$CONFIG_FILE" --yes
