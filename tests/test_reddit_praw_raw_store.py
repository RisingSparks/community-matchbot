from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matchbot.storage.raw_store import RawStore


def _make_submission(post_id: str = "praw123") -> MagicMock:
    """Build a minimal mock of an asyncpraw Submission."""
    sub = MagicMock()
    sub.id = post_id
    sub.title = "Seeking camp for 2026"
    sub.selftext = "Full body text here — not truncated"
    sub.author = MagicMock()
    sub.author.__str__ = lambda s: "praw_user"
    sub.author_fullname = "t2_praw"
    sub.permalink = f"/r/BurningMan/comments/{post_id}/"
    sub.url = f"https://reddit.com/r/BurningMan/comments/{post_id}/"
    sub.created_utc = 1700000000.0
    sub.subreddit = MagicMock()
    sub.subreddit.display_name = "BurningMan"
    sub.score = 5
    sub.num_comments = 2
    return sub


@pytest.mark.asyncio
async def test_praw_saves_raw_payload(tmp_path, monkeypatch):
    """PRAW listener saves full submission fields before any truncation."""
    import matchbot.listeners.reddit as rl

    store = RawStore(base_dir=tmp_path)
    monkeypatch.setattr(rl, "_raw_store", store)

    sub = _make_submission()

    # Mock session: exec().first() returns None (no existing post = not deduped)
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()

    with patch.object(rl, "process_post", new=AsyncMock(return_value=MagicMock())):
        with patch.object(rl, "_get_extractor", return_value=AsyncMock(aclose=AsyncMock())):
            await rl._handle_submission(sub, mock_session)

    assert store.exists("reddit", "praw123")
    payload = store.load("reddit", "praw123")
    assert payload["selftext"] == sub.selftext  # full text, no truncation
    assert payload["id"] == "praw123"


@pytest.mark.asyncio
async def test_praw_skips_save_when_deduped(tmp_path, monkeypatch):
    """Already-seen PRAW submissions are not saved to disk."""
    import matchbot.listeners.reddit as rl

    store = RawStore(base_dir=tmp_path)
    monkeypatch.setattr(rl, "_raw_store", store)

    sub = _make_submission()

    # Mock session: exec().first() returns an existing post (deduped)
    mock_result = MagicMock()
    mock_result.first.return_value = MagicMock()  # existing post found
    mock_session = AsyncMock()
    mock_session.exec = AsyncMock(return_value=mock_result)

    await rl._handle_submission(sub, mock_session)

    assert not store.exists("reddit", "praw123")
