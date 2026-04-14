from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy.exc import ProgrammingError
from sqlmodel import select

from matchbot.db import engine as engine_module
from matchbot.db.engine import create_db_and_tables, get_session
from matchbot.db.models import Platform, Post, PostRole, PostStatus, PostType
from matchbot.extraction.keywords import KeywordResult
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


def test_build_reddit_json_headers_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDDIT_JSON_USER_AGENT", "json-agent")
    monkeypatch.setenv("REDDIT_USER_AGENT", "fallback-agent")
    monkeypatch.setenv("REDDIT_JSON_EMULATE_BROWSER", "false")
    monkeypatch.delenv("REDDIT_JSON_COOKIE", raising=False)
    get_settings.cache_clear()

    headers = reddit_json._build_reddit_json_headers()

    assert headers == {
        "User-Agent": "json-agent",
        "Accept": "application/json",
    }


def test_build_reddit_json_headers_browser_emulation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDDIT_JSON_USER_AGENT", "browser-agent")
    monkeypatch.setenv("REDDIT_JSON_EMULATE_BROWSER", "true")
    monkeypatch.setenv("REDDIT_JSON_COOKIE", "session=abc123")
    get_settings.cache_clear()

    headers = reddit_json._build_reddit_json_headers()

    assert headers["User-Agent"] == "browser-agent"
    assert headers["Accept"].startswith("text/html")
    assert headers["Sec-Fetch-Mode"] == "navigate"
    assert headers["Cookie"] == "session=abc123"


def test_build_source_url_strips_reddit_query_and_fragment() -> None:
    url = (
        "https://www.reddit.com/r/BurningMan/comments/1siozo1/post/"
        "?solution=abc123&js_challenge=1#section"
    )

    assert (
        reddit_json._build_source_url(url)
        == "https://www.reddit.com/r/BurningMan/comments/1siozo1/post/"
    )


def test_build_source_url_strips_reddit_query_from_relative_permalink() -> None:
    assert (
        reddit_json._build_source_url("/r/BurningMan/comments/1siozo1/post/?foo=bar")
        == "https://reddit.com/r/BurningMan/comments/1siozo1/post/"
    )


@pytest.mark.asyncio
async def test_poll_reddit_json_once_uses_checkpoint_and_persists_skipped_with_body(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    mock_extractor,
):
    db_path = tmp_path / "reddit_json_listener.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("REDDIT_JSON_FETCH_LIMIT", "100")
    monkeypatch.setenv("REDDIT_JSON_MAX_CONCURRENT_EXTRACTIONS", "1")
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
                        "created_utc": 1735819200,
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
                        "created_utc": 1735905600,
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
    assert skipped.post_type is None
    assert skipped.raw_text == "No ask or offer, just weather and traffic chatter."
    assert skipped.source_url.endswith("/new_skip/post/")
    assert skipped.source_created_at == datetime.fromtimestamp(1735905600, UTC).replace(tzinfo=None)

    matched = next(p for p in rows if p.platform_post_id == "new_match")
    assert matched.status == PostStatus.INDEXED
    assert matched.platform_author_id == "t2_new_match_author"
    assert matched.author_display_name == "new_match_author"
    assert matched.source_url == "https://reddit.com/r/BurningMan/comments/new_match/post/"
    assert matched.source_created_at == datetime.fromtimestamp(1735819200, UTC).replace(tzinfo=None)

    assert skipped.platform_author_id == "t2_new_skip_author"
    assert skipped.author_display_name == "new_skip_author"
    assert skipped.source_url == "https://reddit.com/r/BurningMan/comments/new_skip/post/"

    engine_module._engine = None


