from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from matchbot.db import engine as engine_module
from matchbot.db.engine import create_db_and_tables, get_session
from matchbot.db.models import Match, MatchStatus, Platform, Post, PostRole, PostStatus, Profile
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
        assert "Rising Sparks Public Dashboard" in response.text
        assert "Live Activity" in response.text
        assert "Most Requested Skills" in response.text
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

        assert payload["key_metrics"]["active_camps"] == 0
        assert payload["key_metrics"]["active_seekers"] == 0
        assert payload["key_metrics"]["intro_to_conversation_rate"] == 0
        assert payload["key_metrics"]["conversation_to_onboarding_rate"] == 0
        assert payload["live_feed"] == []
        assert payload["demand"]["top_contribution_types"] == []
        assert payload["demand"]["top_vibes"] == []
    finally:
        _reset_engine()


def test_community_data_redacts_story_and_feed_identifiers(monkeypatch, tmp_path) -> None:
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
                role=PostRole.SEEKER,
                status=PostStatus.INDEXED,
                detected_at=now - timedelta(hours=2),
                contribution_types="build|art",
                vibes="inclusive|build_focused",
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
                role=PostRole.CAMP,
                status=PostStatus.INDEXED,
                detected_at=now - timedelta(hours=1),
                contribution_types="build|kitchen",
                vibes="inclusive",
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
                role=PostRole.SEEKER,
                status=PostStatus.NEEDS_REVIEW,
                detected_at=now - timedelta(hours=3),
                contribution_types="art",
                vibes="cozy",
            )
            raw_post = Post(
                platform=Platform.FACEBOOK,
                platform_post_id="raw_1",
                platform_author_id="fb_user",
                author_display_name="RawUser",
                source_url="",
                source_community="facebook",
                title="Raw post",
                raw_text="Should not show in feed",
                role=PostRole.SEEKER,
                status=PostStatus.RAW,
                detected_at=now - timedelta(minutes=20),
            )
            camp_profile = Profile(
                role=PostRole.CAMP,
                platform=Platform.REDDIT,
                platform_author_id="camp_profile_1",
                is_active=True,
            )
            seeker_profile = Profile(
                role=PostRole.SEEKER,
                platform=Platform.DISCORD,
                platform_author_id="seeker_profile_1",
                is_active=True,
            )
            inactive_profile = Profile(
                role=PostRole.CAMP,
                platform=Platform.REDDIT,
                platform_author_id="camp_profile_2",
                is_active=False,
            )

            session.add(seeker)
            session.add(camp)
            session.add(needs_review)
            session.add(raw_post)
            session.add(camp_profile)
            session.add(seeker_profile)
            session.add(inactive_profile)
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

        assert payload["summary"]["total_ingested"] == 4
        assert payload["summary"]["indexed"] == 2
        assert payload["summary"]["proposed_matches"] == 1
        assert payload["summary"]["intros_sent"] == 1
        assert payload["backlog"]["needs_review_count"] == 1

        key_metrics = payload["key_metrics"]
        assert key_metrics["active_camps"] == 1
        assert key_metrics["active_seekers"] == 1
        assert key_metrics["match_attempts_total"] == 1
        assert key_metrics["intro_sent_total"] == 1
        assert key_metrics["conversation_started_total"] == 0
        assert key_metrics["onboarded_total"] == 0

        demand = payload["demand"]
        assert demand["top_contribution_types"][0]["name"] == "art"
        assert demand["top_contribution_types"][0]["count"] == 2

        feed = payload["live_feed"]
        assert len(feed) >= 3
        assert all(
            feed[i]["occurred_at"] >= feed[i + 1]["occurred_at"]
            for i in range(len(feed) - 1)
        )
        assert all(event["event_type"] != "post_raw" for event in feed)

        feed_blob = " ".join((event["summary"] or "") for event in feed)
        assert "real@example.com" not in feed_blob
        assert "u/SeekerReal" not in feed_blob
        assert "@SeekerReal" not in feed_blob
        assert "https://example.com/help" not in feed_blob

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
