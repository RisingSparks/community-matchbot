#!/bin/sh
set -e

# Run migrations
/app/.venv/bin/alembic upgrade head

# Start the application
exec /app/.venv/bin/python scripts/run_listeners.py
