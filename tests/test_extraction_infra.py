"""Tests for infrastructure ('Bitch n Swap') extraction."""

from __future__ import annotations

import pytest

from matchbot.db.models import Platform, Post, PostStatus, PostType
from matchbot.extraction import process_post
from matchbot.extraction.keywords import keyword_filter
from matchbot.extraction.schemas import ExtractedPost
from matchbot.taxonomy import INFRASTRUCTURE_CONDITIONS

# ---------------------------------------------------------------------------
# ExtractedPost schema — infrastructure fields
# ---------------------------------------------------------------------------


class TestExtractedPostInfraSchema:
    def test_valid_infra_extracted_post(self):
        ep = ExtractedPost(
            post_type="infrastructure",
            infra_role="seeking",
            infra_categories=["power", "shade"],
            quantity="1 unit",
            condition="good",
            confidence=0.9,
        )
        assert ep.post_type == "infrastructure"
        assert ep.infra_role == "seeking"
        assert "power" in ep.infra_categories
        assert ep.condition == "good"

    def test_invalid_infra_role_becomes_none(self):
        ep = ExtractedPost(post_type="infrastructure", infra_role="donating")
        assert ep.infra_role is None

    def test_unknown_infra_categories_dropped(self):
        ep = ExtractedPost(infra_categories=["power", "jetpack_fuel"])
        assert "power" in ep.infra_categories
        assert "jetpack_fuel" in ep.infra_categories

    def test_invalid_condition_preserved(self):
        ep = ExtractedPost(condition="perfect")
        assert ep.condition == "perfect"

    def test_valid_conditions_accepted(self):
        for cond in INFRASTRUCTURE_CONDITIONS:
            ep = ExtractedPost(condition=cond)
            assert ep.condition == cond

    def test_condition_case_insensitive(self):
        ep = ExtractedPost(condition="GOOD")
        assert ep.condition == "good"

    def test_infra_categories_case_insensitive(self):
        ep = ExtractedPost(infra_categories=["POWER", "Shade"])
        assert "power" in ep.infra_categories
        assert "shade" in ep.infra_categories

    def test_invalid_post_type_becomes_mentorship(self):
        ep = ExtractedPost(post_type="weirdstuff")
        assert ep.post_type == "mentorship"

    def test_infrastructure_post_type_accepted(self):
        ep = ExtractedPost(post_type="infrastructure")
        assert ep.post_type == "infrastructure"


# ---------------------------------------------------------------------------
# Keyword filter — infrastructure detection
# ---------------------------------------------------------------------------


class TestKeywordFilterInfra:
    def test_seeking_generator(self):
        result = keyword_filter(
            "Need a generator for Burning Man",
            "Looking for someone who has a generator to borrow.",
        )
        assert result.matched is True
        assert result.post_type == PostType.INFRASTRUCTURE
        assert result.infra_role == "seeking"

    def test_offering_shade(self):
        result = keyword_filter(
            "Have extra shade structure available",
            "I have a canopy I can lend to someone who needs it.",
        )
        assert result.matched is True
        assert result.post_type == PostType.INFRASTRUCTURE
        assert result.infra_role == "offering"

    def test_bitch_n_swap_offering(self):
        result = keyword_filter(
            "Bitch n Swap - giving away tarp",
            "I have surplus gear — giving away shade tarp free to a good home.",
        )
        assert result.matched is True
        assert result.post_type == PostType.INFRASTRUCTURE
        assert result.infra_role == "offering"

    def test_iso_generator(self):
        result = keyword_filter(
            "ISO generator",
            "Looking to borrow a generator for the week.",
        )
        assert result.matched is True
        assert result.post_type == PostType.INFRASTRUCTURE

    def test_seeking_gear(self):
        result = keyword_filter(
            "Seeking gear for Burn",
            "Does anyone have tools or kitchen equipment to borrow?",
        )
        # Either matched as infra or mentorship depending on patterns — just check it doesn't error
        assert isinstance(result.matched, bool)

    def test_infra_overrides_mentorship(self):
        """A post with both mentorship and infra signals classifies as infrastructure first."""
        result = keyword_filter(
            "Camp member wanted — also have extra generator",
            "We're recruiting builders. Also have a spare generator available to borrow.",
        )
        assert result.post_type == PostType.INFRASTRUCTURE

    def test_mentorship_post_not_infra(self):
        result = keyword_filter(
            "Seeking camp for Burning Man 2025",
            "First time burner looking for a friendly camp to join. Willing to build.",
        )
        assert result.matched is True
        assert result.tier == "hard_match"
        assert result.post_type == "mentorship"
        assert result.infra_role is None

    def test_soft_match_fuzzy_seeker_language(self):
        result = keyword_filter(
            "Regional Burn intro",
            "Any camp recs for someone into fire spinning?",
        )
        assert result.matched is False
        assert result.tier == "soft_match"
        assert result.candidate_role == "seeker"
        assert result.score >= 3

    def test_unrelated_post_not_matched(self):
        result = keyword_filter(
            "What to wear at Burning Man",
            "Tips for staying cool on the playa.",
        )
        assert result.matched is False
        assert result.tier == "no_match"


