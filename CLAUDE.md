# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync --dev

# Run tests
uv run pytest tests/ -x -q

# Run a single test file
uv run pytest tests/test_scoring.py -x -q

# Run a single test by name
uv run pytest tests/test_scoring.py::test_function_name -x -q

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/

# Run the CLI
uv run matchbot --help
uv run matchbot posts list
uv run matchbot queue list
uv run matchbot queue send-feedback <id> [--dry-run]

# Run migrations (required after adding new DB columns)
uv run alembic upgrade head

# Start all platform listeners (Reddit, Discord, Facebook webhook, scheduler)
uv run python scripts/run_listeners.py

# Start only the FastAPI server (Facebook webhook + forms)
uv run uvicorn matchbot.server:app --host 0.0.0.0 --port 8080

# Enable verbose logging
VERBOSE=true uv run matchbot ...
# or
uv run matchbot --verbose ...
```

## Architecture

This is a multi-platform community matchmaking bot for Burning Man. It ingests posts from Reddit, Discord, and Facebook, extracts structured data via LLM, scores compatibility, and proposes matches to a human moderator who approves/sends intro messages.

### Data Flow

```
Platform listeners → Post (raw) → Keyword filter → LLM extraction → Post (indexed)
                                                                          ↓
                                                              propose_matches()
                                                                          ↓
                                                              Match (proposed) → Moderator review
                                                                          ↓
                                                              Intro message sent via platform sender
```

### Key Modules

- **`src/matchbot/db/models.py`** — All SQLModel table definitions (`Profile`, `Post`, `Match`, `Event`, `OptOut`) and status constant classes (`PostRole`, `PostStatus`, `MatchStatus`, `Platform`, `PostType`, `InfraRole`, `SeekerIntent`). Multi-valued fields (`vibes`, `contribution_types`, `infra_categories`) are stored as pipe-delimited strings.

- **`src/matchbot/extraction/`** — LLM extraction pipeline. `__init__.py:process_post()` runs the full pipeline: keyword filter → LLM → taxonomy normalization → DB update → propose_matches. Two LLM providers: Anthropic (Haiku) and OpenAI (gpt-4o-mini), selected by `llm_provider` setting.

- **`src/matchbot/matching/`** — Scoring and match queue.
  - `scorer.py`: Jaccard-based scoring with `WEIGHTS` (membership seekers) and `WEIGHTS_SKILLS` (skills_learning seekers).
  - `queue.py`: `propose_matches()` dispatches to infra or mentorship scoring, creates `Match` records, checks opt-outs.

- **`src/matchbot/messaging/`** — Intro message rendering and sending.
  - `renderer.py`: Jinja2 template dispatch based on `post_type` and `seeker_intent`. Also renders feedback messages.
  - `sender_reddit.py`, `sender_discord.py`, `sender_facebook.py`: Platform-specific DM senders.

- **`src/matchbot/listeners/`** — Platform event listeners running as async tasks in `scripts/run_listeners.py`.
  - `reddit.py`: `run_reddit_listener()` (new posts) + `run_reddit_inbox_listener()` (opt-out DMs).
  - `discord_bot.py`: Discord.py bot; DMs handled for opt-outs.
  - `facebook.py`: FastAPI webhook router for Facebook Graph API.

- **`src/matchbot/server.py`** — FastAPI app factory; mounts the Facebook webhook router, the intake forms router, and an APScheduler on startup.

- **`src/matchbot/forms/router.py`** — Optional direct intake form (GET/POST `/forms/seeker` and `/forms/camp`) bypassing social platforms.

- **`src/matchbot/config/templates/`** — Jinja2 message templates: `intro_{seeker,camp,infra,skills,skills_camp}_{reddit,discord,facebook}.md.j2` and `feedback_{reddit,discord,facebook}.md.j2`.

- **`src/matchbot/taxonomy.py`** — Loads `config/taxonomy.yaml` at import time; provides `normalize_vibes()`, `normalize_contribution_types()`, `normalize_infra_categories()`.

- **`src/matchbot/settings.py`** — Pydantic settings from `.env`; cached via `@lru_cache`. Call `get_settings.cache_clear()` in tests before monkeypatching env vars.

- **`src/matchbot/cli/`** — Typer CLI with sub-apps: `posts`, `queue`, `report`, `submit`, `enrich`.

### Database

- SQLite via `aiosqlite` + SQLAlchemy async engine. Dev DB: `matchbot.db` at repo root.
- Alembic migrations in `alembic/versions/`. Current chain: `3a54dd0eb627 → 4a8a055657bf → 09f197516925 → 7b3e9a2f1c84`.
- When adding a nullable column: add field to the SQLModel class, create a migration (`uv run alembic revision --autogenerate -m "description"`), run `uv run alembic upgrade head`.

### Testing

- `pytest-asyncio` with `asyncio_mode = "auto"`.
- `db_session` fixture (in `conftest.py`) creates an isolated in-memory SQLite DB per test — use this for unit tests.
- `TestClient`-based tests use the on-disk `matchbot.db`; keep these minimal.
- `seeker_post_factory` and `camp_post_factory` fixtures create `Post` objects without DB writes.
- `mock_extractor` fixture mocks the LLM extractor for extraction pipeline tests.
- `reset_settings` fixture is `autouse=True` — it clears the settings cache before/after every test.

### Post Types and Routing

Two distinct matching flows share the same ingestion pipeline:
- **Mentorship** (`PostType.MENTORSHIP`): seeker ↔ camp, scored by Jaccard on vibes + contribution types.
- **Infrastructure** (`PostType.INFRASTRUCTURE`): "Bitch n Swap" gear exchange, seeking ↔ offering, scored by `infra_scorer.py`.

Seeker intent further subdivides mentorship: `SeekerIntent.MEMBERSHIP` uses `WEIGHTS`, `SeekerIntent.SKILLS_LEARNING` uses `WEIGHTS_SKILLS`.
