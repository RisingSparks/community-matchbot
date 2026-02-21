"""Tests for APScheduler background jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from matchbot.db.models import Match, MatchStatus, Platform, Post, PostRole, PostStatus, PostType
from matchbot.scheduler import (
    FEEDBACK_WINDOW_DAYS,
    RETENTION_DAYS,
    RETENTION_PLACEHOLDER,
    STALE_POST_DAYS,
    enforce_data_retention,
    expire_stale_posts,
    trigger_feedback_surveys,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _old_date(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _make_indexed_post(days_old: int, platform_post_id: str = "test") -> Post:
    return Post(
        platform=Platform.REDDIT,
        platform_post_id=platform_post_id,
        title="Some post",
        raw_text="Some content",
        status=PostStatus.INDEXED,
        post_type=PostType.MENTORSHIP,
        detected_at=_old_date(days_old),
    )


def _make_match_with_intro(days_since_intro: int, suffix: str = "") -> Match:
    tag = suffix or str(days_since_intro)
    return Match(
        seeker_post_id=f"seek_{tag}",
        camp_post_id=f"camp_{tag}",
        status=MatchStatus.INTRO_SENT,
        score=0.8,
        intro_sent_at=_old_date(days_since_intro),
    )


# ---------------------------------------------------------------------------
# expire_stale_posts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expire_stale_posts_marks_old_indexed(db_session):
    """Posts older than STALE_POST_DAYS become CLOSED_STALE."""
    old_post = _make_indexed_post(STALE_POST_DAYS + 1, "old001")
    db_session.add(old_post)
    await db_session.commit()
    await db_session.refresh(old_post)

    count = await expire_stale_posts(_engine=db_session.bind)

    assert count == 1
    await db_session.refresh(old_post)
    assert old_post.status == PostStatus.CLOSED_STALE


@pytest.mark.asyncio
async def test_expire_stale_posts_ignores_recent(db_session):
    """Posts newer than STALE_POST_DAYS are not touched."""
    recent_post = _make_indexed_post(STALE_POST_DAYS - 1, "recent001")
    db_session.add(recent_post)
    await db_session.commit()
    await db_session.refresh(recent_post)

    count = await expire_stale_posts(_engine=db_session.bind)

    assert count == 0
    await db_session.refresh(recent_post)
    assert recent_post.status == PostStatus.INDEXED


@pytest.mark.asyncio
async def test_expire_stale_posts_ignores_non_indexed(db_session):
    """SKIPPED posts are not expired."""
    skipped = Post(
        platform=Platform.REDDIT,
        platform_post_id="skip001",
        title="Skipped",
        raw_text="Content",
        status=PostStatus.SKIPPED,
        detected_at=_old_date(STALE_POST_DAYS + 10),
    )
    db_session.add(skipped)
    await db_session.commit()

    count = await expire_stale_posts(_engine=db_session.bind)

    assert count == 0


# ---------------------------------------------------------------------------
# trigger_feedback_surveys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_feedback_surveys_flags_old_intros(db_session):
    """Matches past the feedback window get [feedback pending] note."""
    match = _make_match_with_intro(FEEDBACK_WINDOW_DAYS + 1, "fb01")
    db_session.add(match)
    await db_session.commit()
    await db_session.refresh(match)

    count = await trigger_feedback_surveys(_engine=db_session.bind)

    assert count == 1
    await db_session.refresh(match)
    assert "[feedback pending]" in (match.moderator_notes or "")


@pytest.mark.asyncio
async def test_trigger_feedback_surveys_ignores_recent_intros(db_session):
    """Matches within the feedback window are not flagged."""
    match = _make_match_with_intro(FEEDBACK_WINDOW_DAYS - 1, "fb02")
    db_session.add(match)
    await db_session.commit()

    count = await trigger_feedback_surveys(_engine=db_session.bind)

    assert count == 0


@pytest.mark.asyncio
async def test_trigger_feedback_surveys_not_duplicate(db_session):
    """Running twice doesn't add duplicate [feedback pending] notes."""
    match = _make_match_with_intro(FEEDBACK_WINDOW_DAYS + 5, "fb03")
    db_session.add(match)
    await db_session.commit()
    await db_session.refresh(match)

    await trigger_feedback_surveys(_engine=db_session.bind)
    count2 = await trigger_feedback_surveys(_engine=db_session.bind)

    # Second run: match already has note, outcome_notes still None but note present
    assert count2 == 0


@pytest.mark.asyncio
async def test_trigger_feedback_surveys_ignores_non_intro_sent(db_session):
    """Only INTRO_SENT matches are considered."""
    match = _make_match_with_intro(FEEDBACK_WINDOW_DAYS + 5, "fb04")
    match.status = MatchStatus.ACCEPTED_PENDING
    db_session.add(match)
    await db_session.commit()

    count = await trigger_feedback_surveys(_engine=db_session.bind)

    assert count == 0


# ---------------------------------------------------------------------------
# enforce_data_retention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_data_retention_anonymises_old_posts(db_session):
    """Posts older than RETENTION_DAYS have raw_text replaced."""
    old_post = Post(
        platform=Platform.REDDIT,
        platform_post_id="retain001",
        title="Old sensitive post",
        raw_text="Personal info here",
        status=PostStatus.INDEXED,
        author_display_name="RealName",
        detected_at=_old_date(RETENTION_DAYS + 1),
    )
    db_session.add(old_post)
    await db_session.commit()
    await db_session.refresh(old_post)

    count = await enforce_data_retention(_engine=db_session.bind)

    assert count == 1
    await db_session.refresh(old_post)
    assert old_post.raw_text == RETENTION_PLACEHOLDER
    assert old_post.title == RETENTION_PLACEHOLDER
    assert old_post.author_display_name == ""


@pytest.mark.asyncio
async def test_enforce_data_retention_ignores_recent_posts(db_session):
    """Posts within the retention period are not touched."""
    recent_post = Post(
        platform=Platform.REDDIT,
        platform_post_id="retain002",
        title="Recent post",
        raw_text="Normal content",
        status=PostStatus.INDEXED,
        detected_at=_old_date(RETENTION_DAYS - 1),
    )
    db_session.add(recent_post)
    await db_session.commit()

    count = await enforce_data_retention(_engine=db_session.bind)

    assert count == 0


@pytest.mark.asyncio
async def test_enforce_data_retention_idempotent(db_session):
    """Running twice on the same post doesn't re-anonymise it."""
    old_post = Post(
        platform=Platform.REDDIT,
        platform_post_id="retain003",
        title="Old post",
        raw_text="Content",
        status=PostStatus.INDEXED,
        detected_at=_old_date(RETENTION_DAYS + 5),
    )
    db_session.add(old_post)
    await db_session.commit()

    count1 = await enforce_data_retention(_engine=db_session.bind)
    count2 = await enforce_data_retention(_engine=db_session.bind)

    assert count1 == 1
    assert count2 == 0  # Already anonymised, raw_text == RETENTION_PLACEHOLDER


# ---------------------------------------------------------------------------
# Scheduler factory
# ---------------------------------------------------------------------------


def test_create_scheduler_has_all_jobs():
    """Scheduler is created with the expected 3 jobs."""
    from matchbot.scheduler import create_scheduler

    scheduler = create_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}

    assert "expire_stale_posts" in job_ids
    assert "trigger_feedback_surveys" in job_ids
    assert "enforce_data_retention" in job_ids
