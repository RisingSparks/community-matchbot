from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from matchbot.db import engine as engine_module
from matchbot.db.engine import create_db_and_tables, get_session
from matchbot.db.models import (
    Match,
    MatchStatus,
    Platform,
    Post,
    PostRole,
    PostStatus,
    PostType,
    Profile,
)
from matchbot.public import router as public_router
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
        assert "Rising Sparks" in response.text
        assert "Live Activity" in response.text
        assert "Most Requested Skills" in response.text
        assert "Most Sought Skills" in response.text
        assert "Most Sought Vibes" in response.text
        assert "Matched Drill-Down" in response.text
    finally:
        _reset_engine()


def test_root_page_renders_dashboard(monkeypatch, tmp_path) -> None:
    _setup_sqlite_db(monkeypatch, tmp_path, "community_root_render.db")
    try:
        client = TestClient(create_app(enable_scheduler=False))
        response = client.get("/")
        assert response.status_code == 200
        assert "Rising Sparks" in response.text
        assert "Live Activity" in response.text
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
        assert payload["demand"]["most_sought_skills"] == []
        assert payload["demand"]["most_sought_vibes"] == []
    finally:
        _reset_engine()


def test_community_rest_api_endpoints_exist_and_are_nonbreaking(monkeypatch, tmp_path) -> None:
    _setup_sqlite_db(monkeypatch, tmp_path, "community_api_endpoints.db")
    try:
        client = TestClient(create_app(enable_scheduler=False))

        legacy = client.get("/community/data")
        assert legacy.status_code == 200
        legacy_payload = legacy.json()

        overview = client.get("/community/api/overview")
        metrics = client.get("/community/api/metrics")
        pipeline = client.get("/community/api/pipeline")
        platforms = client.get("/community/api/platforms")
        feed = client.get("/community/api/feed")
        demand = client.get("/community/api/demand")
        matches = client.get("/community/api/matches")
        stories = client.get("/community/api/stories")

        assert overview.status_code == 200
        assert metrics.status_code == 200
        assert pipeline.status_code == 200
        assert platforms.status_code == 200
        assert feed.status_code == 200
        assert demand.status_code == 200
        assert matches.status_code == 200
        assert stories.status_code == 200

        assert overview.json()["summary"] == legacy_payload["summary"]
        assert metrics.json()["key_metrics"] == legacy_payload["key_metrics"]
        assert pipeline.json()["pipeline"] == legacy_payload["pipeline"]
        assert platforms.json()["platform_breakdown"] == legacy_payload["platform_breakdown"]
        assert feed.json()["live_feed"] == legacy_payload["live_feed"]
        assert demand.json()["demand"] == legacy_payload["demand"]
        assert stories.json()["stories"] == legacy_payload["stories"]
    finally:
        _reset_engine()


