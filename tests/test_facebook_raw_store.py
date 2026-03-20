from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matchbot.storage.raw_store import RawStore


def _make_feed_value(post_id: str = "123_456") -> dict:
    return {
        "post_id": post_id,
        "message": "Looking to join a Burning Man camp for 2026!",
        "from": {"id": "user_789", "name": "Jane Burner"},
        "permalink_url": "https://facebook.com/groups/123/posts/456",
        "group_id": "group_123",
    }


@pytest.mark.asyncio
async def test_facebook_saves_raw_payload(tmp_path, monkeypatch):
    """Facebook handler saves full payload with stable post_id."""
    import matchbot.listeners.facebook as fb

    store = RawStore(base_dir=tmp_path)
    monkeypatch.setattr(fb, "_raw_store", store)

    value = _make_feed_value(post_id="123_456")

    # Mock session: exec().first() returns None (new post)
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.object(fb, "get_session", return_value=mock_ctx):
        with patch.object(fb, "process_post", new=AsyncMock(return_value=MagicMock())):
            with patch.object(fb, "_get_extractor", return_value=AsyncMock(aclose=AsyncMock())):
                await fb._handle_feed_change(value)

    assert store.exists("facebook", "123_456")
    payload = store.load("facebook", "123_456")
    assert payload["message"] == value["message"]


@pytest.mark.asyncio
async def test_facebook_skips_save_when_deduped(tmp_path, monkeypatch):
    """Already-seen Facebook posts are not saved."""
    import matchbot.listeners.facebook as fb

    store = RawStore(base_dir=tmp_path)
    monkeypatch.setattr(fb, "_raw_store", store)

    value = _make_feed_value(post_id="123_456")

    mock_result = MagicMock()
    mock_result.first.return_value = MagicMock()  # existing post
    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_result)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.object(fb, "get_session", return_value=mock_ctx):
        await fb._handle_feed_change(value)

    assert not store.exists("facebook", "123_456")


@pytest.mark.asyncio
async def test_facebook_skips_save_when_uuid_fallback(tmp_path, monkeypatch):
    """Posts with no stable platform ID (UUID fallback) are not saved."""
    import matchbot.listeners.facebook as fb

    store = RawStore(base_dir=tmp_path)
    monkeypatch.setattr(fb, "_raw_store", store)

    # No post_id or id in the value dict — triggers UUID fallback
    value = {
        "message": "Looking for a camp",
        "from": {"id": "user_789", "name": "Jane Burner"},
    }

    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.object(fb, "get_session", return_value=mock_ctx):
        with patch.object(fb, "process_post", new=AsyncMock(return_value=MagicMock())):
            with patch.object(fb, "_get_extractor", return_value=AsyncMock(aclose=AsyncMock())):
                await fb._handle_feed_change(value)

    # No files should be saved since there's no stable ID
    assert store.list_ids("facebook") == []
