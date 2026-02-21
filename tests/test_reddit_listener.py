"""Tests for the Reddit listener."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import select

from matchbot.db.models import Platform, Post, PostStatus
from matchbot.listeners.reddit import _handle_submission


def _make_submission(
    sub_id: str = "abc123",
    title: str = "Seeking camp for Burning Man",
    body: str = "I am looking for a camp. Willing to build.",
    author: str = "burner_user",
    subreddit: str = "BurningMan",
    permalink: str = "/r/BurningMan/comments/abc123/test/",
) -> MagicMock:
    submission = MagicMock()
    submission.id = sub_id
    submission.title = title
    submission.selftext = body
    submission.author = author
    submission.permalink = permalink
    submission.subreddit.display_name = subreddit
    return submission


@pytest.mark.asyncio
async def test_handle_submission_creates_post(db_session, mock_extractor):
    from matchbot.extraction.schemas import ExtractedPost

    mock_extractor.extract.return_value = ExtractedPost(
        role="seeker", vibes=["art"], contribution_types=["build"], confidence=0.85
    )

    submission = _make_submission()

    with patch("matchbot.listeners.reddit._get_extractor", return_value=mock_extractor):
        post = await _handle_submission(submission, db_session)

    assert post is not None
    assert post.platform == Platform.REDDIT
    assert post.platform_post_id == "abc123"
    assert post.status in (PostStatus.INDEXED, PostStatus.NEEDS_REVIEW)


@pytest.mark.asyncio
async def test_handle_submission_deduplicates(db_session, mock_extractor):
    submission = _make_submission(sub_id="dup001")

    # First call
    with patch("matchbot.listeners.reddit._get_extractor", return_value=mock_extractor):
        post1 = await _handle_submission(submission, db_session)

    # Second call — should deduplicate
    with patch("matchbot.listeners.reddit._get_extractor", return_value=mock_extractor):
        post2 = await _handle_submission(submission, db_session)

    assert post1 is not None
    assert post2 is None  # skipped
    # Only one post in DB
    posts = (
        await db_session.exec(
            select(Post).where(Post.platform_post_id == "dup001")
        )
    ).all()
    assert len(posts) == 1


@pytest.mark.asyncio
async def test_handle_submission_skipped_if_no_keyword_match(db_session, mock_extractor):
    submission = _make_submission(
        title="What gear should I bring?",
        body="Packing list advice wanted.",
    )

    with patch("matchbot.listeners.reddit._get_extractor", return_value=mock_extractor):
        post = await _handle_submission(submission, db_session)

    assert post is not None
    assert post.status == PostStatus.SKIPPED
    mock_extractor.extract.assert_not_called()


@pytest.mark.asyncio
async def test_handle_submission_truncates_long_body(db_session, mock_extractor):
    from matchbot.extraction.schemas import ExtractedPost

    mock_extractor.extract.return_value = ExtractedPost(
        role="seeker", confidence=0.9
    )

    long_body = "I am looking for a camp. " * 200  # >2000 chars
    submission = _make_submission(
        sub_id="long001",
        title="Seeking camp",
        body=long_body,
    )

    with patch("matchbot.listeners.reddit._get_extractor", return_value=mock_extractor):
        post = await _handle_submission(submission, db_session)

    assert len(post.raw_text) <= 2000
