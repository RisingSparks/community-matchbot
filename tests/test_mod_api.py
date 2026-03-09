"""Tests for the moderator API (/api/mod/)."""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from matchbot.db.models import Event, Platform, Post, PostRole, PostStatus, Profile
from matchbot.server import create_app

# ---------------------------------------------------------------------------
# Fixture: authenticated mod client wired to the in-memory DB
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mod_client(db_session):
    from matchbot.mod.router import _get_session, _require_mod

    app = create_app(enable_scheduler=False)

    async def override_session():
        yield db_session

    app.dependency_overrides[_get_session] = override_session
    app.dependency_overrides[_require_mod] = lambda: None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Auth tests (use their own app instance, not mod_client)
# ---------------------------------------------------------------------------


async def test_login_valid(monkeypatch):
    """Valid password returns 200 and sets a mod_session cookie."""
    monkeypatch.setenv("MOD_PASSWORD", "secret")
    monkeypatch.setenv("MOD_SECRET_KEY", "testkey")
    from matchbot.settings import get_settings

    get_settings.cache_clear()

    app = create_app(enable_scheduler=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/mod/auth/login", json={"password": "secret"})

    get_settings.cache_clear()
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert "mod_session" in resp.cookies


async def test_login_invalid(monkeypatch):
    """Wrong password returns 401."""
    monkeypatch.setenv("MOD_PASSWORD", "secret")
    monkeypatch.setenv("MOD_SECRET_KEY", "testkey")
    from matchbot.settings import get_settings

    get_settings.cache_clear()

    app = create_app(enable_scheduler=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/mod/auth/login", json={"password": "wrong"})

    get_settings.cache_clear()
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Queue tests
# ---------------------------------------------------------------------------


async def test_queue_empty(mod_client):
    resp = await mod_client.get("/api/mod/queue")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_queue_returns_needs_review(mod_client, db_session):
    """NEEDS_REVIEW posts appear; INDEXED posts do not."""
    nr_post = Post(
        platform=Platform.REDDIT,
        platform_post_id="q_nr_1",
        platform_author_id="u1",
        title="NR post",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
    )
    indexed_post = Post(
        platform=Platform.REDDIT,
        platform_post_id="q_idx_1",
        platform_author_id="u2",
        title="Indexed post",
        raw_text="text",
        status=PostStatus.INDEXED,
    )
    db_session.add(nr_post)
    db_session.add(indexed_post)
    await db_session.commit()

    resp = await mod_client.get("/api/mod/queue")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == PostStatus.NEEDS_REVIEW
    assert "age_hours" in data[0]


async def test_queue_filter_by_platform(mod_client, db_session):
    """Platform query param filters correctly."""
    reddit_post = Post(
        platform=Platform.REDDIT,
        platform_post_id="q_reddit_1",
        platform_author_id="u1",
        title="Reddit post",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
    )
    discord_post = Post(
        platform=Platform.DISCORD,
        platform_post_id="q_discord_1",
        platform_author_id="u2",
        title="Discord post",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
    )
    db_session.add(reddit_post)
    db_session.add(discord_post)
    await db_session.commit()

    resp = await mod_client.get("/api/mod/queue", params={"platform": Platform.REDDIT})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["platform"] == Platform.REDDIT


async def test_queue_filter_by_extraction_method(mod_client, db_session):
    soft_post = Post(
        platform=Platform.REDDIT,
        platform_post_id="q_soft_1",
        platform_author_id="u1",
        title="Soft post",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
        extraction_method="keyword_soft",
    )
    llm_post = Post(
        platform=Platform.REDDIT,
        platform_post_id="q_llm_1",
        platform_author_id="u2",
        title="LLM post",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
        extraction_method="llm_openai",
    )
    db_session.add(soft_post)
    db_session.add(llm_post)
    await db_session.commit()

    resp = await mod_client.get(
        "/api/mod/queue",
        params={"extraction_method": "keyword_soft"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["platform_post_id"] == "q_soft_1"
    assert data[0]["extraction_method"] == "keyword_soft"


# ---------------------------------------------------------------------------
# Post detail tests
# ---------------------------------------------------------------------------


async def test_post_detail_404(mod_client):
    resp = await mod_client.get("/api/mod/posts/nonexistent-uuid")
    assert resp.status_code == 404


async def test_post_detail_returns_events(mod_client, db_session):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="detail_1",
        platform_author_id="u1",
        title="Detail test",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    event = Event(
        event_type="test_event",
        post_id=post.id,
        actor="moderator",
        payload="{}",
    )
    db_session.add(event)
    await db_session.commit()

    resp = await mod_client.get(f"/api/mod/posts/{post.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == post.id
    assert data["vibes"] == []
    assert data["vibes_other"] == []
    assert data["contribution_types"] == []
    assert data["contribution_types_other"] == []
    assert data["infra_categories_other"] == []
    assert data["condition_other"] is None
    assert len(data["events"]) == 1
    assert data["events"][0]["event_type"] == "test_event"


# ---------------------------------------------------------------------------
# Approve tests
# ---------------------------------------------------------------------------


async def test_approve_transitions_to_indexed(mod_client, db_session):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="approve_1",
        platform_author_id="u1",
        title="Approve me",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
        role=PostRole.SEEKER,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    resp = await mod_client.post(f"/api/mod/posts/{post.id}/approve", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["new_status"] == "INDEXED"

    await db_session.refresh(post)
    assert post.status == PostStatus.INDEXED
    assert post.profile_id is not None

    profile = await db_session.get(Profile, post.profile_id)
    assert profile is not None
    assert profile.platform_author_id == "u1"
    assert profile.role == PostRole.SEEKER


async def test_approve_409_wrong_status(mod_client, db_session):
    """Approving a post that is already INDEXED returns 409."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="approve_409",
        platform_author_id="u1",
        title="Already indexed",
        raw_text="text",
        status=PostStatus.INDEXED,
        role=PostRole.SEEKER,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    resp = await mod_client.post(f"/api/mod/posts/{post.id}/approve", json={})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Dismiss tests
# ---------------------------------------------------------------------------


async def test_dismiss_requires_reason(mod_client, db_session):
    """Missing or invalid reason returns 422."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="dismiss_req",
        platform_author_id="u1",
        title="Test",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # Missing reason field entirely
    resp = await mod_client.post(f"/api/mod/posts/{post.id}/dismiss", json={})
    assert resp.status_code == 422

    # Invalid reason value
    resp = await mod_client.post(
        f"/api/mod/posts/{post.id}/dismiss", json={"reason": "bad-reason"}
    )
    assert resp.status_code == 422


async def test_dismiss_transitions_to_skipped(mod_client, db_session):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="dismiss_1",
        platform_author_id="u1",
        title="Dismiss me",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    resp = await mod_client.post(
        f"/api/mod/posts/{post.id}/dismiss", json={"reason": "spam"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["new_status"] == "SKIPPED"

    await db_session.refresh(post)
    assert post.status == PostStatus.SKIPPED


# ---------------------------------------------------------------------------
# Edit tests
# ---------------------------------------------------------------------------


async def test_edit_stays_needs_review(mod_client, db_session):
    """Edit leaves post in NEEDS_REVIEW and applies the field change."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="edit_1",
        platform_author_id="u1",
        title="Edit me",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
        role=PostRole.SEEKER,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    resp = await mod_client.post(f"/api/mod/posts/{post.id}/edit", json={"role": "camp"})
    assert resp.status_code == 200

    await db_session.refresh(post)
    assert post.status == PostStatus.NEEDS_REVIEW
    assert post.role == PostRole.CAMP


async def test_edit_requires_at_least_one_field(mod_client, db_session):
    """Sending an all-null body to /edit returns 422."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="edit_empty",
        platform_author_id="u1",
        title="Edit me",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    resp = await mod_client.post(f"/api/mod/posts/{post.id}/edit", json={})
    assert resp.status_code == 422


async def test_edit_rejects_invalid_condition(mod_client, db_session):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="edit_condition",
        platform_author_id="u1",
        title="Edit me",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    resp = await mod_client.post(
        f"/api/mod/posts/{post.id}/edit",
        json={"condition": "excellent"},
    )
    assert resp.status_code == 422


async def test_edit_normalizes_valid_condition(mod_client, db_session):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="edit_condition_ok",
        platform_author_id="u1",
        title="Edit me",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    resp = await mod_client.post(
        f"/api/mod/posts/{post.id}/edit",
        json={"condition": "GOOD"},
    )
    assert resp.status_code == 200

    await db_session.refresh(post)
    assert post.condition == "good"


async def test_edit_syncs_profile_for_indexed_post(mod_client, db_session):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="edit_profile_sync",
        platform_author_id="u_profile",
        author_display_name="Old Name",
        title="Edit me",
        raw_text="text",
        status=PostStatus.INDEXED,
        role=PostRole.SEEKER,
        profile_id=None,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    resp = await mod_client.post(
        f"/api/mod/posts/{post.id}/edit",
        json={"role": "camp", "camp_name": "Dusty Builders"},
    )
    assert resp.status_code == 200

    await db_session.refresh(post)
    assert post.profile_id is not None

    profile = await db_session.get(Profile, post.profile_id)
    assert profile is not None
    assert profile.role == PostRole.CAMP
    assert profile.camp_name == "Dusty Builders"

    matching_profiles = (
        await db_session.exec(
            select(Profile).where(
                Profile.platform == Platform.REDDIT,
                Profile.platform_author_id == "u_profile",
                Profile.role == PostRole.CAMP,
            )
        )
    ).all()
    assert len(matching_profiles) == 1


# ---------------------------------------------------------------------------
# Taxonomy test
# ---------------------------------------------------------------------------


async def test_taxonomy_keys_present(mod_client):
    resp = await mod_client.get("/api/mod/taxonomy")
    assert resp.status_code == 200
    data = resp.json()
    assert "vibes" in data
    assert "contribution_types" in data
    assert "infra_categories" in data
    assert "conditions" in data
    assert "roles" in data
    assert isinstance(data["vibes"], list)
    assert "seeker" in data["roles"]


# ---------------------------------------------------------------------------
# Stats test
# ---------------------------------------------------------------------------


async def test_stats_counts(mod_client, db_session):
    """Creating one NEEDS_REVIEW post makes needs_review_count == 1."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="stats_1",
        platform_author_id="u1",
        title="Stats post",
        raw_text="text",
        status=PostStatus.NEEDS_REVIEW,
        extraction_method="keyword_soft",
    )
    db_session.add(post)
    await db_session.commit()

    resp = await mod_client.get("/api/mod/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_review_count"] == 1
    assert data["soft_matches_count"] == 1
    assert data["oldest_needs_review_age_hours"] is not None
    assert data["approved_today"] == 0
    assert data["dismissed_today"] == 0
