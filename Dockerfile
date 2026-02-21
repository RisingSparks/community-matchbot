# --- Builder Stage ---
FROM python:3.12-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Disable progress bars for cleaner logs
ENV UV_NO_PROGRESS=1

# Install dependencies using cache mounts for speed
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-workspace

# Copy source and install project (with bytecode compilation)
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# --- Runtime Stage ---
FROM python:3.12-slim-bookworm

WORKDIR /app

# Environment setup
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy virtual environment and necessary source files from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/scripts /app/scripts
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/entrypoint.sh /app/entrypoint.sh

# Security: Run as non-root user
RUN groupadd -r matchbot && useradd -r -g matchbot matchbot && \
    chown -R matchbot:matchbot /app
USER matchbot

RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