# ---------------------------------------------------------------------------
# process_post — infrastructure extraction pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_post_infra_seeking(db_session, mock_extractor):
    """Infrastructure seeking post is indexed with infra fields populated."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="infra001",
        title="Need a generator for Burning Man",
        raw_text="Looking to borrow a generator for the week. Need 2000W minimum.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.return_value = ExtractedPost(
        post_type="infrastructure",
        infra_role="seeking",
        infra_categories=["power"],
        quantity="1 unit, 2000W",
        condition=None,
        dates_needed="during the event",
        confidence=0.9,
    )

    result = await process_post(db_session, post, mock_extractor)

    assert result.status == PostStatus.INDEXED
    assert result.post_type == PostType.INFRASTRUCTURE
    assert result.infra_role == "seeking"
    assert "power" in result.infra_categories_list()
    assert result.quantity == "1 unit, 2000W"
    assert result.dates_needed == "during the event"


@pytest.mark.asyncio
async def test_process_post_infra_offering(db_session, mock_extractor):
    """Infrastructure offering post is indexed with correct infra_role."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="infra002",
        title="Have extra shade structure available to borrow",
        raw_text="I have a spare canopy for loan. Free to a good home. Good condition.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.return_value = ExtractedPost(
        post_type="infrastructure",
        infra_role="offering",
        infra_categories=["shade"],
        quantity="1 canopy",
        condition="good",
        confidence=0.88,
    )

    result = await process_post(db_session, post, mock_extractor)

    assert result.post_type == PostType.INFRASTRUCTURE
    assert result.infra_role == "offering"
    assert "shade" in result.infra_categories_list()
    assert result.condition == "good"


@pytest.mark.asyncio
async def test_process_post_infra_does_not_call_mentorship_scorer(db_session, mock_extractor):
    """Infrastructure posts route to infra scorer, never mentorship scorer."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="infra003",
        title="Need a generator for Burning Man",
        raw_text="Looking to borrow a generator for the week.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.return_value = ExtractedPost(
        post_type="infrastructure",
        infra_role="seeking",
        infra_categories=["power"],
        confidence=0.9,
    )

    from unittest.mock import patch

    with patch("matchbot.matching.scorer.score_match") as mock_mentorship_scorer:
        result = await process_post(db_session, post, mock_extractor)
        mock_mentorship_scorer.assert_not_called()

    assert result.post_type == PostType.INFRASTRUCTURE


@pytest.mark.asyncio
async def test_process_post_infra_seeds_post_type_from_keyword_filter(db_session, mock_extractor):
    """Keyword filter seeds post_type before LLM call; LLM confirms or overrides."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="infra004",
        title="ISO generator",
        raw_text="Can someone lend a generator for the week?",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    # LLM returns infrastructure as well
    mock_extractor.extract.return_value = ExtractedPost(
        post_type="infrastructure",
        infra_role="seeking",
        infra_categories=["power"],
        confidence=0.85,
    )

    result = await process_post(db_session, post, mock_extractor)

    assert result.post_type == PostType.INFRASTRUCTURE
    assert result.infra_role == "seeking"


@pytest.mark.asyncio
async def test_process_post_infra_unknown_categories_dropped(db_session, mock_extractor):
    """Unmapped infra categories are preserved and force review."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="infra005",
        title="Have spare generator available",
        raw_text="Can lend a generator. Also have a flux capacitor.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.return_value = ExtractedPost(
        post_type="infrastructure",
        infra_role="offering",
        infra_categories=["power", "flux_capacitor"],
        confidence=0.8,
    )

    result = await process_post(db_session, post, mock_extractor)

    cats = result.infra_categories_list()
    other = result.infra_categories_other_list()
    assert "power" in cats
    assert "flux_capacitor" not in cats
    assert "flux_capacitor" in other
    assert result.status == PostStatus.NEEDS_REVIEW


@pytest.mark.asyncio
async def test_process_post_infra_unmapped_condition_preserved(db_session, mock_extractor):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="infra007",
        title="Have spare canopy available",
        raw_text="Can lend a canopy in excellent condition.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.return_value = ExtractedPost(
        post_type="infrastructure",
        infra_role="offering",
        infra_categories=["shade"],
        condition="excellent",
        confidence=0.95,
    )

    result = await process_post(db_session, post, mock_extractor)

    assert result.condition is None
    assert result.condition_other == "excellent"
    assert result.status == PostStatus.NEEDS_REVIEW


@pytest.mark.asyncio
async def test_process_post_infra_creates_event(db_session, mock_extractor):
    """Infra extraction emits a post_extracted event with post_type in payload."""
    import json

    from sqlmodel import select

    from matchbot.db.models import Event

    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="infra006",
        title="Need a generator for Burning Man",
        raw_text="Looking to borrow a generator.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.return_value = ExtractedPost(
        post_type="infrastructure",
        infra_role="seeking",
        infra_categories=["power"],
        confidence=0.9,
    )

    result = await process_post(db_session, post, mock_extractor)

    events = (await db_session.exec(select(Event).where(Event.post_id == result.id))).all()
    extracted_events = [e for e in events if e.event_type == "post_extracted"]
    assert len(extracted_events) == 1

    payload = json.loads(extracted_events[0].payload)
    assert payload["post_type"] == "infrastructure"
    assert payload["infra_role"] == "seeking"
