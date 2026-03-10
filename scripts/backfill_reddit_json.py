#!/usr/bin/env python
"""Backfill historical Reddit JSON posts using the listener ingestion pipeline."""

import asyncio
import logging
import sys
from datetime import UTC, datetime, time
from pathlib import Path

import typer

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from matchbot.db.engine import create_db_and_tables, dispose_engine, reset_db_and_tables
from matchbot.listeners.reddit_json import backfill_reddit_json
from matchbot.log_config import configure_logging
from matchbot.settings import get_settings

logger = logging.getLogger("matchbot.backfill_reddit_json")
app = typer.Typer()


@app.command()
def main(
    since_date: str = typer.Option(..., "--since-date", help="UTC date cutoff (YYYY-MM-DD)"),
    reset_db: bool = typer.Option(
        False,
        "--reset-db",
        help="Drop all app tables and recreate them before backfilling.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Skip confirmation for --reset-db.",
    ),
    fetch_limit: int | None = typer.Option(
        None,
        "--fetch-limit",
        min=1,
        max=100,
        help="Posts per Reddit page fetch (defaults to REDDIT_JSON_FETCH_LIMIT).",
    ),
    sleep_seconds: float = typer.Option(
        1.5,
        "--sleep-seconds",
        min=0.0,
        help="Pause between page fetches to reduce rate-limit risk.",
    ),
    max_pages: int = typer.Option(
        500,
        "--max-pages",
        min=1,
        help="Safety cap on total pages fetched.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Fetch + classify scope only, without DB writes or extraction.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    """Backfill Reddit posts on/after a UTC date cutoff."""
    settings = get_settings()
    configure_logging(verbose=verbose or settings.verbose)
    logger.info("Loaded REDDIT_JSON_USER_AGENT=%r", settings.reddit_json_user_agent)
    asyncio.run(
        _main_async(
            since_date=since_date,
            reset_db=reset_db,
            yes=yes,
            fetch_limit=fetch_limit,
            sleep_seconds=sleep_seconds,
            max_pages=max_pages,
            dry_run=dry_run,
        )
    )


async def _main_async(
    *,
    since_date: str,
    reset_db: bool,
    yes: bool,
    fetch_limit: int | None,
    sleep_seconds: float,
    max_pages: int,
    dry_run: bool,
) -> None:
    try:
        parsed_since_date = datetime.strptime(since_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise typer.BadParameter("--since-date must be in YYYY-MM-DD format") from exc

    since_datetime = datetime.combine(parsed_since_date, time.min, tzinfo=UTC).replace(tzinfo=None)

    if reset_db and not yes:
        confirmed = typer.confirm(
            "Drop all app tables and recreate them before backfilling?",
            default=False,
        )
        if not confirmed:
            raise typer.Abort()

    if reset_db:
        logger.warning("Resetting all app tables before Reddit JSON backfill.")
        await reset_db_and_tables()
    else:
        await create_db_and_tables()

    try:
        counts = await backfill_reddit_json(
            since_datetime,
            fetch_limit=fetch_limit,
            sleep_seconds=sleep_seconds,
            max_pages=max_pages,
            dry_run=dry_run,
        )
    finally:
        await dispose_engine()

    logger.info(
        (
            "Reddit JSON backfill complete: pages=%d fetched=%d candidates=%d "
            "matched=%d skipped=%d deduped=%d extracted=%d raw_after_error=%d dry_run=%s"
        ),
        counts["pages"],
        counts["fetched"],
        counts["new_candidates"],
        counts["matched"],
        counts["skipped"],
        counts["deduped"],
        counts["extracted"],
        counts["raw_after_error"],
        dry_run,
    )


if __name__ == "__main__":
    app()
