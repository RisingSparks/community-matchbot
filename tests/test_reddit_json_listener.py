from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlmodel import select

from matchbot.db import engine as engine_module
from matchbot.db.engine import create_db_and_tables, get_session
from matchbot.db.models import Platform, Post, PostStatus
from matchbot.listeners import reddit_json
from matchbot.settings import get_settings


def test_is_missing_table_error_detects_undefined_table() -> None:
    err = ProgrammingError(
        'SELECT post.platform_post_id FROM post',
        {},
        Exception('relation "post" does not exist'),
    )
    assert reddit_json._is_missing_table_error(err)


def test_is_missing_table_error_ignores_other_programming_errors() -> None:
    err = ProgrammingError(
        "SELECT * FROM post",
        {},
        Exception("syntax error at or near FROM"),
    )
    assert not reddit_json._is_missing_table_error(err)


@pytest.mark.asyncio
async def test_poll_reddit_json_once_uses_checkpoint_and_persists_skipped_minimal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    mock_extractor,
):
    db_path = tmp_path / "reddit_json_listener.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("REDDIT_JSON_FETCH_LIMIT", "100")
    get_settings.cache_clear()
    engine_module._engine = None

    await create_db_and_tables()

    async with get_session() as session:
        checkpoint = Post(
            platform=Platform.REDDIT,
            platform_post_id="old001",
            platform_author_id="checkpoint_author",
            author_display_name="checkpoint_author",
            source_url="https://reddit.com/r/BurningMan/comments/old001/",
            source_community="BurningMan",
            title="Checkpoint",
            raw_text="already stored",
            status=PostStatus.RAW,
        )
        session.add(checkpoint)
        await session.commit()

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "new_match",
                        "title": "Seeking camp for Burn week",
                        "selftext": "First burner looking for a camp and can help build.",
                        "author": "new_match_author",
                        "author_fullname": "t2_new_match_author",
                        "url_overridden_by_dest": "https://example.org/new-match",
                        "permalink": "/r/BurningMan/comments/new_match/post/",
                    }
                },
                {
                    "data": {
                        "id": "new_skip",
                        "title": "Traffic update for Gate Road",
                        "selftext": "No ask or offer, just weather and traffic chatter.",
                        "author": "new_skip_author",
                        "author_fullname": "t2_new_skip_author",
                        "url": "/r/BurningMan/comments/new_skip/post/",
                        "permalink": "/r/BurningMan/comments/new_skip/post/",
                    }
                },
                {
                    "data": {
                        "id": "old001",
                        "title": "Checkpoint post from previous poll",
                        "selftext": "Should stop here",
                        "author": "checkpoint_author",
                        "permalink": "/r/BurningMan/comments/old001/post/",
                    }
                },
                {
                    "data": {
                        "id": "older_should_not_be_seen",
                        "title": "Older post",
                        "selftext": "Should not be considered",
                        "author": "old_author",
                        "permalink": "/r/BurningMan/comments/older/post/",
                    }
                },
            ]
        }
    }
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)

    async def fake_process_post(session, post, extractor, on_extraction_error="error"):
        post.status = PostStatus.INDEXED
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post

    monkeypatch.setattr(reddit_json, "_get_extractor", lambda: mock_extractor)
    monkeypatch.setattr(reddit_json, "process_post", fake_process_post)

    counts = await reddit_json.poll_reddit_json_once(client=client)

    assert counts["fetched"] == 4
    assert counts["new_candidates"] == 2
    assert counts["matched"] == 1
    assert counts["skipped"] == 1

    async with get_session() as session:
        rows = (await session.exec(select(Post).order_by(Post.platform_post_id))).all()

    post_ids = {p.platform_post_id for p in rows}
    assert "new_match" in post_ids
    assert "new_skip" in post_ids
    assert "old001" in post_ids
    assert "older_should_not_be_seen" not in post_ids

    skipped = next(p for p in rows if p.platform_post_id == "new_skip")
    assert skipped.status == PostStatus.SKIPPED
    assert skipped.raw_text == ""
    assert skipped.source_url.endswith("/new_skip/post/")

    matched = next(p for p in rows if p.platform_post_id == "new_match")
    assert matched.status == PostStatus.INDEXED
    assert matched.platform_author_id == "t2_new_match_author"
    assert matched.author_display_name == "new_match_author"
    assert matched.source_url == "https://reddit.com/r/BurningMan/comments/new_match/post/"

    assert skipped.platform_author_id == "t2_new_skip_author"
    assert skipped.author_display_name == "new_skip_author"
    assert skipped.source_url == "https://reddit.com/r/BurningMan/comments/new_skip/post/"

    engine_module._engine = None


@pytest.mark.asyncio
async def test_poll_reddit_json_once_retries_old_reddit_after_403(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    db_path = tmp_path / "reddit_json_listener_fallback.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("REDDIT_JSON_FETCH_LIMIT", "100")
    get_settings.cache_clear()
    engine_module._engine = None

    await create_db_and_tables()

    blocked_response = MagicMock()
    blocked_response.status_code = 403

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = {"data": {"children": []}}

    client = AsyncMock()
    client.get = AsyncMock(side_effect=[blocked_response, ok_response])

    counts = await reddit_json.poll_reddit_json_once(client=client)

    assert counts["fetched"] == 0
    assert client.get.await_count == 2
    first_call = client.get.await_args_list[0]
    second_call = client.get.await_args_list[1]
    assert first_call.args[0] == "https://www.reddit.com/r/BurningMan/new.json"
    assert second_call.args[0] == "https://old.reddit.com/r/BurningMan/new.json"

    engine_module._engine = None
