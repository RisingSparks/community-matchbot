# burning-man-matchbot

Volunteer-run tooling that helps people discover aligned camps, art projects, and infrastructure opportunities.

## What This Project Is

This project is a lightweight matchmaking and community-sensing pilot for the Burning Man ecosystem.

It is testing a few adjacent use cases at once to learn what the community finds useful:

1. Infrastructure offers, asks, and swaps between camps and projects
2. Camp and art project connections for people offering help or looking for help
3. A broader "alignment snapshot" of what people across the community seem to need, offer, or care about

The common thread is supply and demand. The system looks at already-public posts and tries to surface where people, camps, and projects may be aligned on skills, assets, infrastructure, labor, or intent.

## Project Goals

The immediate goal is not to automate recruiting or force a new workflow. It is to reduce friction, observe real community behavior, and make collective needs more visible.

More concretely, the project aims to:

1. Make public "looking for camp/project/help" and "offering help/infra" posts easier to discover
2. Highlight patterns across the community so people can see where skills, assets, and needs are clustering
3. Support human-reviewed introductions when that is useful
4. Stay as passive as possible by learning from existing Reddit, Facebook, and Discord activity instead of requiring people to fill out yet another form

At this stage, the dashboard is primarily observational. It helps spark discussion about what kinds of matching, visibility, and coordination the community actually wants before the system takes a more active role.

## What It Does

The bot ingests public posts from Reddit, Discord, and Facebook, extracts
structured intent using deterministic rules + optional LLMs, proposes likely
connections, and supports human-reviewed introductions.

The workflow is community-led: camps and project teams remain in control of
fit, vetting, and intake decisions.

Where matching is enabled, the intent is to point people back to the original source posts so humans can decide whether to connect directly. The system is meant to surface relevant connections, not replace human judgment or consent.

Core flow:

1. Ingest post (`RAW`)
2. Extract structure (`INDEXED` or `NEEDS_REVIEW`)
3. Propose matches (`PROPOSED` queue)
4. Human review / approve / reject / triage
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

Run Reddit stage-1 JSON polling only (no Reddit app credentials required):

```bash
uv run python scripts/run_reddit_json_listener.py
```

Backfill historical Reddit JSON posts (same ingestion/extraction pipeline):

```bash
uv run python scripts/backfill_reddit_json.py --since-date 2026-01-01
uv run python scripts/backfill_reddit_json.py --since-date 2026-01-01 --dry-run
```

Enable verbose logs with either:

- `VERBOSE=true`
- `uv run matchbot --verbose ...`

## Public Community Page

Run the API server locally:

```bash
uv run uvicorn matchbot.server:app --reload
```

Open:

- `http://127.0.0.1:8000/community/` — public value page
- `http://127.0.0.1:8000/community/data` — JSON data feed used by the page

Optional CTA config in `.env`:

- `COMMUNITY_FEEDBACK_EMAIL=you@example.com` (uses `mailto:` feedback link)
- `COMMUNITY_FEEDBACK_URL=/forms/` (fallback URL when email is blank)

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
- `COMMUNITY_FEEDBACK_EMAIL` / `COMMUNITY_FEEDBACK_URL`: public community page feedback CTA target

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
