import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import select

from matchbot.db import engine as engine_module
from matchbot.db.engine import create_db_and_tables
from matchbot.db.engine import get_session as get_internal_session
from matchbot.db.models import Platform, Post, PostStatus
from matchbot.importers import facebook_har as facebook_har_module
from matchbot.importers.facebook_har import (
    _find_post_nodes,
    backfill_facebook_posts,
    parse_extension_json,
    parse_facebook_post_fields,
    parse_har_file,
)
from matchbot.title_utils import build_post_title, build_source_title
from scripts.backfill_facebook import (
    _build_group_batches,
    _clean_group_title,
    _detect_format,
    _infer_group_candidate_from_extension_json,
    _infer_group_metadata,
    _infer_group_name_from_extension_json,
    _infer_group_name_from_filename,
    _stage_input_file,
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


def test_find_post_nodes_rejects_comment_id_shapes():
    obj = {
        "data": {
            "node": {
                "id": "Y29tbWVudDoxMjM=",
                "body": {"text": "comment body"},
                "created_time": 1700000001,
                "group_comment_info": {},
            }
        }
    }
    nodes = _find_post_nodes(obj)
    assert nodes == []


def test_find_post_nodes_rejects_comment_typename():
    obj = {
        "__typename": "Comment",
        "id": "123",
        "body": {"text": "comment body"},
        "created_time": 1700000001,
    }
    nodes = _find_post_nodes(obj)
    assert nodes == []


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
    assert fields["source_created_at"] == datetime.fromtimestamp(
        1700000000, tz=UTC
    ).replace(tzinfo=None)


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


def test_parse_facebook_post_fields_story_shape():
    node = {
        "__typename": "Story",
        "id": "story-node",
        "post_id": "3040003819540317",
        "permalink_url": "https://www.facebook.com/groups/252779754929418/posts/3040003819540317/",
        "actors": [{"id": "633547488", "name": "Andre Mesquita"}],
        "comet_sections": {
            "content": {
                "story": {
                    "comet_sections": {
                        "message": {
                            "story": {
                                "message": {
                                    "text": "Looking for a Home at Burning Man 2026?",
                                }
                            }
                        }
                    }
                }
            },
            "timestamp": {
                "story": {
                    "creation_time": 1773405471,
                    "url": "https://www.facebook.com/groups/252779754929418/posts/3040003819540317/",
                }
            },
        },
    }
    fields = parse_facebook_post_fields(node)
    assert fields["platform_post_id"] == "3040003819540317"
    assert fields["platform_author_id"] == "633547488"
    assert fields["author_display_name"] == "Andre Mesquita"
    assert fields["raw_text"] == "Looking for a Home at Burning Man 2026?"
    assert fields["source_url"] == "https://www.facebook.com/groups/252779754929418/posts/3040003819540317/"


def test_parse_facebook_post_fields_filters_member_welcome_noise():
    node = {
        "id": "post:welcome-1",
        "message": {"text": "Let's welcome our new members!\nChris Henderson"},
        "creation_time": 1700000000,
        "actors": [{"id": "group1", "name": "Camps 4 Campers"}],
    }

    assert parse_facebook_post_fields(node) is None


def test_build_post_title_prefers_first_non_empty_line():
    raw_text = "\n\nHERE is looking for campers\nWe are a small camp with openings"
    assert build_post_title(raw_text) == "HERE is looking for campers"


def test_build_source_title_prefers_explicit_source_title():
    assert build_source_title("Looking for campmates", "Body first line") == "Looking for campmates"


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


def test_parse_extension_json_filters_member_welcome_noise(tmp_path):
    ext_content = [
        json.dumps(
            {
                "id": "e-noise",
                "message": "Let's welcome our new members!\nMaxime Coupey",
                "creation_time": 1700000020,
            }
        ),
        json.dumps(
            {
                "id": "e-real",
                "message": "Who’s looking for a Burning Man Camp?",
                "creation_time": 1700000030,
            }
        ),
    ]
    ext_file = tmp_path / "test.json"
    ext_file.write_text(json.dumps(ext_content))

    posts = parse_extension_json(ext_file)
    assert len(posts) == 1
    assert posts[0]["platform_post_id"] == "e-real"


def test_parse_extension_json_with_record_objects(tmp_path):
    ext_content = [
        {
            "seq": 1,
            "capturedAt": "2026-03-22T12:00:00.000Z",
            "text": json.dumps({
                "id": "e2",
                "message": "record post",
                "creation_time": 1700000030,
            }),
        }
    ]
    ext_file = tmp_path / "test_records.json"
    ext_file.write_text(json.dumps(ext_content))

    posts = parse_extension_json(ext_file)
    assert len(posts) == 1
    assert posts[0]["platform_post_id"] == "e2"


def test_detect_format_sniffs_har_without_loading_full_json(tmp_path):
    har_file = tmp_path / "sample.har"
    har_file.write_text('{"log":{"entries":[]},"payload":"' + ("x" * 1000) + '"}')

    assert _detect_format(har_file) == "har"


def test_detect_format_sniffs_extension_json_without_loading_full_json(tmp_path):
    ext_file = tmp_path / "sample.json"
    ext_file.write_text('["payload",' + (" " * 1000) + '"more"]')

    assert _detect_format(ext_file) == "extension"


def test_infer_group_name_from_extension_filename():
    path = Path("data/raw/facebook/burning-man-theme-camps_fb_posts_2026-03-22T12-00-00.json")
    assert _infer_group_name_from_filename(path) == "Burning Man Theme Camps"


def test_infer_group_name_from_extension_filename_with_dots():
    path = Path(
        "data/raw/facebook/burning.man.theme.camp.organizers_fb_posts_2026-03-22T12-00-00.json"
    )
    assert _infer_group_name_from_filename(path) == "Burning Man Theme Camp Organizers"


def test_infer_group_name_from_extension_json(tmp_path):
    ext_content = [
        {
            "seq": 1,
            "capturedAt": "2026-03-22T12:00:00.000Z",
            "pageTitle": "(20+) Burning Man Theme Camps | Facebook",
            "text": "{}",
        }
    ]
    ext_file = tmp_path / "sample.json"
    ext_file.write_text(json.dumps(ext_content))

    assert _infer_group_name_from_extension_json(ext_file) == "Burning Man Theme Camps"


def test_clean_group_title_strips_facebook_suffix_and_member_count():
    assert _clean_group_title("(20+) Burning Man: Campers 4 Camps | Facebook") == (
        "Burning Man: Campers 4 Camps"
    )


def test_infer_group_name_from_extension_json_payload_group_node(tmp_path):
    ext_content = [
        {
            "seq": 1,
            "capturedAt": "2026-03-22T12:00:00.000Z",
            "text": json.dumps(
                {
                    "data": {
                        "node": {
                            "to": {
                                "__typename": "Group",
                                "__isEntity": "Group",
                                "id": "252779754929418",
                                "url": "https://www.facebook.com/groups/252779754929418/",
                                "name": "Camps 4 Campers",
                            }
                        }
                    }
                }
            ),
        }
    ]
    ext_file = tmp_path / "sample.json"
    ext_file.write_text(json.dumps(ext_content))

    assert (
        _infer_group_name_from_extension_json(ext_file, group_id="252779754929418")
        == "Camps 4 Campers"
    )


def test_infer_group_candidate_from_extension_json_matches_preferred_name(tmp_path):
    ext_content = [
        {
            "seq": 1,
            "capturedAt": "2026-03-22T12:00:00.000Z",
            "text": json.dumps(
                {
                    "data": {
                        "node": {
                            "to": {
                                "__typename": "Group",
                                "__isEntity": "Group",
                                "id": "9876543210",
                                "url": "https://www.facebook.com/groups/9876543210/",
                                "name": "Burning Man Theme Camp Organizers",
                            }
                        }
                    }
                }
            ),
        }
    ]
    ext_file = tmp_path / "sample.json"
    ext_file.write_text(json.dumps(ext_content))

    assert _infer_group_candidate_from_extension_json(
        ext_file, preferred_name="Burning Man Theme Camp Organizers"
    ) == ("Burning Man Theme Camp Organizers", "9876543210")


def test_stage_input_file_copies_external_capture(tmp_path):
    source = tmp_path / "downloads" / "officialburners_fb_posts_2026-03-22T14-19-49.782Z.json"
    source.parent.mkdir(parents=True)
    source.write_text("[]")

    staging_dir = tmp_path / "repo" / "data" / "raw" / "facebook"
    staged = _stage_input_file(source, staging_dir=staging_dir)

    assert staged == staging_dir / source.name
    assert staged.read_text() == "[]"


def test_stage_input_file_keeps_repo_local_capture(tmp_path):
    staging_dir = tmp_path / "repo" / "data" / "raw" / "facebook"
    staging_dir.mkdir(parents=True)
    source = staging_dir / "officialburners_fb_posts_2026-03-22T14-19-49.782Z.json"
    source.write_text("[]")

    staged = _stage_input_file(source, staging_dir=staging_dir)

    assert staged == source.resolve()


def test_infer_group_metadata_from_post_urls():
    posts = [
        {
            "platform_post_id": "1",
            "source_url": "https://www.facebook.com/groups/1234567890/posts/1",
        },
        {
            "platform_post_id": "2",
            "source_url": "https://www.facebook.com/groups/1234567890/posts/2",
        },
    ]

    inferred_name, inferred_id = _infer_group_metadata([], {}, posts)

    assert inferred_id == "1234567890"
    assert inferred_name == "Facebook Group 1234567890"


def test_infer_group_metadata_from_har_page_title(tmp_path):
    har_content = {
        "log": {
            "pages": [{"title": "Burning Man Theme Camps | Facebook"}],
            "entries": [],
        }
    }
    har_file = tmp_path / "session.har"
    har_file.write_text(json.dumps(har_content))

    inferred_name, inferred_id = _infer_group_metadata([har_file], {har_file: "har"}, [])

    assert inferred_name == "Burning Man Theme Camps"
    assert inferred_id is None


def test_infer_group_metadata_recovers_numeric_id_from_payload_when_url_uses_slug(tmp_path):
    ext_content = [
        {
            "seq": 1,
            "capturedAt": "2026-03-22T12:00:00.000Z",
            "pageTitle": "Burning Man Theme Camp Organizers | Facebook",
            "text": json.dumps(
                {
                    "data": {
                        "node": {
                            "to": {
                                "__typename": "Group",
                                "__isEntity": "Group",
                                "id": "9876543210",
                                "url": "https://www.facebook.com/groups/9876543210/",
                                "name": "Burning Man Theme Camp Organizers",
                            }
                        }
                    }
                }
            ),
        }
    ]
    ext_file = tmp_path / "sample.json"
    ext_file.write_text(json.dumps(ext_content))

    posts = [
        {
            "platform_post_id": "1",
            "source_url": "https://www.facebook.com/groups/burning-man-theme-camp-organizers/posts/1",
        }
    ]

    inferred_name, inferred_id = _infer_group_metadata([ext_file], {ext_file: "extension"}, posts)

    assert inferred_name == "Burning Man Theme Camp Organizers"
    assert inferred_id == "9876543210"


def test_build_group_batches_splits_multiple_group_files(tmp_path):
    campers = tmp_path / "20-burning-man-campers-4-camps_fb_posts_2026-03-25T19-14-10.289Z.json"
    campers.write_text("[]")
    organizers = (
        tmp_path / "20-burning-man-theme-camp-organizers_fb_posts_2026-03-25T19-11-05.669Z.json"
    )
    organizers.write_text("[]")

    parsed_files = [
        {
            "path": campers,
            "format": "extension",
            "posts": [
                {
                    "platform_post_id": "1",
                    "source_url": "https://www.facebook.com/groups/252779754929418/posts/1/",
                }
            ],
        },
        {
            "path": organizers,
            "format": "extension",
            "posts": [
                {
                    "platform_post_id": "2",
                    "source_url": "https://www.facebook.com/groups/burning-man-theme-camp-organizers/posts/2/",
                }
            ],
        },
    ]

    batches = _build_group_batches(
        parsed_files, group_name_override=None, group_id_override=None
    )

    assert len(batches) == 2
    assert {(batch["group_name"], batch["group_id"]) for batch in batches} == {
        ("20 Burning Man Campers 4 Camps", "252779754929418"),
        ("Burning Man Theme Camp Organizers", None),
    }


def test_build_group_batches_splits_mixed_capture_by_group_token(tmp_path):
    mixed = tmp_path / "fb_posts_2026-03-22T13-22-39.397Z.json"
    mixed.write_text("[]")

    parsed_files = [
        {
            "path": mixed,
            "format": "extension",
            "posts": [
                {
                    "platform_post_id": "1",
                    "source_url": "https://www.facebook.com/groups/1234567890/posts/1/",
                },
                {
                    "platform_post_id": "2",
                    "source_url": "https://www.facebook.com/groups/burning-man-theme-camp-organizers/posts/2/",
                },
            ],
        }
    ]

    batches = _build_group_batches(
        parsed_files, group_name_override=None, group_id_override=None
    )

    assert len(batches) == 2
    assert {(batch["group_name"], batch["group_id"], len(batch["posts"])) for batch in batches} == {
        ("Facebook Group 1234567890", "1234567890", 1),
        ("Burning Man Theme Camp Organizers", None, 1),
    }


@pytest.mark.asyncio
async def test_backfill_facebook_posts_dedup(db_session, monkeypatch, tmp_path):
    # Ensure the internal get_session() uses the same database as our test
    db_path = tmp_path / "test_facebook_dedup.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    engine_module._engine = None  # Force re-creation of engine with new settings

    # We need to create tables in this new DB
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
    assert next(p for p in posts if p.platform_post_id == "new1").title == "New content"
    
    engine_module._engine = None


@pytest.mark.asyncio
async def test_backfill_facebook_posts_since_date(db_session, monkeypatch, tmp_path):
    db_path = tmp_path / "test_facebook_since.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    engine_module._engine = None
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


@pytest.mark.asyncio
async def test_backfill_facebook_posts_keeps_raw_on_extraction_error(monkeypatch, tmp_path):
    db_path = tmp_path / "test_facebook_raw_retry.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))

    engine_module._engine = None
    await create_db_and_tables()

    class FakeExtractor:
        async def aclose(self):
            return None

    async def fake_process_post(session, post, extractor, on_extraction_error="error"):
        assert on_extraction_error == "raw"
        post.status = PostStatus.RAW
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post

    monkeypatch.setattr(facebook_har_module, "process_post", fake_process_post)
    monkeypatch.setattr(facebook_har_module, "_get_extractor", lambda: FakeExtractor())

    fields_list = [
        {
            "platform_post_id": "raw1",
            "platform_author_id": "u1",
            "author_display_name": "User",
            "source_url": "",
            "raw_text": "Looking for camp",
            "source_created_at": datetime.now(),
        }
    ]

    counts = await backfill_facebook_posts(
        fields_list,
        group_name="Test Group",
        no_extract=False,
        sleep_seconds=0,
    )

    assert counts["raw_after_error"] == 1
    assert counts["matched"] == 0
    assert counts["extracted"] == 0

    async with get_internal_session() as session:
        post = (
            await session.exec(
                select(Post).where(
                    Post.platform == Platform.FACEBOOK,
                    Post.platform_post_id == "raw1",
                )
            )
        ).one()

    assert post.status == PostStatus.RAW

    engine_module._engine = None


@pytest.mark.asyncio
async def test_backfill_facebook_posts_retries_existing_raw_post(monkeypatch, tmp_path):
    db_path = tmp_path / "test_facebook_retry_existing_raw.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))

    engine_module._engine = None
    await create_db_and_tables()

    async with get_internal_session() as session:
        existing_post = Post(
            platform=Platform.FACEBOOK,
            platform_post_id="raw-existing-1",
            platform_author_id="u1",
            author_display_name="User",
            source_url="",
            source_community="Facebook Group: Test Group",
            source_created_at=datetime.now(),
            title="Need camp",
            raw_text="Looking for camp",
            status=PostStatus.RAW,
        )
        session.add(existing_post)
        await session.commit()

    class FakeExtractor:
        async def aclose(self):
            return None

    retried_post_ids: list[str] = []

    async def fake_process_post(session, post, extractor, on_extraction_error="error"):
        assert on_extraction_error == "raw"
        retried_post_ids.append(post.platform_post_id)
        post.status = PostStatus.INDEXED
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post

    monkeypatch.setattr(facebook_har_module, "process_post", fake_process_post)
    monkeypatch.setattr(facebook_har_module, "_get_extractor", lambda: FakeExtractor())

    fields_list = [
        {
            "platform_post_id": "raw-existing-1",
            "platform_author_id": "u1",
            "author_display_name": "User",
            "source_url": "",
            "raw_text": "Looking for camp",
            "source_created_at": datetime.now(),
        }
    ]

    counts = await backfill_facebook_posts(
        fields_list,
        group_name="Test Group",
        no_extract=False,
        sleep_seconds=0,
    )

    assert retried_post_ids == ["raw-existing-1"]
    assert counts["deduped"] == 0
    assert counts["new_candidates"] == 0
    assert counts["matched"] == 1
    assert counts["extracted"] == 1

    async with get_internal_session() as session:
        posts = (
            await session.exec(
                select(Post).where(
                    Post.platform == Platform.FACEBOOK,
                    Post.platform_post_id == "raw-existing-1",
                )
            )
        ).all()

    assert len(posts) == 1
    assert posts[0].status == PostStatus.INDEXED

    engine_module._engine = None


@pytest.mark.asyncio
async def test_backfill_facebook_posts_retries_transient_db_disconnect(monkeypatch, tmp_path):
    db_path = tmp_path / "test_facebook_retry_disconnect.db"
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))

    engine_module._engine = None
    await create_db_and_tables()

    class FakeExtractor:
        async def aclose(self):
            return None

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

    async def fake_dispose_engine():
        nonlocal dispose_calls
        dispose_calls += 1

    monkeypatch.setattr(facebook_har_module, "process_post", fake_process_post)
    monkeypatch.setattr(facebook_har_module, "_get_extractor", lambda: FakeExtractor())
    monkeypatch.setattr(
        facebook_har_module,
        "is_disconnect_error",
        lambda exc: isinstance(exc, FakeDisconnectError),
    )
    monkeypatch.setattr(facebook_har_module, "dispose_engine", fake_dispose_engine)

    fields_list = [
        {
            "platform_post_id": "disconnect-1",
            "platform_author_id": "u1",
            "author_display_name": "User",
            "source_url": "",
            "raw_text": "Looking for camp",
            "source_created_at": datetime.now(),
        }
    ]

    counts = await backfill_facebook_posts(
        fields_list,
        group_name="Test Group",
        no_extract=False,
        sleep_seconds=0,
    )

    assert process_attempts == 2
    assert dispose_calls == 1
    assert counts["matched"] == 1
    assert counts["raw_after_error"] == 0

    async with get_internal_session() as session:
        posts = (
            await session.exec(
                select(Post).where(
                    Post.platform == Platform.FACEBOOK,
                    Post.platform_post_id == "disconnect-1",
                )
            )
        ).all()

    assert len(posts) == 1
    assert posts[0].status == PostStatus.INDEXED

    engine_module._engine = None
