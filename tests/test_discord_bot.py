"""Tests for the Discord bot listener."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import select

from matchbot.db.models import Platform, Post, PostStatus
from matchbot.listeners.discord_bot import _handle_discord_message
from matchbot.storage.raw_store import RawStore


def _make_discord_message(
    content: str = "Seeking camp for Burning Man 2025",
    author_id: str = "123456789",
    author_name: str = "burner_user",
    channel_id: str = "CHANNEL_ID_1",
    message_id: str = "msg001",
    guild_name: str = "Rising Sparks",
    jump_url: str = "https://discord.com/channels/123/456/789",
) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.author.id = int(author_id)
    msg.author.display_name = author_name
    msg.author.bot = False
    msg.channel.id = int(channel_id.replace("CHANNEL_ID_", "9"))
    msg.id = int(message_id.replace("msg", "100"))
    msg.guild.name = guild_name
    msg.jump_url = jump_url
    msg.created_at = MagicMock()
    msg.created_at.isoformat.return_value = "2026-03-15T10:00:00"
    return msg


@pytest.mark.asyncio
async def test_handle_discord_message_creates_post(tmp_path, db_session, mock_extractor):
    import matchbot.listeners.discord_bot as db_module
    from matchbot.extraction.schemas import ExtractedPost

    mock_extractor.extract.return_value = ExtractedPost(
        role="seeker", vibes=["art"], contribution_types=["build"], confidence=0.85
    )

    msg = _make_discord_message()

    with (
        patch("matchbot.listeners.discord_bot.get_session") as mock_session_factory,
        patch("matchbot.listeners.discord_bot._get_extractor", return_value=mock_extractor),
        patch.object(db_module, "_raw_store", RawStore(base_dir=tmp_path)),
    ):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_factory():
            yield db_session

        mock_session_factory.return_value = mock_factory()
        await _handle_discord_message(msg)

    posts = (
        await db_session.exec(select(Post).where(Post.platform == Platform.DISCORD))
    ).all()
    assert len(posts) >= 1
    assert posts[0].author_display_name == "burner_user"


@pytest.mark.asyncio
async def test_handle_discord_message_deduplicates(tmp_path, db_session, mock_extractor):
    import matchbot.listeners.discord_bot as db_module
    from matchbot.extraction.schemas import ExtractedPost

    mock_extractor.extract.return_value = ExtractedPost(role="seeker", confidence=0.9)
    msg = _make_discord_message(
        content="Seeking camp for BM",
        channel_id="CHANNEL_ID_1",
        message_id="msg999",
    )

    with (
        patch("matchbot.listeners.discord_bot.get_session") as mock_session_factory,
        patch("matchbot.listeners.discord_bot._get_extractor", return_value=mock_extractor),
        patch.object(db_module, "_raw_store", RawStore(base_dir=tmp_path)),
    ):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_factory():
            yield db_session

        mock_session_factory.side_effect = [mock_factory(), mock_factory()]
        await _handle_discord_message(msg)
        await _handle_discord_message(msg)

    posts = (
        await db_session.exec(
            select(Post).where(Post.platform == Platform.DISCORD)
        )
    ).all()
    assert len(posts) == 1  # deduplicated


@pytest.mark.asyncio
async def test_handle_discord_message_no_keyword_match_skips(tmp_path, db_session, mock_extractor):
    import matchbot.listeners.discord_bot as db_module

    msg = _make_discord_message(content="What's the weather like on playa?")

    with (
        patch("matchbot.listeners.discord_bot.get_session") as mock_session_factory,
        patch("matchbot.listeners.discord_bot._get_extractor", return_value=mock_extractor),
        patch.object(db_module, "_raw_store", RawStore(base_dir=tmp_path)),
    ):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_factory():
            yield db_session

        mock_session_factory.return_value = mock_factory()
        await _handle_discord_message(msg)

    posts = (
        await db_session.exec(select(Post).where(Post.platform == Platform.DISCORD))
    ).all()
    if posts:
        assert posts[0].status == PostStatus.SKIPPED
        assert posts[0].post_type is None
    mock_extractor.extract.assert_not_called()
