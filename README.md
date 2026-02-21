# burning-man-matchbot

## Setup

This repo uses `uv` and keeps dependencies in `pyproject.toml`/`uv.lock`.

```bash
# from repo root
uv sync --dev
```

That creates/updates a local virtual environment at `.venv/`.

If you want to activate it manually:

```bash
source .venv/bin/activate
```

## Run

Run scripts with `uv run` (no manual activation required):

```bash
uv run python ...
```

For debugging, enable verbose logging with `VERBOSE=true` (env) or `matchbot --verbose ...` (CLI).

## Privacy & Terms

This is a volunteer-run community project. We value your privacy and only process public posts from community forums (Reddit, Discord, Facebook) to help match seekers with camps and infrastructure.

*   **Terms of Service:** [TERMS.md](./TERMS.md) (Plain-language rules and community notice)
*   **Privacy Policy:** [PRIVACY.md](./PRIVACY.md) (Data handling and AI processing details)

### How to Opt Out
If you don't want the bot to process your posts or send you matches, simply send a private message (PM/DM) with the text **`opt out`** to the bot on the platform you are using (Reddit or Discord).

## Notes

- Python requirement: `>=3.12`
- Dev tools installed by `uv sync --dev`: `pytest`, `ruff`, `mypy`, `ipython`
