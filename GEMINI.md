# Burning Man Matchbot (GEMINI.md)

Welcome to the `burning-man-matchbot` project. This document provides a high-level overview of the project's purpose, architecture, and development workflows to guide your contributions.

## Project Overview

The **Burning Man Matchbot** is a community-driven tool designed to facilitate connections between "seekers" (individuals looking for camps or mentorship) and "theme camps" or "art projects" within the Burning Man ecosystem. 

### Key Objectives:
- **Index Community Posts:** Ingest public posts from Reddit, Discord, and Facebook.
- **Structured Extraction:** Use LLMs (Anthropic Claude / OpenAI GPT) to transform unstructured social media posts into structured data (vibes, contribution types, intent).
- **Matching Logic:** Propose matches between seekers and camps based on shared vibes and needs.
- **Moderator Control:** Provide a CLI for human moderators to review, approve, and send match introductions.

### Core Tech Stack:
- **Language:** Python 3.12+
- **Dependency Management:** `uv`
- **Data Layer:** `SQLModel` (SQLAlchemy + Pydantic) with `alembic` for migrations.
- **Listeners:** `asyncpraw` (Reddit), `discord.py` (Discord), `fastapi` (Facebook webhooks).
- **LLM Clients:** `anthropic`, `openai`.
- **CLI Framework:** `typer` + `rich`.
- **Scheduling:** `apscheduler`.

## Building and Running

### 1. Setup
The project uses `uv` for environment management.
```bash
# Install dependencies and create a virtual environment
uv sync --dev
```

### 2. Database
The project supports SQLite (local development) and potentially Postgres.
```bash
# Run migrations
uv run alembic upgrade head
```

### 3. Running Listeners
To start all platform listeners (Reddit, Discord, Facebook Webhook) concurrently:
```bash
uv run python scripts/run_listeners.py
```

### 4. Moderator CLI
The main entry point for moderators is the `matchbot` command.
```bash
# Show help
uv run matchbot --help

# Review the match queue
uv run matchbot queue list

# Browse indexed posts
uv run matchbot posts list
```

### 5. Testing and Linting
```bash
# Run tests
uv run pytest

# Linting (Ruff)
uv run ruff check .

# Type checking (MyPy)
uv run mypy src
```

## Development Conventions

- **Surgical Changes:** Focus updates on specific components (e.g., a new extractor or scorer) rather than broad refactors.
- **Data Integrity:** Adhere to the `SQLModel` schemas in `src/matchbot/db/models.py`. Ensure all field changes are captured in an Alembic migration.
- **Async First:** Platform listeners and database sessions are asynchronous. Use `AsyncSession` for DB interactions.
- **LLM Prompts:** Extraction prompts are located in `src/matchbot/extraction/prompts.py`.
- **Templating:** Match introduction messages are rendered using Jinja2 templates in `src/matchbot/config/templates/`.
- **Logging:** Use the project's logging configuration (`matchbot.log_config`). Enable verbose mode with `VERBOSE=true` or `--verbose`.

## Directory Map

- `src/matchbot/cli/`: Typer command definitions.
- `src/matchbot/db/`: Database models and engine configuration.
- `src/matchbot/extraction/`: LLM-based data extraction logic.
- `src/matchbot/listeners/`: Platform-specific inbox/feed listeners.
- `src/matchbot/matching/`: Scoring and triage logic for matching seekers and camps.
- `src/matchbot/messaging/`: Message rendering and platform-specific senders.
- `scripts/`: Operational scripts for running listeners and backfilling data.
- `.planning/`: Project roadmaps, requirements, and state tracking.
- `docs/`: Technical specifications and strategy documents.