@pytest.mark.asyncio
async def test_poll_reddit_json_once_persists_soft_match_without_llm(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    mock_extractor,
):
    db_path = tmp_path / "reddit_json_listener_soft.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("REDDIT_JSON_FETCH_LIMIT", "100")
    monkeypatch.setenv("REDDIT_JSON_MAX_CONCURRENT_EXTRACTIONS", "1")
    get_settings.cache_clear()
    engine_module._engine = None

    await create_db_and_tables()

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "soft_match",
                        "title": "Regional Burn intro",
                        "selftext": "Any camp recs for someone into fire spinning?",
                        "author": "soft_author",
                        "author_fullname": "t2_soft_author",
                        "permalink": "/r/BurningMan/comments/soft_match/post/",
                        "created_utc": 1735905600,
                    }
                }
            ]
        }
    }
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    monkeypatch.setattr(
        reddit_json,
        "keyword_filter",
        lambda title, body: KeywordResult(
            matched=False,
            candidate_role=PostRole.UNKNOWN,
            post_type=PostType.INFRASTRUCTURE,
            infra_role="seeking",
            tier="soft_match",
            score=3,
            reasons=("test_soft_match",),
        ),
    )
    monkeypatch.setattr(reddit_json, "_get_extractor", lambda: mock_extractor)

    async def fake_process_post(session, post, extractor, on_extraction_error="error"):
        post.status = PostStatus.NEEDS_REVIEW
        post.post_type = PostType.INFRASTRUCTURE
        post.infra_role = "seeking"
        post.role = PostRole.UNKNOWN
        post.extraction_method = "keyword_soft"
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post

    monkeypatch.setattr(reddit_json, "process_post", fake_process_post)

    counts = await reddit_json.poll_reddit_json_once(client=client)

    assert counts["matched"] == 1
    assert counts["skipped"] == 0

    async with get_session() as session:
        row = (
            await session.exec(select(Post).where(Post.platform_post_id == "soft_match"))
        ).one()

    assert row.status == PostStatus.NEEDS_REVIEW
    assert row.extraction_method == "keyword_soft"
    assert row.raw_text.startswith("Any camp recs")
    mock_extractor.extract.assert_not_called()

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
    monkeypatch.setenv("REDDIT_JSON_MAX_CONCURRENT_EXTRACTIONS", "1")
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
    sleep = AsyncMock()
    monkeypatch.setattr(reddit_json.asyncio, "sleep", sleep)

    counts = await reddit_json.poll_reddit_json_once(client=client)

    assert counts["fetched"] == 0
    assert client.get.await_count == 2
    sleep.assert_awaited_once_with(reddit_json._REDDIT_BLOCK_RETRY_DELAY_SECONDS)
    first_call = client.get.await_args_list[0]
    second_call = client.get.await_args_list[1]
    assert first_call.args[0] == "https://www.reddit.com/r/BurningMan/new.json"
    assert second_call.args[0] == "https://old.reddit.com/r/BurningMan/new.json"

    engine_module._engine = None


@pytest.mark.asyncio
async def test_fetch_reddit_json_page_retries_old_reddit_after_429_with_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked_response = MagicMock()
    blocked_response.status_code = 429
    blocked_response.headers = {"Retry-After": "12.5"}

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.headers = {}
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = {"data": {"children": []}}

    client = AsyncMock()
    client.get = AsyncMock(side_effect=[blocked_response, ok_response])
    sleep = AsyncMock()
    monkeypatch.setattr(reddit_json.asyncio, "sleep", sleep)

    payload = await reddit_json._fetch_reddit_json_page(client, limit=25)

    assert payload == {"data": {"children": []}}
    sleep.assert_awaited_once_with(12.5)
    assert client.get.await_count == 2


@pytest.mark.asyncio
async def test_fetch_reddit_json_page_raises_when_primary_and_fallback_are_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked_primary = MagicMock()
    blocked_primary.status_code = 403
    blocked_primary.headers = {}

    blocked_fallback = MagicMock()
    blocked_fallback.status_code = 429
    blocked_fallback.headers = {"Retry-After": "45"}
    blocked_fallback.raise_for_status.side_effect = httpx.HTTPStatusError(
        "blocked",
        request=MagicMock(),
        response=blocked_fallback,
    )

    client = AsyncMock()
    client.get = AsyncMock(side_effect=[blocked_primary, blocked_fallback])
    sleep = AsyncMock()
    monkeypatch.setattr(reddit_json.asyncio, "sleep", sleep)

    with pytest.raises(httpx.HTTPStatusError):
        await reddit_json._fetch_reddit_json_page(client, limit=25)

    sleep.assert_awaited_once_with(reddit_json._REDDIT_BLOCK_RETRY_DELAY_SECONDS)
    assert client.get.await_count == 2


