#!/usr/bin/env python
"""
Backfill historical posts from a CSV file.

CSV format: title, body, platform, community, author_id, author_name, url, post_id

Usage:
    uv run python scripts/backfill.py --file posts.csv [--no-extract]
"""

import asyncio
import csv
import logging
import sys
import uuid
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from matchbot.db.engine import create_db_and_tables, get_session
from matchbot.db.models import Platform, Post, PostStatus
from matchbot.extraction import process_post
from matchbot.extraction.anthropic_extractor import AnthropicExtractor
from matchbot.extraction.openai_extractor import OpenAIExtractor
from matchbot.log_config import configure_logging
from matchbot.settings import get_settings

logger = logging.getLogger("matchbot.backfill")

app = typer.Typer()


@app.command()
def backfill(
    file: str = typer.Option(..., "--file", "-f", help="Path to CSV file"),
    extract: bool = typer.Option(True, "--extract/--no-extract", help="Run LLM extraction"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing to DB"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Ingest historical posts from a CSV file."""
    configure_logging(verbose=verbose or get_settings().verbose)
    asyncio.run(_backfill_async(file, extract, dry_run))


async def _backfill_async(file: str, extract: bool, dry_run: bool) -> None:
    await create_db_and_tables()

    settings = get_settings()
    extractor = None
    if extract:
        extractor = (
            AnthropicExtractor() if settings.llm_provider == "anthropic" else OpenAIExtractor()
        )

    try:
        path = Path(file)
        if not path.exists():
            logger.error("File not found: %s", file)
            raise SystemExit(1)

        count = 0
        skipped = 0

        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if dry_run:
                    logger.info("[dry-run] Would ingest: %s", row.get("title", "")[:60])
                    count += 1
                    continue

                post = Post(
                    platform=row.get("platform", Platform.MANUAL),
                    platform_post_id=row.get("post_id") or f"backfill_{uuid.uuid4().hex[:12]}",
                    platform_author_id=row.get("author_id", "unknown"),
                    author_display_name=row.get("author_name", ""),
                    source_url=row.get("url", ""),
                    source_community=row.get("community", ""),
                    title=row.get("title", "")[:500],
                    raw_text=row.get("body", "")[:2000],
                    status=PostStatus.RAW,
                )

                async with get_session() as session:
                    session.add(post)
                    await session.commit()
                    await session.refresh(post)

                    if extract and extractor:
                        post = await process_post(session, post, extractor)
                        logger.info("Backfilled %s → %s", post.platform_post_id, post.status)
                    else:
                        logger.info("Backfilled %s (no extraction)", post.platform_post_id)

                count += 1

        logger.info("Done. Ingested %d posts, skipped %d.", count, skipped)
    finally:
        if extractor:
            await extractor.aclose()


if __name__ == "__main__":
    app()
