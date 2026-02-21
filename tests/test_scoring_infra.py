"""Tests for infrastructure match scoring and match proposal."""

from __future__ import annotations

import pytest

from matchbot.db.models import InfraRole, Platform, Post, PostStatus, PostType
from matchbot.matching.infra_scorer import score_infra_match

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infra_post(
    infra_role: str,
    categories: list[str],
    quantity: str | None = None,
    condition: str | None = None,
    dates_needed: str | None = None,
    platform_post_id: str | None = None,
) -> Post:
    return Post(
        platform=Platform.REDDIT,
        platform_post_id=platform_post_id or f"infra_{id(object())}",
        title="Infra post",
        raw_text="Some text",
        status=PostStatus.INDEXED,
        post_type=PostType.INFRASTRUCTURE,
        infra_role=infra_role,
        infra_categories="|".join(categories),
        quantity=quantity,
        condition=condition,
        dates_needed=dates_needed,
    )


# ---------------------------------------------------------------------------
# score_infra_match unit tests
# ---------------------------------------------------------------------------


class TestScoreInfraMatch:
    def test_perfect_category_match(self):
        seeking = _infra_post(InfraRole.SEEKING, ["power", "shade"])
        offering = _infra_post(InfraRole.OFFERING, ["power", "shade"])
        score, breakdown = score_infra_match(seeking, offering)
        assert score > 0.0
        assert breakdown["category_overlap"] == 1.0

    def test_partial_category_match(self):
        seeking = _infra_post(InfraRole.SEEKING, ["power", "shade", "tools"])
        offering = _infra_post(InfraRole.OFFERING, ["power"])
        score, breakdown = score_infra_match(seeking, offering)
        assert 0 < breakdown["category_overlap"] < 1.0

    def test_no_category_overlap_returns_zero(self):
        seeking = _infra_post(InfraRole.SEEKING, ["power"])
        offering = _infra_post(InfraRole.OFFERING, ["shade"])
        score, breakdown = score_infra_match(seeking, offering)
        assert score == 0.0

    def test_incompatible_roles_returns_zero(self):
        both_seeking = _infra_post(InfraRole.SEEKING, ["power"])
        also_seeking = _infra_post(InfraRole.SEEKING, ["power"])
        score, breakdown = score_infra_match(both_seeking, also_seeking)
        assert score == 0.0
        assert breakdown == {}

    def test_both_offering_returns_zero(self):
        a = _infra_post(InfraRole.OFFERING, ["shade"])
        b = _infra_post(InfraRole.OFFERING, ["shade"])
        score, breakdown = score_infra_match(a, b)
        assert score == 0.0

    def test_order_independent(self):
        seeking = _infra_post(InfraRole.SEEKING, ["power"])
        offering = _infra_post(InfraRole.OFFERING, ["power"])
        score_ab, _ = score_infra_match(seeking, offering)
        score_ba, _ = score_infra_match(offering, seeking)
        assert score_ab == pytest.approx(score_ba)

    def test_score_includes_recency_component(self):
        seeking = _infra_post(InfraRole.SEEKING, ["power"])
        offering = _infra_post(InfraRole.OFFERING, ["power"])
        score, breakdown = score_infra_match(seeking, offering)
        assert "recency" in breakdown
        assert breakdown["recency"] > 0  # recent posts score positively

    def test_score_bounded_zero_to_one(self):
        seeking = _infra_post(InfraRole.SEEKING, ["power", "shade", "tools"])
        offering = _infra_post(InfraRole.OFFERING, ["power", "shade", "tools"])
        score, _ = score_infra_match(seeking, offering)
        assert 0.0 <= score <= 1.0

    def test_empty_categories_returns_zero(self):
        seeking = _infra_post(InfraRole.SEEKING, [])
        offering = _infra_post(InfraRole.OFFERING, [])
        score, _ = score_infra_match(seeking, offering)
        assert score == 0.0