def test_retry_delay_seconds_uses_default_for_zero_or_invalid_retry_after() -> None:
    zero_response = MagicMock()
    zero_response.headers = {"Retry-After": "0"}

    invalid_response = MagicMock()
    invalid_response.headers = {"Retry-After": "not-a-number"}

    assert (
        reddit_json._retry_delay_seconds(zero_response)
        == reddit_json._REDDIT_BLOCK_RETRY_DELAY_SECONDS
    )
    assert (
        reddit_json._retry_delay_seconds(invalid_response)
        == reddit_json._REDDIT_BLOCK_RETRY_DELAY_SECONDS
    )


@pytest.mark.asyncio
async def test_backfill_reddit_json_pages_with_after_and_stops_at_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDDIT_JSON_MAX_CONCURRENT_EXTRACTIONS", "1")
    get_settings.cache_clear()
    cutoff = datetime.fromtimestamp(180, UTC).replace(tzinfo=None)
    seen_ids: list[str] = []

    async def fake_ingest(data, extractor, *, dry_run):
        seen_ids.append(data["id"])
        return "skipped", extractor

    monkeypatch.setattr(reddit_json, "_ingest_reddit_json_item", fake_ingest)

    page_1 = MagicMock()
    page_1.status_code = 200
    page_1.raise_for_status.return_value = None
    page_1.json.return_value = {
        "data": {
            "after": "t3_page1",
            "children": [
                {"data": {"id": "newest", "created_utc": 220}},
                {"data": {"id": "older", "created_utc": 210}},
            ],
        }
    }

    page_2 = MagicMock()
    page_2.status_code = 200
    page_2.raise_for_status.return_value = None
    page_2.json.return_value = {
        "data": {
            "after": "t3_page2",
            "children": [
                {"data": {"id": "at_cutoff", "created_utc": 200}},
                {"data": {"id": "too_old", "created_utc": 170}},
            ],
        }
    }

    client = AsyncMock()
    client.get = AsyncMock(side_effect=[page_1, page_2])

    counts = await reddit_json.backfill_reddit_json(
        cutoff,
        fetch_limit=100,
        sleep_seconds=0,
        max_pages=10,
        dry_run=False,
        client=client,
    )

    assert counts["pages"] == 2
    assert counts["fetched"] == 4
    assert counts["new_candidates"] == 3
    assert seen_ids == ["older", "newest", "at_cutoff"]
    assert client.get.await_args_list[0].kwargs["params"] == {"limit": 100, "raw_json": 1}
    assert client.get.await_args_list[1].kwargs["params"] == {
        "limit": 100,
        "raw_json": 1,
        "after": "t3_page1",
    }


@pytest.mark.asyncio
async def test_backfill_reddit_json_retries_blocked_fetch_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDDIT_JSON_MAX_CONCURRENT_EXTRACTIONS", "1")
    get_settings.cache_clear()

    blocked_primary = MagicMock()
    blocked_primary.status_code = 403
    blocked_primary.headers = {"Retry-After": "0"}

    blocked_fallback = MagicMock()
    blocked_fallback.status_code = 403
    blocked_fallback.headers = {"Retry-After": "0"}
    blocked_fallback.raise_for_status.side_effect = httpx.HTTPStatusError(
        "blocked",
        request=MagicMock(),
        response=blocked_fallback,
    )

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.headers = {}
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = {
        "data": {
            "after": None,
            "children": [
                {"data": {"id": "newest", "created_utc": 220}},
            ],
        }
    }

    client = AsyncMock()
    client.get = AsyncMock(side_effect=[blocked_primary, blocked_fallback, ok_response])
    sleep = AsyncMock()
    monkeypatch.setattr(reddit_json.asyncio, "sleep", sleep)

    seen_ids: list[str] = []

    async def fake_ingest(data, extractor, *, dry_run):
        seen_ids.append(data["id"])
        return "skipped", extractor

    monkeypatch.setattr(reddit_json, "_ingest_reddit_json_item", fake_ingest)

    counts = await reddit_json.backfill_reddit_json(
        datetime.fromtimestamp(200, UTC).replace(tzinfo=None),
        fetch_limit=100,
        sleep_seconds=0,
        max_pages=5,
        dry_run=False,
        client=client,
    )

    assert counts["pages"] == 1
    assert counts["fetched"] == 1
    assert seen_ids == ["newest"]
    assert sleep.await_args_list == [
        ((reddit_json._REDDIT_BLOCK_RETRY_DELAY_SECONDS,), {}),
        ((reddit_json._REDDIT_BLOCK_RETRY_DELAY_SECONDS,), {}),
    ]


