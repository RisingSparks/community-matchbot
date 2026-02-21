# Fly.io Deployment Plan

## Context

The matchbot currently runs only locally. We're deploying it to Fly.io on the free tier using a single VM that runs `scripts/run_listeners.py` — which already combines uvicorn (Facebook webhook) + Reddit + Discord listeners in one `asyncio.TaskGroup`. SQLite is persisted on a Fly volume so it survives redeploys.

One issue to fix: `alembic/env.py` reads its DB URL from the hardcoded `alembic.ini` value (`sqlite:///matchbot.db`), while `engine.py` reads from `settings.db_path`. On Fly, `DB_PATH=/data/matchbot.db`, so Alembic would migrate the wrong file if left unfixed.

## Files to Create

### `Dockerfile`
```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Install deps first (layer cache)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-workspace

# Copy source and install package
COPY . .
RUN uv sync --frozen --no-dev

COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
```

### `entrypoint.sh`
```bash
#!/bin/sh
set -e
uv run alembic upgrade head
exec uv run python scripts/run_listeners.py
```
Runs migrations on every deploy (idempotent), then starts the combined listener process.

### `fly.toml`
```toml
app = "burning-man-matchbot"
primary_region = "sjc"

[build]

[env]
  SERVER_HOST = "0.0.0.0"
  SERVER_PORT = "8080"
  DB_PATH = "/data/matchbot.db"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = false   # CRITICAL: listeners must stay alive
  auto_start_machines = true
  min_machines_running = 1

  [[http_service.checks]]
    grace_period = "10s"
    interval = "30s"
    method = "GET"
    timeout = "5s"
    path = "/health"

[mounts]
  source = "matchbot_data"
  destination = "/data"

[[vm]]
  size = "shared-cpu-1x"
  memory = "256mb"
```

`auto_stop_machines = false` is critical — Fly's default is to spin down idle VMs, which would kill the Reddit/Discord listeners.

### `.dockerignore`
```
.env
matchbot.db
matchbot.db-journal
reports/
.git/
__pycache__/
*.pyc
.venv/
tests/
.pytest_cache/
```

## Files to Modify

### `alembic/env.py`
Add env-aware URL override after `config = context.config` (line 17):
```python
import os
db_path = os.environ.get("DB_PATH", "matchbot.db")
config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
```
This makes Alembic use the same DB path as the app engine, controlled by the `DB_PATH` env var.

## Deploy Steps (run after implementation)

```bash
# 1. Install flyctl if needed
brew install flyctl && fly auth login

# 2. Create the app
fly apps create burning-man-matchbot

# 3. Create persistent volume (1GB, free)
fly volumes create matchbot_data --region sjc --size 1

# 4. Set all secrets from .env
fly secrets set \
  ANTHROPIC_API_KEY=... \
  REDDIT_CLIENT_ID=... \
  REDDIT_CLIENT_SECRET=... \
  REDDIT_USERNAME=... \
  REDDIT_PASSWORD=... \
  DISCORD_BOT_TOKEN=... \
  DISCORD_MODERATOR_CHANNEL_ID=... \
  FACEBOOK_APP_ID=... \
  FACEBOOK_APP_SECRET=... \
  FACEBOOK_PAGE_ACCESS_TOKEN=... \
  FACEBOOK_VERIFY_TOKEN=... \
  MODERATOR_NAME=...

# 5. Deploy
fly deploy

# 6. Tail logs to verify startup
fly logs
```

## Facebook Webhook
After deploy, set the webhook URL in your Facebook app dashboard to:
`https://burning-man-matchbot.fly.dev/webhook`

## Verification
- `fly logs` — should show "Database ready." then all 4 tasks starting
- `curl https://burning-man-matchbot.fly.dev/health` — should return `{"status": "ok"}`
- `fly ssh console` + `ls /data/` — should show `matchbot.db`
