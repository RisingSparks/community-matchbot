"""Shared test fixtures."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import matchbot.listeners.discord_bot as _discord_bot_module
import matchbot.listeners.facebook as _facebook_module
import matchbot.listeners.reddit as _reddit_module
import matchbot.listeners.reddit_json as _reddit_json_module
from matchbot.db.models import Platform, Post, PostRole, PostStatus, PostType
from matchbot.extraction.schemas import ExtractedPost
from matchbot.public.router import clear_community_cache
from matchbot.settings import get_settings

# ---------------------------------------------------------------------------
# Settings isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolate_raw_store(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Redirect all raw store writes to a temp directory so tests never pollute data/raw/."""
    from matchbot.storage.raw_store import RawStore

    store = RawStore(base_dir=tmp_path / "raw")
    for module in (_reddit_module, _reddit_json_module, _discord_bot_module, _facebook_module):
        monkeypatch.setattr(module, "_raw_store", store)


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch: pytest.MonkeyPatch):
    """Clear the settings cache before and after every test so each test gets a
    fresh Settings() instance. Prevents a stale singleton from leaking
    environment or monkeypatched values across tests."""
    monkeypatch.setenv("VERBOSE", "false")
    get_settings.cache_clear()
    clear_community_cache()
    yield
    get_settings.cache_clear()
    clear_community_cache()


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """In-memory async SQLite session, isolated per test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Mock LLM extractor
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_extractor():
    """Mock extractor returning a default ExtractedPost. provider_name is sync; extract is async."""
    extractor = MagicMock()
    extractor.provider_name.return_value = "anthropic"
    extractor.extract = AsyncMock(
        return_value=ExtractedPost(
            role="seeker",
            camp_name=None,
            camp_size_min=None,
            camp_size_max=None,
            year=2025,
            vibes=["art", "build_focused"],
            contribution_types=["build", "art"],
            location_preference=None,
            availability_notes="Available for build week",
            contact_method="DM me on Reddit",
            confidence=0.85,
            extraction_notes=None,
        )
    )
    extractor.aclose = AsyncMock(return_value=None)
    return extractor


# ---------------------------------------------------------------------------
# Post factories
# ---------------------------------------------------------------------------


def _make_post(
    platform: str = Platform.REDDIT,
    role: str = PostRole.SEEKER,
    vibes: list[str] | None = None,
    contribution_types: list[str] | None = None,
    year: int | None = 2025,
    status: str = PostStatus.INDEXED,
    title: str = "Seeking camp for Burning Man",
    raw_text: str = "I am looking for a camp. Willing to build.",
    source_community: str = "BurningMan",
    seeker_intent: str | None = None,
    post_type: str | None = PostType.MENTORSHIP,
) -> Post:
    v = vibes or ["art", "build_focused"]
    ct = contribution_types or ["build", "art"]
    return Post(
        platform=platform,
        platform_post_id=f"test_{id(object())}",
        platform_author_id="user_123",
        author_display_name="TestUser",
        source_url="https://reddit.com/r/BurningMan/test",
        source_community=source_community,
        title=title,
        raw_text=raw_text,
        status=status,
        role=role,
        vibes="|".join(v),
        contribution_types="|".join(ct),
        year=year,
        seeker_intent=seeker_intent,
        post_type=post_type,
    )


@pytest.fixture
def seeker_post_factory():
    """Factory for seeker Post objects."""

    def factory(**kwargs):
        kwargs.setdefault("role", PostRole.SEEKER)
        return _make_post(**kwargs)

    return factory


@pytest.fixture
def camp_post_factory():
    """Factory for camp Post objects."""

    def factory(**kwargs):
        kwargs.setdefault("role", PostRole.CAMP)
        kwargs.setdefault("vibes", ["art", "build_focused"])
        kwargs.setdefault("contribution_types", ["build", "kitchen_food"])
        kwargs.setdefault("title", "Our camp has openings!")
        kwargs.setdefault("raw_text", "We are recruiting members. Join our art camp!")
        return _make_post(**kwargs)

    return factory