@pytest.mark.asyncio
async def test_backfill_reddit_json_dedupes_and_runs_same_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    mock_extractor,
) -> None:
    db_path = tmp_path / "reddit_json_backfill.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("REDDIT_JSON_MAX_CONCURRENT_EXTRACTIONS", "1")
    get_settings.cache_clear()
    engine_module._engine = None

    await create_db_and_tables()

    async with get_session() as session:
        existing = Post(
            platform=Platform.REDDIT,
            platform_post_id="dup01",
            platform_author_id="author_dup",
            author_display_name="author_dup",
            source_url="https://reddit.com/r/BurningMan/comments/dup01/",
            source_community="BurningMan",
            title="Existing post",
            raw_text="already here",
            status=PostStatus.INDEXED,
        )
        session.add(existing)
        await session.commit()

    response = MagicMock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": {
            "after": None,
            "children": [
                {
                    "data": {
                        "id": "new_match",
                        "title": "Looking for camp and can help build",
                        "selftext": "Can help with setup and teardown.",
                        "author": "new_match_author",
                        "author_fullname": "t2_new_match_author",
                        "permalink": "/r/BurningMan/comments/new_match/post/",
                        "created_utc": 220,
                    }
                },
                {
                    "data": {
                        "id": "dup01",
                        "title": "Duplicate existing",
                        "selftext": "Should dedupe.",
                        "author": "author_dup",
                        "permalink": "/r/BurningMan/comments/dup01/post/",
                        "created_utc": 215,
                    }
                },
                {
                    "data": {
                        "id": "new_skip",
                        "title": "Road update only",
                        "selftext": "No ask/offer here.",
                        "author": "new_skip_author",
                        "author_fullname": "t2_new_skip_author",
                        "permalink": "/r/BurningMan/comments/new_skip/post/",
                        "created_utc": 210,
                    }
                },
            ],
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

    counts = await reddit_json.backfill_reddit_json(
        datetime.fromtimestamp(200, UTC).replace(tzinfo=None),
        fetch_limit=100,
        sleep_seconds=0,
        max_pages=5,
        dry_run=False,
        client=client,
    )

    assert counts["pages"] == 1
    assert counts["fetched"] == 3
    assert counts["new_candidates"] == 3
    assert counts["deduped"] == 1
    assert counts["matched"] == 1
    assert counts["skipped"] == 1
    assert counts["extracted"] == 1

    async with get_session() as session:
        rows = (await session.exec(select(Post).order_by(Post.platform_post_id))).all()

    status_by_id = {row.platform_post_id: row.status for row in rows}
    assert status_by_id["dup01"] == PostStatus.INDEXED
    assert status_by_id["new_match"] == PostStatus.INDEXED
    assert status_by_id["new_skip"] == PostStatus.SKIPPED
    engine_module._engine = None


