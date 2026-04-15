# Burning Man Matchbot (GEMINI.md)

Welcome to the `burning-man-matchbot` project. This document provides an up-to-date, high-level overview of the project's architecture, data models, and development workflows.

## Project Overview

The **Burning Man Matchbot** is a community-driven tool designed to facilitate connections within the Burning Man ecosystem. It focuses on two primary interaction types:
- **Mentorship:** Connecting "seekers" (individuals/small groups) with "theme camps" or "art projects" for membership or collaboration.
- **Infrastructure:** Facilitating gear/equipment exchange ("Bitch n Swap"), such as borrowing/lending generators, shade, or tools.

### Key Objectives:
- **Index Community Posts:** Ingest public posts from Reddit, Discord, and Facebook (webhooks and manual backfills).
- **Structured Extraction:** Use LLMs (Anthropic Claude / OpenAI GPT) to transform unstructured social media posts into structured data (vibes, contribution types, seeker intent, infrastructure categories, geolocation).
- **Matching Logic:** Propose matches between seekers and camps based on shared vibes and needs.
- **Moderator Control:** Provide a FastAPI-based **Moderator API** and CLI for reviewing, approving, and sending match introductions.

### Core Tech Stack:
- **Language:** Python 3.12+
- **Dependency Management:** `uv`
- **Data Layer:** `SQLModel` (SQLAlchemy + Pydantic) with `alembic` for migrations. Supports SQLite and Postgres.
- **API Framework:** `fastapi` with routers for moderation, public community pages, and form-based submissions.
- **Platform Listeners:** `asyncpraw` (Reddit PRAW), `reddit_json` (Reddit JSON listener), `discord.py` (Discord), `fastapi` (Facebook webhooks).
- **LLM Clients:** `anthropic`, `openai`.
- **CLI Framework:** `typer` + `rich`.
- **Scheduling:** `apscheduler` for background tasks (backfills, matching, extraction).

## Building and Running

### 1. Setup
The project uses `uv` for environment management.
```bash
# Install dependencies and create a virtual environment
uv sync --dev
```

### 2. Database
```bash
# Run migrations
uv run alembic upgrade head
```

### 3. Running the Server (API & Listeners)
To start the FastAPI server (which mounts all platform routers and the scheduler):
```bash
uv run python -m matchbot.server
```
To run listeners and the scheduler concurrently:
```bash
uv run python scripts/run_listeners.py
```

### 4. Moderator Interaction
- **Web API:** Access the moderator API at `/api/mod/` (requires `mod_session` auth).
- **CLI:** Use the `matchbot` command for management.
```bash
uv run matchbot --help
uv run matchbot queue list
uv run matchbot posts list
```

### 5. Testing and Linting
```bash
# Run tests
uv run pytest

# Linting and Formatting
uv run ruff check .
uv run ruff format .

# Type checking
uv run mypy src
```

## Data Model & Lifecycle

### Core Models (`src/matchbot/db/models.py`):
- **`Post`:** The raw and extracted data from a social media post. Includes fields for `mentorship` and `infrastructure`.
- **`Profile`:** Aggregates data from multiple posts for a single author/identity.
- **`Match`:** A proposed or approved connection between a seeker and a camp.
- **`Event`:** An audit log for all system and moderator actions.
- **`OptOut`:** Tracks privacy requests to skip indexing for specific users.

### Post Lifecycle:
1. **`raw`:** Post fetched but not processed.
2. **`extracted`:** LLM has parsed the post into structured fields.
3. **`needs_review`:** Waiting for human moderator approval (especially if LLM confidence is low).
4. **`indexed`:** Post data is synced to a `Profile` and available for matching.
5. **`skipped` / `error`:** Discarded posts or processing failures.

### Match Lifecycle:
1. **`proposed`:** System-generated match based on scoring.
2. **`approved`:** Moderator confirmed the match is good.
3. **`intro_sent`:** Introduction message sent to both parties.
4. **`declined`:** Moderator or user rejected the match.

## Development Conventions

- **Surgical Changes:** Focus updates on specific components (e.g., a new extractor or scorer) rather than broad refactors.
- **Taxonomy:** All vibes, roles, and categories are defined in `src/matchbot/config/taxonomy.yaml`. Use `src/matchbot/taxonomy.py` for normalization.
- **Lifecycle Transitions:** Use the `transition` logic in `src/matchbot/lifecycle/` to ensure valid status changes and audit logging.
- **Async First:** Platform listeners and database sessions are asynchronous. Use `AsyncSession` for DB interactions.
- **Templating:** Match introduction messages use Jinja2 templates in `src/matchbot/config/templates/`.
- **Backfilling:** Use scripts in `scripts/backfill_*.py` for batch ingestion of historical data.

## Directory Map

- `src/matchbot/cli/`: Typer command definitions.
- `src/matchbot/db/`: SQLModel models and engine configuration.
- `src/matchbot/extraction/`: LLM-based data extraction and geolocation parsing.
- `src/matchbot/listeners/`: Platform-specific inbox/feed listeners (Reddit, Discord, FB).
- `src/matchbot/matching/`: Scoring and triage logic for matching.
- `src/matchbot/messaging/`: Message rendering and platform-specific senders.
- `src/matchbot/mod/`: Moderator API and auth.
- `src/matchbot/public/`: Public-facing community views and APIs.
- `src/matchbot/lifecycle/`: Status transition management and audit logging.
- `src/matchbot/enrichment/`: Tools for augmenting post data (e.g., additional metadata).
- `scripts/`: Operational scripts for running listeners and backfilling data.
- `.planning/`: Project roadmaps, requirements, and state tracking.
