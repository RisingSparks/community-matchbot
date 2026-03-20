# src/matchbot/cli/cmd_data.py
"""CLI commands for raw data management and replay."""
from __future__ import annotations

import asyncio
import logging

import typer

from matchbot.settings import get_settings
from matchbot.storage.raw_store import RawStore

app = typer.Typer(help="Raw data management commands.")
logger = logging.getLogger(__name__)

_PLATFORM_MAP = {
    "reddit": "reddit",
    "discord": "discord",
    "facebook": "facebook",
}


def _get_raw_store() -> RawStore:
    return RawStore(base_dir=get_settings().raw_data_dir)


async def _post_exists_async(platform: str, post_ids: list[str]) -> dict[str, bool]:
    """Return a mapping of post_id → True if already in DB."""
    if not post_ids:
        return {}
    from sqlmodel import select

    from matchbot.db.engine import get_session
    from matchbot.db.models import Post

    async with get_session() as session:
        rows = (
            await session.exec(
                select(Post.platform_post_id).where(
                    Post.platform == platform,
                    Post.platform_post_id.in_(post_ids),
                )
            )
        ).all()
    existing = set(rows)
    return {pid: pid in existing for pid in post_ids}


def _post_exists_batch(platform: str, post_ids: list[str]) -> dict[str, bool]:
    """Synchronous wrapper — runs one DB query for all IDs at once."""
    return asyncio.run(_post_exists_async(platform, post_ids))


async def _replay_one(platform: str, post_id: str, payload: dict) -> None:
    """Reconstruct a Post from a raw payload and run extraction."""
    from matchbot.db.engine import get_session
    from matchbot.db.models import Post, PostStatus
    from matchbot.extraction import process_post
    from matchbot.extraction.anthropic_extractor import AnthropicExtractor
    from matchbot.extraction.openai_extractor import OpenAIExtractor

    settings = get_settings()

    if platform == "reddit":
        from matchbot.listeners.reddit_json import (
            _REDDIT_COMMUNITY,
            _build_source_url,
            _source_created_at_from_json,
        )
        title = (payload.get("title") or "")[:500]
        raw_text = (payload.get("selftext") or "")[:2000]
        author_id = payload.get("author_fullname") or payload.get("author") or "unknown"
        author_display = payload.get("author") or author_id
        source_url = _build_source_url(payload.get("permalink") or payload.get("url") or "")
        source_community = payload.get("subreddit") or _REDDIT_COMMUNITY
        source_created_at = _source_created_at_from_json(payload)

    elif platform == "discord":
        title = (payload.get("content") or "")[:80]
        raw_text = (payload.get("content") or "")[:2000]
        author_id = payload.get("author_id") or ""
        author_display = payload.get("author_display_name") or ""
        source_url = payload.get("jump_url") or ""
        source_community = f"Discord: {payload.get('guild_name') or ''}"
        source_created_at = None

    else:  # facebook
        title = (payload.get("message") or "")[:80]
        raw_text = (payload.get("message") or "")[:2000]
        author_id = (payload.get("from") or {}).get("id") or ""
        author_display = (payload.get("from") or {}).get("name") or ""
        source_url = payload.get("permalink_url") or ""
        source_community = f"Facebook Group: {payload.get('group_id') or ''}"
        source_created_at = None

    post = Post(
        platform=platform,
        platform_post_id=post_id,
        platform_author_id=author_id,
        author_display_name=author_display,
        source_url=source_url,
        source_community=source_community,
        title=title,
        raw_text=raw_text,
        source_created_at=source_created_at,
        status=PostStatus.RAW,
    )

    extractor = AnthropicExtractor() if settings.llm_provider != "openai" else OpenAIExtractor()
    try:
        async with get_session() as session:
            session.add(post)
            await session.commit()
            await session.refresh(post)
            await process_post(session, post, extractor, on_extraction_error="raw")
    finally:
        await extractor.aclose()


@app.command()
def replay(
    platform: str = typer.Option(..., help="Platform to replay: reddit, discord, facebook"),
    date: str | None = typer.Option(
        None, help="Replay only this date (YYYY-MM-DD). Default: all dates."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="List what would be processed without touching the DB."
    ),
) -> None:
    """Re-process raw cached payloads through the extraction pipeline.

    Reads raw JSON files from the data/raw/ directory and feeds each one
    through the same extraction pipeline used by live listeners.
    Posts already in the database are skipped.
    """
    if platform not in _PLATFORM_MAP:
        valid = ", ".join(_PLATFORM_MAP)
        typer.echo(f"Error: Unknown platform '{platform}'. Valid: {valid}", err=True)
        raise typer.Exit(code=1)

    store = _get_raw_store()
    ids = store.list_ids(platform, date=date)

    if not ids:
        typer.echo(
            f"No raw files found for platform={platform}"
            + (f" date={date}" if date else "")
            + "."
        )
        raise typer.Exit()

    typer.echo(
        f"Found {len(ids)} raw file(s) for {platform}"
        + (f" on {date}" if date else "")
        + "."
    )

    # Batch DB lookup — one query for all IDs instead of N queries.
    exists_map = _post_exists_batch(platform, ids)

    async def _run_all() -> tuple[int, int, int]:
        processed = skipped = errors = 0
        for post_id in ids:
            if exists_map.get(post_id):
                typer.echo(f"  [skipped] {post_id} — already in DB")
                skipped += 1
                continue

            payload = store.load(platform, post_id)
            if payload is None:
                typer.echo(f"  [error] {post_id} — file missing or unreadable")
                errors += 1
                continue

            if dry_run:
                typer.echo(f"  [would process] {post_id}")
                processed += 1
                continue

            try:
                await _replay_one(platform, post_id, payload)
                typer.echo(f"  [processed] {post_id}")
                processed += 1
            except Exception as exc:  # noqa: BLE001
                typer.echo(f"  [error] {post_id} — {exc}")
                errors += 1

        return processed, skipped, errors

    processed, skipped, errors = asyncio.run(_run_all())
    typer.echo(f"\nDone. processed={processed} skipped={skipped} errors={errors}")
