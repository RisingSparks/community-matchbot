#!/usr/bin/env python
"""Backfill historical Reddit JSON posts using the listener ingestion pipeline."""

import asyncio
import logging
import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import typer

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from matchbot.db.engine import create_db_and_tables, dispose_engine, reset_db_and_tables
from matchbot.listeners.reddit_json import _build_reddit_json_headers, backfill_reddit_json
from matchbot.log_config import configure_logging
from matchbot.settings import get_settings

logger = logging.getLogger("matchbot.backfill_reddit_json")
app = typer.Typer()


def _collect_cached_ids(since_datetime: datetime, *, settings) -> list[str]:
    """Return all Reddit post IDs in data/raw/reddit/ for scrape-dates >= since_datetime.date()."""
    from matchbot.storage.raw_store import RawStore

    store = RawStore(base_dir=settings.raw_data_dir)
    since_date = since_datetime.date()
    platform_dir = Path(settings.raw_data_dir) / "reddit"
    all_ids: list[str] = []
    if not platform_dir.exists():
        return all_ids
    for date_dir in sorted(platform_dir.iterdir()):
        try:
            dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if dir_date >= since_date:
            all_ids.extend(store.list_ids("reddit", date=date_dir.name))
    return all_ids


async def _backfill_from_cache(
    all_ids: list[str], *, dry_run: bool, since_datetime: datetime
) -> None:
    """Replay raw Reddit payloads from disk without hitting the Reddit API."""
    from matchbot.cli.cmd_data import _post_status_async, _replay_one
    from matchbot.listeners.reddit_json import _source_created_at_from_json
    from matchbot.settings import get_settings
    from matchbot.storage.raw_store import RawStore

    settings = get_settings()
    store = RawStore(base_dir=settings.raw_data_dir)
    # Use the async helper directly — we're already inside a running event loop.
    status_map = await _post_status_async("reddit", all_ids)

    processed = skipped = errors = 0
    for post_id in all_ids:
        existing_status = status_map.get(post_id)
        if existing_status is not None and existing_status != "raw":
            logger.debug("Cache replay: skipping %s (already in DB)", post_id)
            skipped += 1
            continue

        payload = store.load("reddit", post_id)
        if payload is None:
            logger.warning("Cache replay: file missing for %s", post_id)
            errors += 1
            continue

        # Filter by actual post creation time, not the scrape-folder date.
        # A wide backfill may have cached posts older than --since-date.
        post_created_at = _source_created_at_from_json(payload)
        if post_created_at is not None and post_created_at < since_datetime:
            logger.debug(
                "Cache replay: skipping %s (created_at %s before since_datetime %s)",
                post_id,
                post_created_at,
                since_datetime,
            )
            skipped += 1
            continue

        if dry_run:
            logger.info("Cache replay [dry-run]: would process %s", post_id)
            processed += 1
            continue

        try:
            await _replay_one("reddit", post_id, payload)
            logger.info("Cache replay: processed %s", post_id)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Cache replay: error on %s — %s", post_id, exc)
            errors += 1

    logger.info(
        "Cache replay complete: processed=%d skipped=%d errors=%d dry_run=%s",
        processed, skipped, errors, dry_run,
    )


@app.command()
def main(
    since_date: str | None = typer.Option(
        None,
        "--since-date",
        help="UTC date cutoff (YYYY-MM-DD). Defaults to 7 days ago if omitted.",
    ),
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
    live: bool = typer.Option(
        False,
        "--live",
        help="Force fetching from the Reddit API even if a local cache exists.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    """Backfill Reddit posts on/after a UTC date cutoff."""
    settings = get_settings()
    configure_logging(verbose=verbose or settings.verbose)
    if since_date is None:
        since_date = (datetime.now(UTC) - timedelta(days=7)).date().isoformat()
        logger.info("No --since-date provided; defaulting to %s (last 7 days UTC).", since_date)
    if live:
        logger.info("Loaded REDDIT_JSON_USER_AGENT=%r", settings.reddit_json_user_agent)
        logger.info(
            "Loaded REDDIT_JSON_EMULATE_BROWSER=%s REDDIT_JSON_COOKIE_PRESENT=%s",
            settings.reddit_json_emulate_browser,
            bool(settings.reddit_json_cookie),
        )
        logger.info("Effective Reddit JSON headers=%r", _build_reddit_json_headers())
    asyncio.run(
        _main_async(
            since_date=since_date,
            reset_db=reset_db,
            yes=yes,
            fetch_limit=fetch_limit,
            sleep_seconds=sleep_seconds,
            max_pages=max_pages,
            dry_run=dry_run,
            live=live,
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
    live: bool,
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

    if not live:
        settings = get_settings()
        cached_ids = _collect_cached_ids(since_datetime, settings=settings)
        if cached_ids:
            if fetch_limit or sleep_seconds != 1.5 or max_pages != 500:
                logger.warning(
                    "Using cache (--live not set): --fetch-limit, --sleep-seconds, "
                    "and --max-pages are ignored."
                )
            logger.info(
                "Cache-first: found %d cached post(s) for dates >= %s. "
                "Processing from cache. Pass --live to fetch from Reddit instead.",
                len(cached_ids),
                since_datetime.date(),
            )
            try:
                await _backfill_from_cache(
                    cached_ids, dry_run=dry_run, since_datetime=since_datetime
                )
            finally:
                await dispose_engine()
            return
        logger.info("Cache empty for dates >= %s — fetching from Reddit.", since_datetime.date())

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