def test_community_matches_api_filters_and_sanitizes(monkeypatch, tmp_path) -> None:
    _setup_sqlite_db(monkeypatch, tmp_path, "community_matches_api.db")

    now = datetime.now(UTC).replace(tzinfo=None)
    old_match_time = now - timedelta(days=45)
    recent_match_time = now - timedelta(days=2)

    async def _seed() -> None:
        async with get_session() as session:
            seeker_recent = Post(
                platform=Platform.REDDIT,
                platform_post_id="seek_recent",
                platform_author_id="s_recent",
                source_url="https://reddit.com/seek_recent",
                title="Need builders",
                raw_text="Email me at recent@example.com u/RecentUser",
                role=PostRole.SEEKER,
                status=PostStatus.INDEXED,
                contribution_types="build|art",
                detected_at=now - timedelta(days=3),
            )
            camp_recent = Post(
                platform=Platform.DISCORD,
                platform_post_id="camp_recent",
                platform_author_id="c_recent",
                source_url="https://discord.com/channels/x/y",
                title="Camp needs build",
                raw_text="@CampRecent needs build team",
                role=PostRole.CAMP,
                status=PostStatus.INDEXED,
                contribution_types="build|kitchen",
                detected_at=now - timedelta(days=3),
            )
            seeker_old = Post(
                platform=Platform.FACEBOOK,
                platform_post_id="seek_old",
                platform_author_id="s_old",
                source_url="https://facebook.com/groups/z/posts/1",
                title="Old seeker",
                raw_text="Old text",
                role=PostRole.SEEKER,
                status=PostStatus.INDEXED,
                contribution_types="art",
                detected_at=now - timedelta(days=50),
            )
            camp_old = Post(
                platform=Platform.REDDIT,
                platform_post_id="camp_old",
                platform_author_id="c_old",
                source_url="https://reddit.com/camp_old",
                title="Old camp",
                raw_text="Old camp text",
                role=PostRole.CAMP,
                status=PostStatus.INDEXED,
                contribution_types="sound",
                detected_at=now - timedelta(days=50),
            )

            session.add(seeker_recent)
            session.add(camp_recent)
            session.add(seeker_old)
            session.add(camp_old)
            await session.commit()
            await session.refresh(seeker_recent)
            await session.refresh(camp_recent)
            await session.refresh(seeker_old)
            await session.refresh(camp_old)

            session.add(
                Match(
                    seeker_post_id=seeker_recent.id,
                    camp_post_id=camp_recent.id,
                    status=MatchStatus.APPROVED,
                    score=0.91,
                    confidence=0.82,
                    created_at=recent_match_time,
                )
            )
            session.add(
                Match(
                    seeker_post_id=seeker_old.id,
                    camp_post_id=camp_old.id,
                    status=MatchStatus.DECLINED,
                    score=0.33,
                    confidence=0.2,
                    created_at=old_match_time,
                )
            )
            await session.commit()

    try:
        asyncio.run(_seed())
        client = TestClient(create_app(enable_scheduler=False))

        filtered = client.get("/community/api/matches?status=approved&days=30&limit=50")
        assert filtered.status_code == 200
        filtered_payload = filtered.json()
        assert filtered_payload["summary"]["total"] == 1
        assert filtered_payload["summary"]["by_status"]["approved"] == 1
        assert len(filtered_payload["matched"]) == 1
        row = filtered_payload["matched"][0]
        assert row["status"] == MatchStatus.APPROVED
        assert row["shared_signals"] == "build"
        assert row["match_reason"] == "Both mention build as contribution styles."
        assert row["seeker_source_url"] == "https://reddit.com/seek_recent"
        assert row["camp_source_url"] == "https://discord.com/channels/x/y"
        assert "recent@example.com" not in row["seeker_summary"]
        assert "u/RecentUser" not in row["seeker_summary"]

        wide = client.get("/community/api/matches?days=all&limit=2")
        assert wide.status_code == 200
        wide_payload = wide.json()
        assert wide_payload["summary"]["total"] == 2
        assert len(wide_payload["matched"]) == 2
        older = wide_payload["matched"][1]
        assert older["shared_signals"] == "none"
        assert older["match_reason"].startswith("No shared contribution tags were extracted.")
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
        assert demand["most_sought_skills"][0]["name"] == "kitchen"
        assert demand["most_sought_skills"][0]["demand_count"] == 1
        assert demand["most_sought_skills"][0]["supply_count"] == 0
        assert demand["most_sought_vibes"][0]["name"] == "inclusive"
        assert demand["most_sought_vibes"][0]["demand_count"] == 1
        assert demand["most_sought_vibes"][0]["supply_count"] == 1

        feed = payload["live_feed"]
        assert len(feed) >= 2
        assert all(
            feed[i]["occurred_at"] >= feed[i + 1]["occurred_at"]
            for i in range(len(feed) - 1)
        )
        assert all(event["event_type"] != "post_raw" for event in feed)
        assert all(event["event_type"] != "post_indexed" for event in feed)
        assert any(event["event_type"] == "post_needs_review" for event in feed)

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


def test_live_feed_excludes_post_indexed_events(monkeypatch, tmp_path) -> None:
    _setup_sqlite_db(monkeypatch, tmp_path, "community_no_post_indexed_feed_events.db")

    now = datetime.now(UTC).replace(tzinfo=None)

    async def _seed() -> None:
        async with get_session() as session:
            seeker = Post(
                platform=Platform.REDDIT,
                platform_post_id="seek_no_feed",
                platform_author_id="t2_seek_no_feed",
                title="Need build help",
                raw_text="Looking for help",
                role=PostRole.SEEKER,
                status=PostStatus.INDEXED,
                source_created_at=now - timedelta(days=2),
                detected_at=now - timedelta(days=1),
            )
            camp = Post(
                platform=Platform.DISCORD,
                platform_post_id="camp_no_feed",
                platform_author_id="discord_camp_no_feed",
                title="Camp seeking builders",
                raw_text="We have open spots",
                role=PostRole.CAMP,
                status=PostStatus.NEEDS_REVIEW,
                detected_at=now - timedelta(hours=12),
            )
            session.add(seeker)
            session.add(camp)
            await session.commit()
            await session.refresh(seeker)
            await session.refresh(camp)

            session.add(
                Match(
                    seeker_post_id=seeker.id,
                    camp_post_id=camp.id,
                    status=MatchStatus.APPROVED,
                    score=0.76,
                    confidence=0.65,
                    created_at=now - timedelta(hours=2),
                )
            )
            await session.commit()

    try:
        asyncio.run(_seed())
        client = TestClient(create_app(enable_scheduler=False))
        response = client.get("/community/data")
        assert response.status_code == 200
        payload = response.json()

        feed = payload["live_feed"]
        assert len(feed) == 2
        assert any(item["event_type"] == "post_needs_review" for item in feed)
        assert any(item["event_type"] == "match_approved" for item in feed)
        assert all(item["event_type"] != "post_indexed" for item in feed)
    finally:
        _reset_engine()