# ---------------------------------------------------------------------------
# propose_matches — infra dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_matches_creates_infra_match(db_session):
    """Two infra posts with opposite roles and overlapping categories produce a match."""
    from matchbot.matching.queue import propose_matches

    seeking = _infra_post(InfraRole.SEEKING, ["power"])
    seeking.platform_post_id = "seek001"
    offering = _infra_post(InfraRole.OFFERING, ["power"])
    offering.platform_post_id = "offer001"

    db_session.add(seeking)
    db_session.add(offering)
    await db_session.commit()
    await db_session.refresh(seeking)
    await db_session.refresh(offering)

    matches = await propose_matches(db_session, seeking)

    assert len(matches) == 1
    assert matches[0].match_method == "deterministic_infra"
    assert matches[0].score > 0.0


@pytest.mark.asyncio
async def test_propose_matches_infra_no_category_overlap(db_session):
    """Infra posts with no shared categories produce no match."""
    from matchbot.matching.queue import propose_matches

    seeking = _infra_post(InfraRole.SEEKING, ["power"])
    seeking.platform_post_id = "seek002"
    offering = _infra_post(InfraRole.OFFERING, ["shade"])
    offering.platform_post_id = "offer002"

    db_session.add(seeking)
    db_session.add(offering)
    await db_session.commit()
    await db_session.refresh(seeking)
    await db_session.refresh(offering)

    matches = await propose_matches(db_session, seeking)
    assert matches == []


@pytest.mark.asyncio
async def test_propose_matches_infra_deduplication(db_session):
    """Calling propose_matches twice does not create duplicate Match records."""
    from matchbot.matching.queue import propose_matches

    seeking = _infra_post(InfraRole.SEEKING, ["power"])
    seeking.platform_post_id = "seek003"
    offering = _infra_post(InfraRole.OFFERING, ["power"])
    offering.platform_post_id = "offer003"

    db_session.add(seeking)
    db_session.add(offering)
    await db_session.commit()
    await db_session.refresh(seeking)
    await db_session.refresh(offering)

    await propose_matches(db_session, seeking)
    second_run = await propose_matches(db_session, seeking)
    assert second_run == []


@pytest.mark.asyncio
async def test_propose_matches_infra_does_not_cross_mentorship(db_session):
    """Infra posts are never matched against mentorship posts."""
    from matchbot.db.models import PostRole
    from matchbot.matching.queue import propose_matches

    seeking_infra = _infra_post(InfraRole.SEEKING, ["power"])
    seeking_infra.platform_post_id = "seek004"

    # A mentorship camp post — should not be proposed as an infra match
    camp = Post(
        platform=Platform.REDDIT,
        platform_post_id="camp001",
        title="Camp has openings",
        raw_text="Join our art camp!",
        status=PostStatus.INDEXED,
        post_type=PostType.MENTORSHIP,
        role=PostRole.CAMP,
        infra_categories="power",  # same category text but it's a mentorship post
    )

    db_session.add(seeking_infra)
    db_session.add(camp)
    await db_session.commit()
    await db_session.refresh(seeking_infra)
    await db_session.refresh(camp)

    matches = await propose_matches(db_session, seeking_infra)
    assert matches == []


@pytest.mark.asyncio
async def test_propose_matches_mentorship_does_not_cross_infra(db_session):
    """Mentorship posts are never matched against infra posts."""
    from matchbot.db.models import PostRole
    from matchbot.matching.queue import propose_matches

    seeker = Post(
        platform=Platform.REDDIT,
        platform_post_id="seek005",
        title="Seeking camp",
        raw_text="Looking for a camp to join.",
        status=PostStatus.INDEXED,
        post_type=PostType.MENTORSHIP,
        role=PostRole.SEEKER,
        vibes="art",
        contribution_types="build",
    )
    infra_offering = _infra_post(InfraRole.OFFERING, ["power"])
    infra_offering.platform_post_id = "offer005"

    db_session.add(seeker)
    db_session.add(infra_offering)
    await db_session.commit()
    await db_session.refresh(seeker)
    await db_session.refresh(infra_offering)

    matches = await propose_matches(db_session, seeker)
    assert matches == []
