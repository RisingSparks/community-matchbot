"""Async Reddit listener using asyncpraw streaming."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import asyncpraw
import yaml
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.engine import get_session
from matchbot.db.models import OptOut, Platform, Post, PostStatus
from matchbot.extraction import process_post
from matchbot.extraction.anthropic_extractor import AnthropicExtractor
from matchbot.extraction.openai_extractor import OpenAIExtractor
from matchbot.log_config import log_exception
from matchbot.settings import get_settings

logger = logging.getLogger(__name__)

_SOURCES_PATH = Path(__file__).parent.parent / "config" / "sources.yaml"


def _load_subreddits() -> list[str]:
    with open(_SOURCES_PATH) as f:
        sources = yaml.safe_load(f)
    return sources.get("reddit", {}).get("subreddits", [])


def _get_extractor():
    settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAIExtractor()
    return AnthropicExtractor()


async def _handle_submission(submission, session: AsyncSession) -> Post | None:
    """Process a single Reddit submission."""
    # Deduplication
    existing = (
        await session.exec(
            select(Post).where(
                Post.platform == Platform.REDDIT,
                Post.platform_post_id == submission.id,
            )
        )
    ).first()
    if existing:
        logger.debug("Skipping duplicate Reddit post: %s", submission.id)
        return None

    raw_text = (submission.selftext or "")[:2000]
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id=submission.id,
        platform_author_id=str(submission.author) if submission.author else "unknown",
        author_display_name=str(submission.author) if submission.author else "unknown",
        source_url=f"https://reddit.com{submission.permalink}",
        source_community=submission.subreddit.display_name,
        title=submission.title[:500],
        raw_text=raw_text,
        status=PostStatus.RAW,
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)

    extractor = _get_extractor()
    try:
        post = await process_post(session, post, extractor)
    finally:
        await extractor.aclose()
    logger.info("Reddit post %s → status=%s", submission.id, post.status)
    return post


async def run_reddit_listener() -> None:
    """
    Main Reddit listener loop.
    Streams submissions from allowed subreddits with reconnect logic.
    """
    settings = get_settings()
    subreddits = _load_subreddits()
    if not subreddits:
        logger.warning("No subreddits configured in sources.yaml")
        return

    multi_sub = "+".join(subreddits)
    backoff = 60

    while True:
        try:
            reddit = asyncpraw.Reddit(
                client_id=settings.reddit_client_id,
                client_secret=settings.reddit_client_secret,
                user_agent=settings.reddit_user_agent,
                username=settings.reddit_username,
                password=settings.reddit_password,
            )
            subreddit = await reddit.subreddit(multi_sub)
            logger.info("Reddit listener started on r/%s", multi_sub)

            async for submission in subreddit.stream.submissions(skip_existing=True):
                async with get_session() as session:
                    try:
                        await _handle_submission(submission, session)
                    except Exception as exc:
                        log_exception(
                            logger,
                            "Error processing Reddit submission %s: %s",
                            submission.id,
                            exc,
                        )

            await reddit.close()

        except asyncio.CancelledError:
            logger.info("Reddit listener cancelled.")
            return
        except Exception as exc:
            log_exception(logger, "Reddit listener error: %s - reconnecting in %ss", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 600)
        else:
            backoff = 60


async def run_reddit_inbox_listener() -> None:
    """
    Listen for Reddit inbox messages and handle opt-out requests.
    Streams unread messages and records opt-outs for "opt out" replies.
    """
    settings = get_settings()
    backoff = 60

    while True:
        try:
            reddit = asyncpraw.Reddit(
                client_id=settings.reddit_client_id,
                client_secret=settings.reddit_client_secret,
                user_agent=settings.reddit_user_agent,
                username=settings.reddit_username,
                password=settings.reddit_password,
            )
            logger.info("Reddit inbox listener started.")

            async for message in reddit.inbox.stream(skip_existing=True):
                try:
                    if not hasattr(message, "body"):
                        continue
                    if message.body.strip().lower() == "opt out":
                        author_id = str(message.author) if message.author else None
                        if author_id:
                            async with get_session() as session:
                                opt_out = OptOut(
                                    platform=Platform.REDDIT,
                                    platform_author_id=author_id,
                                )
                                session.add(opt_out)
                                await session.commit()
                            await message.mark_read()
                            await message.reply(
                                "You've been opted out of future introductions. "
                                "You won't receive any more match messages from us."
                            )
                            logger.info("Reddit user %s opted out.", author_id)
                        else:
                            await message.mark_read()
                    else:
                        await message.mark_read()
                except Exception as exc:
                    log_exception(logger, "Error processing Reddit inbox message: %s", exc)

            await reddit.close()

        except asyncio.CancelledError:
            logger.info("Reddit inbox listener cancelled.")
            return
        except Exception as exc:
            log_exception(
                logger,
                "Reddit inbox listener error: %s - reconnecting in %ss",
                exc,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 600)
        else:
            backoff = 60
