#!/bin/sh
set -e

# Run migrations
/app/.venv/bin/alembic upgrade head

# Start the application command supplied by Fly process group, if present.
# Fallback keeps local behavior unchanged.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

exec /app/.venv/bin/python scripts/run_listeners.py
