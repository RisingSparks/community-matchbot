# burning-man-matchbot

Volunteer-run tooling to match Burning Man seekers with camps, art projects, and infrastructure opportunities.

## What It Does

The bot ingests public posts from Reddit, Discord, and Facebook, extracts structured intent using deterministic rules + optional LLMs, proposes matches, and supports moderator review + outreach.

Positioning: this is a discovery tool, not a recruitment tool. It helps
self-motivated people find aligned camps/art projects and helps camps/art teams
find new energy that fits their culture.

Core flow:

1. Ingest post (`RAW`)
2. Extract structure (`INDEXED` or `NEEDS_REVIEW`)
3. Propose matches (`PROPOSED` queue)
4. Moderator approve/reject/triage
5. Send intros + collect feedback

## Quickstart

Requirements:

- Python `>=3.12`
- [`uv`](https://docs.astral.sh/uv/)

From repo root:

```bash
uv sync --dev
cp .env.example .env
uv run alembic upgrade head
uv run matchbot --help
```

For local verification:

```bash
scripts/test_e2e_local.sh
```

Warning: `scripts/test_e2e_local.sh` removes `matchbot.db` before rebuilding test state (it creates a timestamped backup unless `--no-backup`).

## Run the System

Run all listeners (Reddit + Discord + Facebook webhook server):

```bash
uv run python scripts/run_listeners.py
```

Enable verbose logs with either:

- `VERBOSE=true`
- `uv run matchbot --verbose ...`

## CLI Overview

Top-level command groups:

- `uv run matchbot posts --help`
- `uv run matchbot queue --help`
- `uv run matchbot report --help`
- `uv run matchbot submit --help`
- `uv run matchbot enrich --help`

Common commands:

```bash
uv run matchbot posts list --limit 20
uv run matchbot posts show <post_id>
uv run matchbot posts re-extract <post_id>

uv run matchbot queue list --limit 20
uv run matchbot queue view <match_id>
uv run matchbot queue triage <match_id>
uv run matchbot queue approve <match_id>
uv run matchbot queue send-intro <match_id> --platform reddit --dry-run

uv run matchbot submit text "Looking for a camp in 2026" --platform manual --community local-test --extract
uv run matchbot submit file ./seed_posts.csv --platform manual --extract

uv run matchbot report metrics --format json
uv run matchbot report weekly --week 2026-W10
```

## Configuration

Environment variables are loaded from `.env` via `src/matchbot/settings.py`.

Start with:

```bash
cp .env.example .env
```

Key config files:

- `src/matchbot/config/sources.yaml`: platform communities/channels to ingest
- `src/matchbot/config/taxonomy.yaml`: normalized vibe/contribution/infrastructure categories

Platform setup guide:

- `docs/PLATFORM_SETUP.md`

## Enrichment (WWW Guide)

The enrichment command can attach WWW Guide metadata to camp posts.

Set in `.env`:

- `WWW_GUIDE_URL` (required unless passed via CLI `--url`)
- `WWW_GUIDE_YEAR` (optional)

Run:

```bash
uv run matchbot enrich www-guide --dry-run
uv run matchbot enrich www-guide --url <guide_json_url> --year 2026
```

## Development Commands

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy src
uv run alembic upgrade head
```

## Testing and Debugging

Recommended first pass:

```bash
scripts/test_e2e_local.sh
```

Useful options:

```bash
scripts/test_e2e_local.sh --skip-pytest
scripts/test_e2e_local.sh --with-llm
scripts/test_e2e_local.sh --no-backup
```

Fast runtime checks:

```bash
uv run matchbot posts list --status error --limit 20
uv run matchbot posts list --status indexed --limit 20
uv run matchbot queue list --limit 20
```

Detailed guide:

- `docs/TESTING.md`

## Privacy, Terms, and Opt-Out

This is a volunteer-run community project processing public posts from configured channels.

- Terms: `TERMS.md`
- Privacy: `PRIVACY.md`

Opt out by sending the bot a PM/DM with the exact text `opt out` on supported platforms.

## Documentation Index

- `docs/PLATFORM_SETUP.md`: Reddit/Discord/Facebook setup
- `docs/TESTING.md`: local E2E + debugging workflow
- `docs/MOD_API_REFERENCE.md`: moderator API reference
- `docs/MODERATOR_UI_SPEC.md`: moderator UI spec
- `docs/MODERATOR_UI_SPEC_v2.md`: updated UI spec
- `docs/BRIEFING_BOOK.md`: product/strategy context
- `docs/COMMUNITY_DISCUSSION_ONE_PAGER.md`: short, plain-language community discussion draft
- `PRIVACY.md`: privacy notice
- `TERMS.md`: terms/community notice
