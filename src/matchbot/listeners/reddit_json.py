"""Reddit JSON poller for unauthenticated stage-1 ingestion."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from sqlmodel import select

from matchbot.db.engine import get_session
from matchbot.db.models import Platform, Post, PostStatus
from matchbot.extraction import process_post
from matchbot.extraction.anthropic_extractor import AnthropicExtractor
from matchbot.extraction.keywords import keyword_filter
from matchbot.extraction.openai_extractor import OpenAIExtractor
from matchbot.log_config import log_exception
from matchbot.settings import get_settings

logger = logging.getLogger(__name__)

_REDDIT_NEW_URL = "https://www.reddit.com/r/BurningMan/new.json"
_REDDIT_NEW_URL_FALLBACK = "https://old.reddit.com/r/BurningMan/new.json"
_REDDIT_COMMUNITY = "BurningMan"


def _get_extractor():
    settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAIExtractor()
    return AnthropicExtractor()


def _build_source_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://reddit.com{url}"
    return f"https://reddit.com/{url}"


async def _latest_reddit_post_id() -> str | None:
    async with get_session() as session:
        row = (
            await session.exec(
                select(Post.platform_post_id)
                .where(
                    Post.platform == Platform.REDDIT,
                    Post.source_community == _REDDIT_COMMUNITY,
                )
                .order_by(Post.detected_at.desc())
                .limit(1)
            )
        ).first()
    return row if row else None


async def _post_exists(platform_post_id: str) -> bool:
    async with get_session() as session:
        existing = (
            await session.exec(
                select(Post.id).where(
                    Post.platform == Platform.REDDIT,
                    Post.platform_post_id == platform_post_id,
                )
            )
        ).first()
    return existing is not None


async def poll_reddit_json_once(client: httpx.AsyncClient | None = None) -> dict[str, int]:
    """Poll Reddit JSON once and ingest posts newer than the latest stored post."""
    settings = get_settings()

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(
            timeout=30,
            headers={
                "User-Agent": settings.reddit_json_user_agent or settings.reddit_user_agent,
                "Accept": "application/json",
            },
        )

    counts = {
        "fetched": 0,
        "new_candidates": 0,
        "deduped": 0,
        "skipped": 0,
        "matched": 0,
        "extracted": 0,
        "raw_after_error": 0,
    }

    try:
        checkpoint_id = await _latest_reddit_post_id()

        params = {"limit": settings.reddit_json_fetch_limit, "raw_json": 1}
        response = await client.get(_REDDIT_NEW_URL, params=params)
        if response.status_code == 403:
            logger.warning(
                (
                    "Reddit JSON endpoint blocked request from %s; "
                    "retrying via fallback endpoint. "
                    "Set REDDIT_JSON_USER_AGENT to a descriptive value "
                    "(e.g. 'matchbot/0.1 by u/<username>')."
                ),
                _REDDIT_NEW_URL,
            )
            response = await client.get(_REDDIT_NEW_URL_FALLBACK, params=params)

        response.raise_for_status()
        payload = response.json()

        children = payload.get("data", {}).get("children", [])
        counts["fetched"] = len(children)

        new_items: list[dict[str, Any]] = []
        for child in children:
            data = child.get("data", {})
            post_id = data.get("id")
            if not post_id:
                continue
            if checkpoint_id and post_id == checkpoint_id:
                break
            new_items.append(data)

        counts["new_candidates"] = len(new_items)

        extractor = None
        try:
            for data in reversed(new_items):  # process oldest->newest
                post_id = data.get("id")
                if not post_id:
                    continue

                if await _post_exists(post_id):
                    counts["deduped"] += 1
                    continue

                title = (data.get("title") or "")[:500]
                body = (data.get("selftext") or "")[:2000]
                author_id = data.get("author_fullname") or data.get("author") or "unknown"
                author_display = data.get("author") or author_id
                permalink = data.get("permalink") or ""
                # Canonicalize Reddit posts to their permalink in source_url.
                # If permalink is missing, fall back to available URL fields.
                source_url = _build_source_url(
                    permalink
                    or data.get("url_overridden_by_dest")
                    or data.get("url")
                )

                kw_result = keyword_filter(title, body)

                async with get_session() as session:
                    if not kw_result.matched:
                        post = Post(
                            platform=Platform.REDDIT,
                            platform_post_id=post_id,
                            platform_author_id=author_id,
                            author_display_name=author_display,
                            source_url=source_url,
                            source_community=_REDDIT_COMMUNITY,
                            title=title,
                            raw_text="",
                            status=PostStatus.SKIPPED,
                            extraction_method="keyword",
                        )
                        session.add(post)
                        await session.commit()
                        counts["skipped"] += 1
                        continue

                    post = Post(
                        platform=Platform.REDDIT,
                        platform_post_id=post_id,
                        platform_author_id=author_id,
                        author_display_name=author_display,
                        source_url=source_url,
                        source_community=_REDDIT_COMMUNITY,
                        title=title,
                        raw_text=body,
                        status=PostStatus.RAW,
                    )
                    session.add(post)
                    await session.commit()
                    await session.refresh(post)

                    if extractor is None:
                        extractor = _get_extractor()

                    before_status = post.status
                    post = await process_post(
                        session,
                        post,
                        extractor,
                        on_extraction_error="raw",
                    )
                    counts["matched"] += 1
                    if post.status == PostStatus.RAW and before_status == PostStatus.RAW:
                        counts["raw_after_error"] += 1
                    else:
                        counts["extracted"] += 1
        finally:
            if extractor is not None:
                await extractor.aclose()

        return counts
    finally:
        if owns_client and client is not None:
            await client.aclose()


async def run_reddit_json_listener() -> None:
    """Poll Reddit JSON at a fixed interval with reconnect/backoff behavior."""
    settings = get_settings()
    if not settings.reddit_json_enabled:
        logger.info("Reddit JSON listener disabled (REDDIT_JSON_ENABLED=false).")
        return

    backoff = 30

    while True:
        try:
            counts = await poll_reddit_json_once()
            logger.info(
                (
                    "Reddit JSON poll complete: fetched=%d new=%d matched=%d "
                    "skipped=%d deduped=%d raw_after_error=%d"
                ),
                counts["fetched"],
                counts["new_candidates"],
                counts["matched"],
                counts["skipped"],
                counts["deduped"],
                counts["raw_after_error"],
            )
            backoff = 30
            await asyncio.sleep(settings.reddit_json_poll_interval_seconds)
        except asyncio.CancelledError:
            logger.info("Reddit JSON listener cancelled.")
            return
        except Exception as exc:
            log_exception(
                logger,
                "Reddit JSON listener error: %s - retrying in %ss",
                exc,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 600)
