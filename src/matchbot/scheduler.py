"""
APScheduler background jobs.

Jobs:
1. expire_stale_posts        — marks INDEXED posts CLOSED_STALE after N days
2. trigger_feedback_surveys  — notes matches ready for feedback (post-intro window)
3. enforce_data_retention    — anonymises/clears raw post text after retention period

The scheduler is created once and started by the FastAPI lifespan hook.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.engine import get_engine
from matchbot.db.models import Match, MatchStatus, Post, PostStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration defaults (all overridable via settings in the future)
# ---------------------------------------------------------------------------

STALE_POST_DAYS: int = 60           # INDEXED posts older than this become CLOSED_STALE
FEEDBACK_WINDOW_DAYS: int = 14      # Days after intro_sent_at to request feedback
RETENTION_DAYS: int = 365           # Days after which raw_text is anonymised
RETENTION_PLACEHOLDER: str = "[content removed for privacy]"


# ---------------------------------------------------------------------------
# Job implementations
# ---------------------------------------------------------------------------


async def expire_stale_posts(_engine=None) -> int:
    """
    Mark INDEXED posts as CLOSED_STALE if they have been idle for STALE_POST_DAYS.

    Returns the number of posts expired.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_POST_DAYS)
    engine = _engine or get_engine()
    expired = 0

    async with AsyncSession(engine, expire_on_commit=False) as session:
        posts = (
            await session.exec(
                select(Post).where(
                    Post.status == PostStatus.INDEXED,
                    Post.detected_at < cutoff,  # type: ignore[operator]
                )
            )
        ).all()

        for post in posts:
            post.status = PostStatus.CLOSED_STALE
            session.add(post)
            expired += 1

        if expired:
            await session.commit()

    logger.info("expire_stale_posts: expired %d posts", expired)
    return expired


async def trigger_feedback_surveys(_engine=None) -> int:
    """
    Identify matches that are past the feedback window and have not yet been
    marked for feedback. Adds a note to moderator_notes.

    Returns the number of matches flagged.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=FEEDBACK_WINDOW_DAYS)
    engine = _engine or get_engine()
    flagged = 0

    async with AsyncSession(engine, expire_on_commit=False) as session:
        matches = (
            await session.exec(
                select(Match).where(
                    Match.status == MatchStatus.INTRO_SENT,
                    Match.intro_sent_at < cutoff,  # type: ignore[operator]
                )
            )
        ).all()

        for match in matches:
            existing = match.moderator_notes or ""
            if "[feedback pending]" not in existing:
                match.moderator_notes = (existing + " [feedback pending]").strip()
                session.add(match)
                flagged += 1

        if flagged:
            await session.commit()

    logger.info("trigger_feedback_surveys: flagged %d matches", flagged)
    return flagged


async def enforce_data_retention(_engine=None) -> int:
    """
    Anonymise raw_text for posts older than RETENTION_DAYS.

    Returns the number of posts anonymised.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    engine = _engine or get_engine()
    anonymised = 0

    async with AsyncSession(engine, expire_on_commit=False) as session:
        posts = (
            await session.exec(
                select(Post).where(
                    Post.detected_at < cutoff,  # type: ignore[operator]
                    Post.raw_text != RETENTION_PLACEHOLDER,
                )
            )
        ).all()

        for post in posts:
            post.raw_text = RETENTION_PLACEHOLDER
            post.title = RETENTION_PLACEHOLDER
            post.author_display_name = ""
            post.platform_author_id = "[redacted]"
            post.contact_method = None
            post.availability_notes = None
            session.add(post)
            anonymised += 1

        if anonymised:
            await session.commit()

    logger.info("enforce_data_retention: anonymised %d posts", anonymised)
    return anonymised


# ---------------------------------------------------------------------------
# Scheduler factory
# ---------------------------------------------------------------------------


def create_scheduler() -> AsyncIOScheduler:
    """
    Build and return a configured AsyncIOScheduler.

    Call scheduler.start() to activate and scheduler.shutdown() to stop.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Run once per hour
    scheduler.add_job(
        expire_stale_posts,
        "interval",
        hours=1,
        id="expire_stale_posts",
        replace_existing=True,
    )

    # Run once per day at 09:00 UTC
    scheduler.add_job(
        trigger_feedback_surveys,
        "cron",
        hour=9,
        minute=0,
        id="trigger_feedback_surveys",
        replace_existing=True,
    )

    # Run once per day at 03:00 UTC (low-traffic window)
    scheduler.add_job(
        enforce_data_retention,
        "cron",
        hour=3,
        minute=0,
        id="enforce_data_retention",
        replace_existing=True,
    )

    return scheduler
