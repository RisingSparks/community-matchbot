#!/usr/bin/env bash
# Deploy the main Fly app, then enforce machine count.
# Usage:
#   ./scripts/deploy_main_app.sh
#   MACHINE_COUNT=1 ./scripts/deploy_main_app.sh
#   ./scripts/deploy_main_app.sh --remote-only
set -euo pipefail

APP_NAME="burning-man-matchbot"
CONFIG_FILE="fly.toml"
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

echo "Enforcing ${MACHINE_COUNT} machine(s)..."
fly scale count "$MACHINE_COUNT" -c "$CONFIG_FILE" --yes
