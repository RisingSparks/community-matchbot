# Repository Guidelines

## Project Structure & Module Organization
- Core application code lives in `src/matchbot/`, organized by domain: `listeners/`, `extraction/`, `matching/`, `messaging/`, `db/`, `cli/`, and `reporting/`.
- Tests live in `tests/` and mirror runtime modules (`test_extraction.py`, `test_scheduler.py`, etc.).
- Database migrations are in `alembic/versions/`; runtime scripts are in `scripts/`.
- Config and message templates live in `src/matchbot/config/` (`sources.yaml`, `taxonomy.yaml`, `templates/*.md.j2`).
- Operational and product docs are in `docs/`.

## Build, Test, and Development Commands
- `uv sync --dev`: install app and dev dependencies into `.venv`.
- `uv run pytest`: run the full test suite.
- `uv run ruff check .`: run lint checks (imports, pyupgrade, style errors).
- `uv run mypy src`: run static type checking.
- `uv run matchbot --help`: inspect CLI commands.
- `uv run python scripts/run_listeners.py`: run Reddit, Discord, and FastAPI webhook listeners together.
- `uv run alembic upgrade head`: apply DB migrations.

## Coding Style & Naming Conventions
- Python 3.12+; 4-space indentation; prefer type hints on public interfaces.
- Keep line length within Ruff’s configured limit (`100`).
- Use `snake_case` for functions/modules, `PascalCase` for classes, and explicit, domain-based names (`infra_scorer.py`, `cmd_queue.py`).
- Keep modules focused by feature area; add new CLI commands under `src/matchbot/cli/` as `cmd_<topic>.py`.

## Testing Guidelines
- Framework: `pytest` with `pytest-asyncio` (`asyncio_mode = auto`).
- Put tests under `tests/` with `test_*.py` naming.
- Prefer fixture-driven tests via `tests/conftest.py`; use in-memory async SQLite for DB behavior.
- Add or update tests for any change in extraction, scoring, listeners, or lifecycle logic before opening a PR.

## Commit & Pull Request Guidelines
- Follow the existing commit style: short, imperative summaries (for example, `Update cmd_posts.py`, `Migrate OpenAI calls to Responses API`), with optional prefixes like `docs:`.
- Keep commits scoped to one logical change.
- PRs should include: purpose, key behavioral changes, test evidence (`uv run pytest`, lint/type results), and any config/migration impact.
- Link related issues and include sample CLI output or screenshots when user-visible behavior changes.

## Security & Configuration Tips
- Copy `.env.example` to `.env` for local setup; never commit real secrets.
- Treat `matchbot.db` as local/dev data; do not rely on it for reproducible tests.
- Review `PRIVACY.md` and `TERMS.md` when changing ingestion, messaging, or data retention behavior.