@pytest.mark.asyncio
async def test_backfill_reddit_json_retries_existing_raw_post(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    mock_extractor,
) -> None:
    db_path = tmp_path / "reddit_json_backfill_retry_raw.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("REDDIT_JSON_MAX_CONCURRENT_EXTRACTIONS", "1")
    get_settings.cache_clear()
    engine_module._engine = None

    await create_db_and_tables()

    async with get_session() as session:
        existing = Post(
            platform=Platform.REDDIT,
            platform_post_id="raw01",
            platform_author_id="author_raw",
            author_display_name="author_raw",
            source_url="https://reddit.com/r/BurningMan/comments/raw01/",
            source_community="BurningMan",
            title="Existing raw post",
            raw_text="still needs extraction",
            status=PostStatus.RAW,
        )
        session.add(existing)
        await session.commit()

    response = MagicMock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": {
            "after": None,
            "children": [
                {
                    "data": {
                        "id": "raw01",
                        "title": "Existing raw post",
                        "selftext": "still needs extraction",
                        "author": "author_raw",
                        "author_fullname": "t2_author_raw",
                        "permalink": "/r/BurningMan/comments/raw01/post/",
                        "created_utc": 220,
                    }
                }
            ],
        }
    }
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)

    retried_ids: list[str] = []

    async def fake_process_post(session, post, extractor, on_extraction_error="error"):
        retried_ids.append(post.platform_post_id)
        post.status = PostStatus.INDEXED
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post

    monkeypatch.setattr(reddit_json, "_get_extractor", lambda: mock_extractor)
    monkeypatch.setattr(reddit_json, "process_post", fake_process_post)

    counts = await reddit_json.backfill_reddit_json(
        datetime.fromtimestamp(200, UTC).replace(tzinfo=None),
        fetch_limit=100,
        sleep_seconds=0,
        max_pages=5,
        dry_run=False,
        client=client,
    )

    assert retried_ids == ["raw01"]
    assert counts["deduped"] == 0
    assert counts["matched"] == 1
    assert counts["extracted"] == 1

    async with get_session() as session:
        row = (
            await session.exec(select(Post).where(Post.platform_post_id == "raw01"))
        ).one()

    assert row.status == PostStatus.INDEXED
    engine_module._engine = None


@pytest.mark.asyncio
async def test_backfill_reddit_json_retries_transient_db_disconnect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    mock_extractor,
) -> None:
    db_path = tmp_path / "reddit_json_backfill_retry_disconnect.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("REDDIT_JSON_MAX_CONCURRENT_EXTRACTIONS", "1")
    get_settings.cache_clear()
    engine_module._engine = None

    await create_db_and_tables()

    response = MagicMock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": {
            "after": None,
            "children": [
                {
                    "data": {
                        "id": "disconnect01",
                        "title": "Looking for camp",
                        "selftext": "Can help with build.",
                        "author": "disconnect_author",
                        "author_fullname": "t2_disconnect_author",
                        "permalink": "/r/BurningMan/comments/disconnect01/post/",
                        "created_utc": 220,
                    }
                }
            ],
        }
    }
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)

    class FakeDisconnectError(RuntimeError):
        pass

    process_attempts = 0
    dispose_calls = 0

    async def fake_process_post(session, post, extractor, on_extraction_error="error"):
        nonlocal process_attempts
        process_attempts += 1
        if process_attempts == 1:
            raise FakeDisconnectError("connection is closed")
        post.status = PostStatus.INDEXED
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post

    async def fake_dispose_engine() -> None:
        nonlocal dispose_calls
        dispose_calls += 1

    monkeypatch.setattr(reddit_json, "_get_extractor", lambda: mock_extractor)
    monkeypatch.setattr(reddit_json, "process_post", fake_process_post)
    monkeypatch.setattr(
        reddit_json,
        "is_disconnect_error",
        lambda exc: isinstance(exc, FakeDisconnectError),
    )
    monkeypatch.setattr(reddit_json, "dispose_engine", fake_dispose_engine)

    counts = await reddit_json.backfill_reddit_json(
        datetime.fromtimestamp(200, UTC).replace(tzinfo=None),
        fetch_limit=100,
        sleep_seconds=0,
        max_pages=5,
        dry_run=False,
        client=client,
    )

    assert process_attempts == 2
    assert dispose_calls == 1
    assert counts["matched"] == 1
    assert counts["extracted"] == 1
    assert counts["raw_after_error"] == 0

    async with get_session() as session:
        row = (
            await session.exec(select(Post).where(Post.platform_post_id == "disconnect01"))
        ).one()

    assert row.status == PostStatus.INDEXED
    engine_module._engine = None


