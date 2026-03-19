from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def sample_item():
    return {
        "id": "test123",
        "title": "Looking to join a camp",
        "selftext": "I am interested in joining a camp for BM 2026",
        "author": "redditor_jane",
        "author_fullname": "t2_abc",
        "permalink": "/r/BurningMan/comments/test123/looking_to_join/",
        "created_utc": 1700000000,
    }


@pytest.mark.asyncio
async def test_ingest_saves_raw_payload(tmp_path, sample_item, monkeypatch):
    """Raw payload should be saved to disk before DB processing."""
    from matchbot.extraction.keywords import KeywordResult
    from matchbot.listeners import reddit_json as rj
    from matchbot.storage.raw_store import RawStore

    store = RawStore(base_dir=tmp_path)
    monkeypatch.setattr(rj, "_raw_store", store)
    monkeypatch.setattr(rj, "_post_exists", AsyncMock(return_value=False))

    # Keyword filter returns no_match so we skip DB session complexity
    monkeypatch.setattr(
        rj,
        "keyword_filter",
        MagicMock(
            return_value=KeywordResult(
                matched=False, candidate_role="unknown", tier="no_match"
            )
        ),
    )

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_ctx.add = MagicMock()  # session.add is synchronous in SQLAlchemy
    monkeypatch.setattr(rj, "get_session", MagicMock(return_value=mock_ctx))

    await rj._ingest_reddit_json_item(sample_item, extractor=None, dry_run=False)

    # File must exist and contain the full, un-truncated payload
    assert store.exists("reddit", "test123")
    payload = store.load("reddit", "test123")
    assert payload["selftext"] == sample_item["selftext"]
    assert payload["id"] == "test123"


@pytest.mark.asyncio
async def test_ingest_skips_save_when_deduped(tmp_path, sample_item, monkeypatch):
    """Already-seen posts should not be saved again."""
    from matchbot.listeners import reddit_json as rj
    from matchbot.storage.raw_store import RawStore

    store = RawStore(base_dir=tmp_path)
    monkeypatch.setattr(rj, "_raw_store", store)
    monkeypatch.setattr(rj, "_post_exists", AsyncMock(return_value=True))

    outcome, _ = await rj._ingest_reddit_json_item(sample_item, extractor=None, dry_run=False)

    assert outcome == "deduped"
    assert not store.exists("reddit", "test123")