def test_community_order_book_for_skills_and_vibes(monkeypatch, tmp_path) -> None:
    _setup_sqlite_db(monkeypatch, tmp_path, "community_order_book.db")

    now = datetime.now(UTC).replace(tzinfo=None)

    async def _seed() -> None:
        async with get_session() as session:
            session.add_all(
                [
                    Post(
                        platform=Platform.REDDIT,
                        platform_post_id="camp_1",
                        platform_author_id="camp_1",
                        title="Camp needs kitchen and build",
                        raw_text="Seeking kitchen and build folks",
                        role=PostRole.CAMP,
                        post_type=PostType.MENTORSHIP,
                        status=PostStatus.INDEXED,
                        contribution_types="kitchen|build",
                        vibes="inclusive|art",
                        detected_at=now - timedelta(days=1),
                    ),
                    Post(
                        platform=Platform.DISCORD,
                        platform_post_id="camp_2",
                        platform_author_id="camp_2",
                        title="Camp needs kitchen and art",
                        raw_text="Seeking kitchen and art folks",
                        role=PostRole.CAMP,
                        post_type=PostType.MENTORSHIP,
                        status=PostStatus.INDEXED,
                        contribution_types="kitchen|art",
                        vibes="inclusive|music",
                        detected_at=now - timedelta(days=1),
                    ),
                    Post(
                        platform=Platform.REDDIT,
                        platform_post_id="seeker_1",
                        platform_author_id="seeker_1",
                        title="I can build",
                        raw_text="Offering build and art help",
                        role=PostRole.SEEKER,
                        post_type=PostType.MENTORSHIP,
                        status=PostStatus.INDEXED,
                        contribution_types="build|art",
                        vibes="inclusive|music",
                        detected_at=now - timedelta(days=1),
                    ),
                    Post(
                        platform=Platform.FACEBOOK,
                        platform_post_id="seeker_2",
                        platform_author_id="seeker_2",
                        title="I can teach",
                        raw_text="Offering teaching support",
                        role=PostRole.SEEKER,
                        post_type=PostType.MENTORSHIP,
                        status=PostStatus.NEEDS_REVIEW,
                        contribution_types="teaching",
                        vibes="sober",
                        detected_at=now - timedelta(hours=12),
                    ),
                    Post(
                        platform=Platform.REDDIT,
                        platform_post_id="infra_camp",
                        platform_author_id="infra_camp",
                        title="Need generator",
                        raw_text="Seeking power gear",
                        role=PostRole.CAMP,
                        post_type=PostType.INFRASTRUCTURE,
                        status=PostStatus.INDEXED,
                        infra_role="seeking",
                        infra_categories="power",
                        contribution_types="logistics",
                        vibes="party",
                        detected_at=now - timedelta(hours=8),
                    ),
                ]
            )
            await session.commit()

    try:
        asyncio.run(_seed())
        client = TestClient(create_app(enable_scheduler=False))
        response = client.get("/community/data")
        assert response.status_code == 200
        demand = response.json()["demand"]

        skills = demand["most_sought_skills"]
        assert [row["name"] for row in skills[:3]] == ["kitchen", "art", "build"]
        assert skills[0]["demand_count"] == 2
        assert skills[0]["supply_count"] == 0
        assert skills[0]["net_gap"] == 2
        assert skills[0]["fill_ratio"] == 0
        assert skills[1]["demand_count"] == 1
        assert skills[1]["supply_count"] == 1
        assert skills[1]["fill_ratio"] == 1.0

        vibes = demand["most_sought_vibes"]
        assert [row["name"] for row in vibes[:3]] == ["inclusive", "art", "music"]
        assert vibes[0]["demand_count"] == 2
        assert vibes[0]["supply_count"] == 1
        assert vibes[0]["net_gap"] == 1
        assert vibes[0]["fill_ratio"] == 0.5
        assert all(row["name"] != "party" for row in vibes)
    finally:
        _reset_engine()


def test_community_data_retries_on_disconnect(monkeypatch, tmp_path) -> None:
    _setup_sqlite_db(monkeypatch, tmp_path, "community_retry_disconnect.db")
    calls = {"count": 0}

    async def _flaky_payload(_session):
        calls["count"] += 1
        if calls["count"] == 1:
            raise DBAPIError(
                statement="SELECT 1",
                params={},
                orig=Exception(
                    "ConnectionDoesNotExistError: connection was closed in the middle of operation"
                ),
            )
        return {"summary": {}, "weekly": {}, "backlog": {}, "updated_at": "ok"}

    try:
        monkeypatch.setattr(public_router, "build_public_community_payload", _flaky_payload)
        client = TestClient(create_app(enable_scheduler=False))
        response = client.get("/community/data")
        assert response.status_code == 200
        assert response.json()["updated_at"] == "ok"
        assert calls["count"] == 2
    finally:
        _reset_engine()


def test_community_data_does_not_retry_non_disconnect(monkeypatch, tmp_path) -> None:
    _setup_sqlite_db(monkeypatch, tmp_path, "community_no_retry_non_disconnect.db")
    calls = {"count": 0}

    async def _boom(_session):
        calls["count"] += 1
        raise RuntimeError("not a disconnect")

    try:
        monkeypatch.setattr(public_router, "build_public_community_payload", _boom)
        client = TestClient(create_app(enable_scheduler=False), raise_server_exceptions=False)
        response = client.get("/community/data")
        assert response.status_code == 500
        assert calls["count"] == 1
    finally:
        _reset_engine()
