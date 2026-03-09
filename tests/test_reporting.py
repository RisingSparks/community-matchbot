"""Tests for pilot reporting metrics."""

from __future__ import annotations

import json

import pytest

from matchbot.db.models import Match, MatchStatus, Platform, Post, PostRole, PostStatus
from matchbot.reporting.metrics import compute_metrics, export_matches_csv, export_metrics_json


async def _seed_scenario(session):
    """Create a known scenario: 2 seekers, 1 camp, matches in various states."""
    seeker1 = Post(
        platform=Platform.REDDIT, platform_post_id="s1", role=PostRole.SEEKER,
        status=PostStatus.INDEXED, vibes="art", contribution_types="build",
    )
    seeker2 = Post(
        platform=Platform.DISCORD, platform_post_id="s2", role=PostRole.SEEKER,
        status=PostStatus.INDEXED, vibes="music", contribution_types="sound_lighting",
    )
    camp1 = Post(
        platform=Platform.REDDIT, platform_post_id="c1", role=PostRole.CAMP,
        status=PostStatus.INDEXED, vibes="art", contribution_types="build|kitchen_food",
    )
    session.add_all([seeker1, seeker2, camp1])
    await session.commit()
    await session.refresh(seeker1)
    await session.refresh(seeker2)
    await session.refresh(camp1)

    match1 = Match(
        seeker_post_id=seeker1.id, camp_post_id=camp1.id,
        status=MatchStatus.ONBOARDED, score=0.85,
    )
    match2 = Match(
        seeker_post_id=seeker2.id, camp_post_id=camp1.id,
        status=MatchStatus.INTRO_SENT, score=0.60,
        mismatch_reason=None,
    )
    match3 = Match(
        seeker_post_id=seeker1.id, camp_post_id=camp1.id,
        status=MatchStatus.DECLINED, score=0.45,
        mismatch_reason="Different years",
    )
    # Deduplicate — use distinct seeker IDs for these
    match3.seeker_post_id = seeker2.id  # just for variety
    session.add_all([match1, match2, match3])
    await session.commit()


@pytest.mark.asyncio
async def test_compute_metrics_zero_state(db_session):
    metrics = await compute_metrics(db_session)
    assert metrics["active_camp_profiles"] == 0
    assert metrics["active_seeker_profiles"] == 0
    assert metrics["total_posts_indexed"] == 0
    assert metrics["match_attempts_total"] == 0
    assert metrics["intro_to_conversation_rate"] == 0.0


@pytest.mark.asyncio
async def test_compute_metrics_with_data(db_session):
    await _seed_scenario(db_session)
    metrics = await compute_metrics(db_session)

    assert metrics["total_posts_indexed"] == 3
    assert metrics["match_attempts_total"] == 3
    assert metrics["onboarded_total"] == 1
    # intro_sent_total includes INTRO_SENT + CONVERSATION_STARTED + ACCEPTED_PENDING + ONBOARDED
    assert metrics["intro_sent_total"] >= 2


@pytest.mark.asyncio
async def test_compute_metrics_mismatch_reasons(db_session):
    await _seed_scenario(db_session)
    metrics = await compute_metrics(db_session)
    assert "Different years" in metrics["top_mismatch_reasons"]


@pytest.mark.asyncio
async def test_compute_metrics_by_platform(db_session):
    await _seed_scenario(db_session)
    metrics = await compute_metrics(db_session)
    assert Platform.REDDIT in metrics["by_platform"]
    assert Platform.DISCORD in metrics["by_platform"]


@pytest.mark.asyncio
async def test_export_metrics_json(db_session, tmp_path):
    await _seed_scenario(db_session)
    out = tmp_path / "metrics.json"
    await export_metrics_json(db_session, out)
    assert out.exists()
    data = json.loads(out.read_text())
    assert "computed_at" in data
    assert data["total_posts_indexed"] == 3


@pytest.mark.asyncio
async def test_export_matches_csv(db_session, tmp_path):
    await _seed_scenario(db_session)
    out = tmp_path / "matches.csv"
    await export_matches_csv(db_session, out)
    assert out.exists()
    content = out.read_text()
    assert "id" in content
    assert "status" in content
    assert "score" in content
