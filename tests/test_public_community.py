from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from matchbot.db import engine as engine_module
from matchbot.db.engine import create_db_and_tables, get_session
from matchbot.db.models import Match, MatchStatus, Platform, Post, PostStatus
from matchbot.server import create_app
from matchbot.settings import get_settings


def _setup_sqlite_db(monkeypatch, tmp_path, name: str) -> None:
    db_path = tmp_path / name
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DB_PATH", str(db_path))
    get_settings.cache_clear()
    engine_module._engine = None
    asyncio.run(create_db_and_tables())


def _reset_engine() -> None:
    engine_module._engine = None
    get_settings.cache_clear()


def test_community_page_renders(monkeypatch, tmp_path) -> None:
    _setup_sqlite_db(monkeypatch, tmp_path, "community_render.db")
    try:
        client = TestClient(create_app(enable_scheduler=False))
        response = client.get("/community/")
        assert response.status_code == 200
        assert "Show more good-fit connections." in response.text
        assert "How would you improve this?" in response.text
    finally:
        _reset_engine()


def test_community_data_zero_state(monkeypatch, tmp_path) -> None:
    _setup_sqlite_db(monkeypatch, tmp_path, "community_zero_state.db")
    try:
        client = TestClient(create_app(enable_scheduler=False))
        response = client.get("/community/data")
        assert response.status_code == 200
        payload = response.json()

        assert payload["summary"]["total_ingested"] == 0
        assert payload["summary"]["indexed"] == 0
        assert payload["summary"]["proposed_matches"] == 0
        assert payload["summary"]["intros_sent"] == 0
        assert payload["backlog"]["needs_review_count"] == 0
        assert payload["backlog"]["oldest_needs_review_age_hours"] is None
        assert payload["stories"] == []
    finally:
        _reset_engine()


def test_community_data_redacts_story_identifiers(monkeypatch, tmp_path) -> None:
    _setup_sqlite_db(monkeypatch, tmp_path, "community_redaction.db")

    async def _seed() -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        async with get_session() as session:
            seeker = Post(
                platform=Platform.REDDIT,
                platform_post_id="seek_1",
                platform_author_id="t2_real_user",
                author_display_name="SeekerReal",
                source_url="https://reddit.com/r/BurningMan/comments/seek_1/",
                source_community="BurningMan",
                title="Need a camp",
                raw_text=(
                    "I am @SeekerReal and u/SeekerReal. Email me at real@example.com "
                    "or visit https://example.com/help"
                ),
                status=PostStatus.INDEXED,
                detected_at=now - timedelta(hours=2),
                contribution_types="build|art",
            )
            camp = Post(
                platform=Platform.REDDIT,
                platform_post_id="camp_1",
                platform_author_id="t2_camp_user",
                author_display_name="CampReal",
                source_url="https://reddit.com/r/BurningMan/comments/camp_1/",
                source_community="BurningMan",
                title="Camp offering spots",
                raw_text="We need builders and artists.",
                status=PostStatus.INDEXED,
                detected_at=now - timedelta(hours=1),
                contribution_types="build|kitchen",
            )
            needs_review = Post(
                platform=Platform.DISCORD,
                platform_post_id="review_1",
                platform_author_id="discord_user",
                author_display_name="DiscordUser",
                source_url="",
                source_community="discord",
                title="Pending review",
                raw_text="Needs moderation",
                status=PostStatus.NEEDS_REVIEW,
                detected_at=now - timedelta(hours=3),
            )
            session.add(seeker)
            session.add(camp)
            session.add(needs_review)
            await session.commit()
            await session.refresh(seeker)
            await session.refresh(camp)

            match = Match(
                seeker_post_id=seeker.id,
                camp_post_id=camp.id,
                status=MatchStatus.INTRO_SENT,
                score=0.84,
                confidence=0.78,
                created_at=now - timedelta(hours=1),
                intro_sent_at=now - timedelta(minutes=30),
            )
            session.add(match)
            await session.commit()

    try:
        asyncio.run(_seed())
        client = TestClient(create_app(enable_scheduler=False))
        response = client.get("/community/data")
        assert response.status_code == 200
        payload = response.json()

        assert payload["summary"]["total_ingested"] == 3
        assert payload["summary"]["indexed"] == 2
        assert payload["summary"]["proposed_matches"] == 1
        assert payload["summary"]["intros_sent"] == 1
        assert payload["backlog"]["needs_review_count"] == 1
        assert payload["stories"]

        story_blob = " ".join(
            [
                payload["stories"][0]["problem"],
                payload["stories"][0]["intervention"],
                payload["stories"][0]["outcome"],
                payload["stories"][0]["confidence_note"],
            ]
        )
        assert "real@example.com" not in story_blob
        assert "u/SeekerReal" not in story_blob
        assert "@SeekerReal" not in story_blob
        assert "https://example.com/help" not in story_blob
        assert "[contact]" in story_blob or "[link]" in story_blob
    finally:
        _reset_engine()

