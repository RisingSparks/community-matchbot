#!/usr/bin/env python
"""Backfill historical Facebook posts from HAR or Extension JSON files."""

import asyncio
import logging
import sys
from datetime import UTC, datetime, time
from pathlib import Path

import typer

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from matchbot.db.engine import create_db_and_tables, dispose_engine
from matchbot.importers.facebook_har import (
    backfill_facebook_posts,
    parse_extension_json,
    parse_har_file,
)
from matchbot.log_config import configure_logging
from matchbot.settings import get_settings

logger = logging.getLogger("matchbot.backfill_facebook")
app = typer.Typer()
_FORMAT_SNIFF_BYTES = 64 * 1024


def _detect_format(path: Path) -> str:
    """Detect if the file is a HAR or extension-style JSON."""
    try:
        with open(path, "rb") as f:
            header = f.read(_FORMAT_SNIFF_BYTES).lstrip()
            if header.startswith(b"["):
                return "extension"
            if header.startswith(b"{") and b'"log"' in header and b'"entries"' in header:
                return "har"
    except OSError:
        pass
    return "unknown"


@app.command()
def main(
    files: list[Path] = typer.Argument(..., help="Path to HAR or Extension JSON file(s)"),
    group_name: str = typer.Option(..., "--group-name", help="Name of the Facebook group"),
    group_id: str | None = typer.Option(
        None, "--group-id", help="Numeric Facebook Group ID (optional)"
    ),
    since_date: str | None = typer.Option(
        None, "--since-date", help="UTC date cutoff (YYYY-MM-DD)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Parse and dedup only, without DB writes."
    ),
    no_extract: bool = typer.Option(
        False, "--no-extract", help="Skip LLM extraction, save as RAW."
    ),
    sleep_seconds: float = typer.Option(0.5, "--sleep-seconds", help="Pause between LLM calls."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging."),
) -> None:
    """Backfill Facebook posts from intercepted network traffic files."""
    settings = get_settings()
    configure_logging(verbose=verbose or settings.verbose)

    asyncio.run(
        _main_async(
            files=files,
            group_name=group_name,
            group_id=group_id,
            since_date=since_date,
            dry_run=dry_run,
            no_extract=no_extract,
            sleep_seconds=sleep_seconds,
        )
    )


async def _main_async(
    *,
    files: list[Path],
    group_name: str,
    group_id: str | None,
    since_date: str | None,
    dry_run: bool,
    no_extract: bool,
    sleep_seconds: float,
) -> None:
    since_datetime = None
    if since_date:
        try:
            parsed_since_date = datetime.strptime(since_date, "%Y-%m-%d").date()
            since_datetime = datetime.combine(
                parsed_since_date, time.min, tzinfo=UTC
            ).replace(tzinfo=None)
        except ValueError as exc:
            raise typer.BadParameter("--since-date must be in YYYY-MM-DD format") from exc

    await create_db_and_tables()

    all_parsed_posts = []
    for path in files:
        if not path.exists():
            logger.error("File not found: %s", path)
            continue

        fmt = _detect_format(path)
        logger.info("Processing %s (detected format: %s)", path, fmt)

        if fmt == "har":
            posts = parse_har_file(path)
        elif fmt == "extension":
            posts = parse_extension_json(path)
        else:
            logger.error("Could not detect format for %s", path)
            continue

        logger.info("Found %d post-like nodes in %s", len(posts), path)
        all_parsed_posts.extend(posts)

    # Global dedup across files (in case multiple files overlap)
    unique_posts_map = {}
    for p in all_parsed_posts:
        unique_posts_map[p["platform_post_id"]] = p

    unique_posts = list(unique_posts_map.values())
    logger.info("Total unique posts found across all files: %d", len(unique_posts))

    if not unique_posts:
        logger.info("No posts to process.")
        await dispose_engine()
        return

    try:
        counts = await backfill_facebook_posts(
            unique_posts,
            group_name=group_name,
            group_id=group_id,
            since_datetime=since_datetime,
            dry_run=dry_run,
            sleep_seconds=sleep_seconds,
            no_extract=no_extract,
        )
    finally:
        await dispose_engine()

    logger.info(
        (
            "Facebook backfill complete: parsed=%d new_candidates=%d matched=%d "
            "skipped=%d deduped=%d before_cutoff=%d extracted=%d raw_after_error=%d dry_run=%s"
        ),
        counts["parsed"],
        counts["new_candidates"],
        counts["matched"],
        counts["skipped"],
        counts["deduped"],
        counts["before_cutoff"],
        counts["extracted"],
        counts["raw_after_error"],
        dry_run,
    )


if __name__ == "__main__":
    app()
