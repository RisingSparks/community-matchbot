#!/usr/bin/env bash
set -euo pipefail

APP_NAME="burning-man-matchbot-reddit-poller"
CONFIG_FILE="fly.reddit-poller.toml"

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
