import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import select

from matchbot.db.models import Platform, Post, PostStatus
from matchbot.importers.facebook_har import (
    _find_post_nodes,
    backfill_facebook_posts,
    parse_extension_json,
    parse_facebook_post_fields,
    parse_har_file,
)


def test_find_post_nodes_graphql_relay_style():
    obj = {
        "data": {
            "node": {
                "group_feed": {
                    "edges": [
                        {
                            "node": {
                                "id": "post:123",
                                "message": {"text": "Hello world"},
                                "creation_time": 1700000000,
                                "actors": [{"id": "user1", "name": "User One"}],
                            }
                        }
                    ]
                }
            }
        }
    }
    nodes = _find_post_nodes(obj)
    assert len(nodes) == 1
    assert nodes[0]["id"] == "post:123"


def test_find_post_nodes_flat():
    obj = {
        "post_id": "456",
        "message": "Flat style message",
        "created_time": 1700000001,
        "from": {"id": "user2", "name": "User Two"},
    }
    nodes = _find_post_nodes(obj)
    assert len(nodes) == 1
    assert nodes[0]["post_id"] == "456"


def test_find_post_nodes_depth_limit():
    # Create a deeply nested object
    obj = {"a": {}}
    curr = obj["a"]
    for _ in range(25):
        curr["b"] = {}
        curr = curr["b"]
    
    # Place a post at the bottom
    curr["id"] = "deep"
    curr["creation_time"] = 123
    curr["message"] = "too deep"
    
    nodes = _find_post_nodes(obj)
    assert len(nodes) == 0  # Should be skipped due to depth limit


def test_parse_facebook_post_fields_graphql():
    node = {
        "id": "post:123",
        "message": {"text": "Hello world"},
        "creation_time": 1700000000,
        "actors": [{"id": "user1", "name": "User One"}],
        "url": "https://fb.com/123",
    }
    fields = parse_facebook_post_fields(node)
    assert fields["platform_post_id"] == "123"
    assert fields["platform_author_id"] == "user1"
    assert fields["author_display_name"] == "User One"
    assert fields["raw_text"] == "Hello world"
    assert fields["source_url"] == "https://fb.com/123"
    assert fields["source_created_at"] == datetime.fromtimestamp(1700000000, tz=UTC).replace(tzinfo=None)


def test_parse_facebook_post_fields_webhook():
    node = {
        "post_id": "456",
        "message": "Flat style",
        "created_time": 1700000001,
        "from": {"id": "user2", "name": "User Two"},
        "permalink_url": "https://fb.com/456",
    }
    fields = parse_facebook_post_fields(node)
    assert fields["platform_post_id"] == "456"
    assert fields["platform_author_id"] == "user2"
    assert fields["author_display_name"] == "User Two"
    assert fields["raw_text"] == "Flat style"
    assert fields["source_url"] == "https://fb.com/456"


def test_parse_facebook_post_fields_body_text():
    node = {
        "id": "789",
        "body": {"text": "Body text style"},
        "creation_time": 1700000002,
    }
    fields = parse_facebook_post_fields(node)
    assert fields["raw_text"] == "Body text style"


def test_parse_har_file(tmp_path):
    har_content = {
        "log": {
            "entries": [
                {
                    "request": {"url": "https://www.facebook.com/api/graphql/"},
                    "response": {
                        "content": {
                            "text": json.dumps({
                                "id": "h1",
                                "message": "har post",
                                "creation_time": 1700000010,
                            })
                        }
                    }
                }
            ]
        }
    }
    har_file = tmp_path / "test.har"
    har_file.write_text(json.dumps(har_content))
    
    posts = parse_har_file(har_file)
    assert len(posts) == 1
    assert posts[0]["platform_post_id"] == "h1"


def test_parse_extension_json(tmp_path):
    ext_content = [
        json.dumps({
            "id": "e1",
            "message": "ext post",
            "creation_time": 1700000020,
        })
    ]
    ext_file = tmp_path / "test.json"
    ext_file.write_text(json.dumps(ext_content))
    
    posts = parse_extension_json(ext_file)
    assert len(posts) == 1
    assert posts[0]["platform_post_id"] == "e1"


@pytest.mark.asyncio
async def test_backfill_facebook_posts_dedup(db_session, monkeypatch, tmp_path):
    # Ensure the internal get_session() uses the same database as our test
    db_path = tmp_path / "test_facebook_dedup.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    from matchbot.db import engine as engine_module
    engine_module._engine = None  # Force re-creation of engine with new settings

    # We need to create tables in this new DB
    from matchbot.db.engine import create_db_and_tables, get_session as get_internal_session
    await create_db_and_tables()

    # Insert an existing post using the internal session so it's in the same DB
    async with get_internal_session() as session:
        existing_post = Post(
            platform=Platform.FACEBOOK,
            platform_post_id="dup1",
            platform_author_id="u1",
            author_display_name="User",
            source_url="",
            source_community="Test",
            source_created_at=datetime.now(),
            title="Title",
            raw_text="Existing",
            status=PostStatus.INDEXED,
        )
        session.add(existing_post)
        await session.commit()

    fields_list = [
        {
            "platform_post_id": "dup1",
            "platform_author_id": "u1",
            "author_display_name": "User",
            "source_url": "",
            "raw_text": "Duplicate content",
            "source_created_at": datetime.now(),
        },
        {
            "platform_post_id": "new1",
            "platform_author_id": "u2",
            "author_display_name": "User 2",
            "source_url": "",
            "raw_text": "New content",
            "source_created_at": datetime.now(),
        }
    ]

    counts = await backfill_facebook_posts(
        fields_list,
        group_name="Test Group",
        dry_run=False,
        no_extract=True,
    )

    assert counts["new_candidates"] == 1
    assert counts["deduped"] == 1

    # Verify DB state
    async with get_internal_session() as session:
        posts = (await session.exec(select(Post).where(Post.platform == Platform.FACEBOOK))).all()
    
    assert len(posts) == 2
    post_ids = [p.platform_post_id for p in posts]
    assert "dup1" in post_ids
    assert "new1" in post_ids
    
    engine_module._engine = None


@pytest.mark.asyncio
async def test_backfill_facebook_posts_since_date(db_session, monkeypatch, tmp_path):
    db_path = tmp_path / "test_facebook_since.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    from matchbot.db import engine as engine_module
    engine_module._engine = None
    from matchbot.db.engine import create_db_and_tables
    await create_db_and_tables()

    since = datetime(2024, 1, 1)
    fields_list = [
        {
            "platform_post_id": "old",
            "platform_author_id": "u1",
            "author_display_name": "User",
            "source_url": "",
            "raw_text": "Old",
            "source_created_at": datetime(2023, 12, 31),
        },
        {
            "platform_post_id": "recent",
            "platform_author_id": "u2",
            "author_display_name": "User 2",
            "source_url": "",
            "raw_text": "Recent",
            "source_created_at": datetime(2024, 1, 2),
        }
    ]

    counts = await backfill_facebook_posts(
        fields_list,
        group_name="Test Group",
        since_datetime=since,
        no_extract=True,
    )

    assert counts["new_candidates"] == 1
    assert counts["before_cutoff"] == 1
    
    from matchbot.db.engine import get_session as get_internal_session
    async with get_internal_session() as session:
        posts = (await session.exec(select(Post).where(Post.platform == Platform.FACEBOOK))).all()
    assert len(posts) == 1
    assert posts[0].platform_post_id == "recent"
    
    engine_module._engine = None