@pytest.mark.asyncio
async def test_backfill_reddit_json_dry_run_does_not_write_or_extract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "reddit_json_backfill_dry_run.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("REDDIT_JSON_MAX_CONCURRENT_EXTRACTIONS", "1")
    get_settings.cache_clear()
    engine_module._engine = None

    await create_db_and_tables()

    response = MagicMock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": {
            "after": None,
            "children": [
                {
                    "data": {
                        "id": "matched_candidate",
                        "title": "Looking for camp this year",
                        "selftext": "Can contribute build and strike.",
                        "author": "match_author",
                        "permalink": "/r/BurningMan/comments/matched_candidate/post/",
                        "created_utc": 220,
                    }
                },
                {
                    "data": {
                        "id": "skipped_candidate",
                        "title": "Weather report",
                        "selftext": "No ask/offer in this post.",
                        "author": "skip_author",
                        "permalink": "/r/BurningMan/comments/skipped_candidate/post/",
                        "created_utc": 215,
                    }
                },
            ],
        }
    }
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)

    called = {"get_extractor": False}

    def fail_if_called():
        called["get_extractor"] = True
        raise AssertionError("_get_extractor should not be called in dry-run")

    monkeypatch.setattr(reddit_json, "_get_extractor", fail_if_called)

    counts = await reddit_json.backfill_reddit_json(
        datetime.fromtimestamp(200, UTC).replace(tzinfo=None),
        fetch_limit=100,
        sleep_seconds=0,
        max_pages=5,
        dry_run=True,
        client=client,
    )

    assert counts["pages"] == 1
    assert counts["matched"] == 1
    assert counts["skipped"] == 1
    assert counts["extracted"] == 0
    assert counts["raw_after_error"] == 0
    assert called["get_extractor"] is False

    async with get_session() as session:
        rows = (await session.exec(select(Post))).all()

    assert rows == []
    engine_module._engine = None


@pytest.mark.asyncio
async def test_poll_reddit_json_once_parallelizes_bounded_extraction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    db_path = tmp_path / "reddit_json_listener_parallel.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("REDDIT_JSON_FETCH_LIMIT", "100")
    monkeypatch.setenv("REDDIT_JSON_MAX_CONCURRENT_EXTRACTIONS", "2")
    get_settings.cache_clear()
    engine_module._engine = None

    await create_db_and_tables()

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "post_a",
                        "title": "Looking for camp A",
                        "selftext": "Happy to help with build.",
                        "author": "author_a",
                        "author_fullname": "t2_author_a",
                        "permalink": "/r/BurningMan/comments/post_a/post/",
                        "created_utc": 1735819200,
                    }
                },
                {
                    "data": {
                        "id": "post_b",
                        "title": "Looking for camp B",
                        "selftext": "Happy to help with kitchen.",
                        "author": "author_b",
                        "author_fullname": "t2_author_b",
                        "permalink": "/r/BurningMan/comments/post_b/post/",
                        "created_utc": 1735819100,
                    }
                },
            ]
        }
    }
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)

    state = {"in_flight": 0, "max_in_flight": 0}

    async def fake_process_post(session, post, extractor, on_extraction_error="error"):
        state["in_flight"] += 1
        state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        await asyncio.sleep(0.05)
        post.status = PostStatus.INDEXED
        session.add(post)
        await session.commit()
        await session.refresh(post)
        state["in_flight"] -= 1
        return post

    class StubExtractor:
        def __init__(self) -> None:
            self.aclose = AsyncMock(return_value=None)

    monkeypatch.setattr(reddit_json, "_get_extractor", StubExtractor)
    monkeypatch.setattr(reddit_json, "process_post", fake_process_post)

    counts = await reddit_json.poll_reddit_json_once(client=client)

    assert counts["matched"] == 2
    assert counts["extracted"] == 2
    assert state["max_in_flight"] == 2
    engine_module._engine = None
