from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matchbot.storage.raw_store import RawStore


def _make_discord_message(msg_id: str = "111", channel_id: str = "999") -> MagicMock:
    msg = MagicMock()
    msg.id = msg_id
    msg.channel.id = channel_id
    msg.author.bot = False
    msg.author.id = "user_456"
    msg.author.display_name = "BurnerPete"
    msg.content = "Looking to join a camp for BM 2026 — very excited!"
    msg.jump_url = f"https://discord.com/channels/123/{channel_id}/{msg_id}"
    msg.guild.name = "BurningMan"
    msg.created_at = MagicMock()
    msg.created_at.isoformat.return_value = "2026-03-15T10:00:00"
    return msg


@pytest.mark.asyncio
async def test_discord_saves_raw_payload(tmp_path, monkeypatch):
    """Discord handler saves full message content before any truncation."""
    import matchbot.listeners.discord_bot as db

    store = RawStore(base_dir=tmp_path)
    monkeypatch.setattr(db, "_raw_store", store)

    msg = _make_discord_message()
    platform_post_id = f"{msg.channel.id}_{msg.id}"

    # Mock session: exec().first() returns None (new message)
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.object(db, "get_session", return_value=mock_ctx):
        with patch.object(db, "process_post", new=AsyncMock(return_value=MagicMock())):
            with patch.object(db, "_get_extractor", return_value=AsyncMock(aclose=AsyncMock())):
                await db._handle_discord_message(msg)

    assert store.exists("discord", platform_post_id)
    payload = store.load("discord", platform_post_id)
    assert payload["content"] == msg.content  # full content, not truncated


@pytest.mark.asyncio
async def test_discord_skips_save_when_deduped(tmp_path, monkeypatch):
    """Already-seen Discord messages are not saved to disk."""
    import matchbot.listeners.discord_bot as db

    store = RawStore(base_dir=tmp_path)
    monkeypatch.setattr(db, "_raw_store", store)

    msg = _make_discord_message()
    platform_post_id = f"{msg.channel.id}_{msg.id}"

    # Mock session: exec().first() returns an existing post (deduped)
    mock_result = MagicMock()
    mock_result.first.return_value = MagicMock()
    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_result)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.object(db, "get_session", return_value=mock_ctx):
        await db._handle_discord_message(msg)

    assert not store.exists("discord", platform_post_id)
