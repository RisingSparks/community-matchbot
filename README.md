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

## Notes

- Python requirement: `>=3.12`
- Dev tools installed by `uv sync --dev`: `pytest`, `ruff`, `mypy`, `ipython`
