# Testing and Debugging

This guide is the fastest path to test and debug the app locally.

## 1) Deterministic Local E2E (recommended first)

From repo root:

```bash
scripts/test_e2e_local.sh
```

What it does:

1. Backs up existing `matchbot.db` (unless `--no-backup`)
2. Deletes `matchbot.db` (clean teardown)
3. Runs migrations
4. Runs `pytest` (unless `--skip-pytest`)
5. Seeds deterministic indexed seeker/camp posts
6. Asserts queue has at least one proposed match

Options:

```bash
scripts/test_e2e_local.sh --skip-pytest
scripts/test_e2e_local.sh --with-llm
scripts/test_e2e_local.sh --no-backup
```

`--with-llm` adds a real extraction phase using your `.env` provider + API key.

## 2) Manual Runtime Checks

After the script (or any run), inspect state:

```bash
uv run matchbot posts list --limit 20
uv run matchbot posts list --status indexed --limit 20
uv run matchbot posts list --status error --limit 20
uv run matchbot queue list --limit 20
```

Inspect a specific record:

```bash
uv run matchbot posts show <post_id>
uv run matchbot queue view <match_id>
```

Re-run extraction for a post:

```bash
uv run matchbot posts re-extract <post_id>
```

## 3) Live Integration Debug

When deterministic local flow is passing, test real listeners:

```bash
uv run python scripts/run_listeners.py
```

If ingestion fails, validate credentials and platform config:

1. `.env`
2. `src/matchbot/config/sources.yaml`
3. `docs/PLATFORM_SETUP.md`

## 4) Common Failure Patterns

1. `No matches with status='proposed'`: you do not yet have both an indexed seeker and indexed camp post.
2. Many posts in `error`: LLM provider/API key mismatch in `.env`.
3. Many posts in `raw`: extraction not being run, or ingestion path is bypassing extraction.
