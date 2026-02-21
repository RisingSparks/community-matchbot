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
