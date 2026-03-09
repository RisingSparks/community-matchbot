"""Tests for LLM extraction layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel import select

from matchbot.db.models import Platform, Post, PostRole, PostStatus, Profile
from matchbot.extraction import process_post
from matchbot.extraction.schemas import ExtractedPost

# ---------------------------------------------------------------------------
# ExtractedPost schema validation
# ---------------------------------------------------------------------------


class TestExtractedPostSchema:
    def test_valid_seeker(self):
        ep = ExtractedPost(
            role="seeker",
            vibes=["art", "build_focused"],
            contribution_types=["build"],
            confidence=0.8,
        )
        assert ep.role == "seeker"
        assert "art" in ep.vibes
        assert ep.confidence == 0.8

    def test_invalid_role_becomes_unknown(self):
        ep = ExtractedPost(role="wizard")
        assert ep.role == "unknown"

    def test_unknown_vibes_preserved_in_schema(self):
        ep = ExtractedPost(vibes=["art", "invalid_vibe_xyz"])
        assert "art" in ep.vibes
        assert "invalid_vibe_xyz" in ep.vibes

    def test_unknown_contribution_types_preserved_in_schema(self):
        ep = ExtractedPost(contribution_types=["build", "interpretive_dance"])
        assert "build" in ep.contribution_types
        assert "interpretive_dance" in ep.contribution_types

    def test_confidence_clamped_high(self):
        ep = ExtractedPost(confidence=1.5)
        assert ep.confidence == 1.0

    def test_confidence_clamped_low(self):
        ep = ExtractedPost(confidence=-0.5)
        assert ep.confidence == 0.0

    def test_all_fields_none_is_valid(self):
        ep = ExtractedPost()
        assert ep.role == "unknown"
        assert ep.vibes == []
        assert ep.contribution_types == []


# ---------------------------------------------------------------------------
# process_post orchestration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_post_keyword_no_match_skips(db_session, mock_extractor):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="abc123",
        title="Great weather tips for the playa",
        raw_text="Stay hydrated and wear a hat!",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    result = await process_post(db_session, post, mock_extractor)

    assert result.status == PostStatus.SKIPPED
    assert result.post_type is None
    mock_extractor.extract.assert_not_called()


@pytest.mark.asyncio
async def test_process_post_soft_match_goes_to_needs_review_without_llm(db_session, mock_extractor):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="soft001",
        title="Regional Burn intro",
        raw_text="Any camp recs for someone into fire spinning?",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    result = await process_post(db_session, post, mock_extractor)

    assert result.status == PostStatus.NEEDS_REVIEW
    assert result.role == PostRole.SEEKER
    assert result.extraction_method == "keyword_soft"
    mock_extractor.extract.assert_not_called()


@pytest.mark.asyncio
async def test_process_post_indexes_on_high_confidence(db_session, mock_extractor):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="xyz789",
        title="Seeking camp for Burning Man 2025",
        raw_text="I am looking for a camp. Willing to build and cook.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.return_value = ExtractedPost(
        role="seeker",
        vibes=["art", "build_focused"],
        contribution_types=["build", "kitchen_food"],
        year=2025,
        confidence=0.9,
    )

    result = await process_post(db_session, post, mock_extractor)

    assert result.status == PostStatus.INDEXED
    assert result.role == PostRole.SEEKER
    assert result.year == 2025
    assert result.profile_id is not None

    profile = await db_session.get(Profile, result.profile_id)
    assert profile is not None
    assert profile.role == PostRole.SEEKER
    assert profile.platform == Platform.REDDIT
    mock_extractor.extract.assert_called_once()


@pytest.mark.asyncio
async def test_process_post_reuses_existing_profile_for_same_author_and_role(
    db_session, mock_extractor
):
    first = Post(
        platform=Platform.REDDIT,
        platform_post_id="profile_1",
        platform_author_id="same_author",
        author_display_name="First Name",
        title="Seeking camp for Burning Man 2025",
        raw_text="I can help with build.",
        status=PostStatus.RAW,
    )
    db_session.add(first)
    await db_session.commit()
    await db_session.refresh(first)

    mock_extractor.extract.return_value = ExtractedPost(
        role="seeker",
        contribution_types=["build"],
        confidence=0.9,
    )
    first = await process_post(db_session, first, mock_extractor)

    second = Post(
        platform=Platform.REDDIT,
        platform_post_id="profile_2",
        platform_author_id="same_author",
        author_display_name="Updated Name",
        title="Still seeking camp",
        raw_text="Also happy to help with kitchen.",
        status=PostStatus.RAW,
    )
    db_session.add(second)
    await db_session.commit()
    await db_session.refresh(second)

    mock_extractor.extract.return_value = ExtractedPost(
        role="seeker",
        contribution_types=["kitchen_food"],
        confidence=0.95,
    )
    second = await process_post(db_session, second, mock_extractor)

    profiles = (
        await db_session.exec(
            select(Profile).where(
                Profile.platform == Platform.REDDIT,
                Profile.platform_author_id == "same_author",
                Profile.role == PostRole.SEEKER,
            )
        )
    ).all()

    assert len(profiles) == 1
    assert first.profile_id == second.profile_id == profiles[0].id
    assert profiles[0].display_name == "Updated Name"
    assert profiles[0].contribution_types == "kitchen_food"


@pytest.mark.asyncio
async def test_process_post_needs_review_on_low_confidence(db_session, mock_extractor):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="low001",
        title="Looking for a camp",
        raw_text="Seeking a place to stay.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.return_value = ExtractedPost(
        role="seeker",
        confidence=0.4,
    )

    result = await process_post(db_session, post, mock_extractor)

    assert result.status == PostStatus.NEEDS_REVIEW
    assert result.extraction_confidence == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_process_post_error_on_llm_failure(db_session, mock_extractor):
    from matchbot.extraction.base import ExtractionError

    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="err001",
        title="Looking for a camp, willing to build",
        raw_text="Some text about seeking camp.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.side_effect = ExtractionError("API timeout")

    result = await process_post(db_session, post, mock_extractor)

    assert result.status == PostStatus.ERROR


@pytest.mark.asyncio
async def test_process_post_keeps_raw_on_llm_failure_when_configured(db_session, mock_extractor):
    from matchbot.extraction.base import ExtractionError

    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="err002",
        title="Looking for a camp, willing to build",
        raw_text="Some text about seeking camp.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.side_effect = ExtractionError("API timeout")

    result = await process_post(db_session, post, mock_extractor, on_extraction_error="raw")

    assert result.status == PostStatus.RAW


@pytest.mark.asyncio
async def test_process_post_normalizes_vibes(db_session, mock_extractor):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="norm001",
        title="Seeking camp",
        raw_text="Looking for a camp. I'm a first time burner.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.return_value = ExtractedPost(
        role="seeker",
        vibes=["art", "INVALID_VIBE"],
        contribution_types=["build"],
        confidence=0.85,
    )

    result = await process_post(db_session, post, mock_extractor)

    # Only valid vibes should be stored
    assert "art" in result.vibes_list()
    assert "INVALID_VIBE" not in result.vibes_list()


@pytest.mark.asyncio
async def test_process_post_preserves_unmapped_terms_and_routes_to_review(
    db_session, mock_extractor
):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="other001",
        title="Seeking camp for makers",
        raw_text="Looking for a camp with a maker vibe and hands-on fabrication.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.return_value = ExtractedPost(
        role="seeker",
        vibes=["art"],
        vibes_other=["maker"],
        contribution_types=["build"],
        contribution_types_other=["fabrication"],
        confidence=0.92,
    )

    result = await process_post(db_session, post, mock_extractor)

    assert result.status == PostStatus.NEEDS_REVIEW
    assert result.vibes_list() == ["art"]
    assert result.vibes_other_list() == ["maker"]
    assert result.contribution_types_list() == ["build", "fabrication"]
    assert result.contribution_types_other_list() == []


@pytest.mark.asyncio
async def test_process_post_uses_keyword_role_when_llm_returns_unknown(db_session, mock_extractor):
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="role001",
        title="Seeking camp for Burning Man 2025",
        raw_text="First time burner looking for a camp. Happy to build.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.return_value = ExtractedPost(
        role="unknown",
        contribution_types=["build"],
        confidence=0.9,
    )

    result = await process_post(db_session, post, mock_extractor)

    assert result.role == PostRole.SEEKER


@pytest.mark.asyncio
async def test_process_post_creates_event_record(db_session, mock_extractor):
    from sqlmodel import select

    from matchbot.db.models import Event

    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="evt001",
        title="Seeking camp for Burning Man",
        raw_text="Looking for a good camp to join.",
        status=PostStatus.RAW,
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    mock_extractor.extract.return_value = ExtractedPost(
        role="seeker",
        confidence=0.9,
    )

    result = await process_post(db_session, post, mock_extractor)

    events = (await db_session.exec(select(Event).where(Event.post_id == result.id))).all()
    assert len(events) >= 1
    event_types = [e.event_type for e in events]
    assert "post_extracted" in event_types


# ---------------------------------------------------------------------------
# Extractor implementations (mock API calls)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anthropic_extractor_parses_response():
    from matchbot.extraction.anthropic_extractor import AnthropicExtractor

    mock_response = MagicMock()
    mock_response.stop_reason = "end_turn"
    mock_response.content = []
    mock_response.parsed_output = ExtractedPost(
        role="seeker",
        camp_name=None,
        camp_size_min=None,
        camp_size_max=None,
        year=2025,
        vibes=["art", "build_focused"],
        contribution_types=["build"],
        location_preference=None,
        availability_notes="Available build week",
        contact_method="DM on Reddit",
        confidence=0.85,
        extraction_notes=None,
    )

    mock_client = AsyncMock()
    mock_client.messages.parse = AsyncMock(return_value=mock_response)

    extractor = AnthropicExtractor(client=mock_client)
    result = await extractor.extract("Seeking camp", "Looking for camp", "reddit", "BurningMan")

    assert result.role == "seeker"
    assert result.year == 2025
    assert "art" in result.vibes
    assert result.confidence == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_openai_extractor_parses_response():
    from matchbot.extraction.openai_extractor import OpenAIExtractor

    mock_response = MagicMock()
    mock_response.output = []
    mock_response.output_parsed = ExtractedPost(
        role="camp",
        camp_name="Solar Circus",
        camp_size_min=20,
        camp_size_max=30,
        year=2025,
        vibes=["art", "party"],
        contribution_types=["build", "kitchen_food"],
        location_preference=None,
        availability_notes="Need builders for early arrival",
        contact_method="Post in comments",
        confidence=0.9,
        extraction_notes=None,
    )

    mock_client = AsyncMock()
    mock_client.responses.parse = AsyncMock(return_value=mock_response)

    extractor = OpenAIExtractor(client=mock_client)
    result = await extractor.extract(
        "Camp has openings",
        "We are recruiting",
        "reddit",
        "BurningMan",
    )

    assert result.role == "camp"
    assert result.camp_name == "Solar Circus"
    assert result.camp_size_min == 20


@pytest.mark.asyncio
async def test_openai_extractor_raises_on_refusal():
    from matchbot.extraction.base import ExtractionError
    from matchbot.extraction.openai_extractor import OpenAIExtractor

    refusal_item = MagicMock()
    refusal_item.type = "refusal"
    refusal_item.refusal = "I cannot help with that."
    output_message = MagicMock()
    output_message.type = "message"
    output_message.content = [refusal_item]

    mock_response = MagicMock()
    mock_response.output = [output_message]
    mock_response.output_parsed = None

    mock_client = AsyncMock()
    mock_client.responses.parse = AsyncMock(return_value=mock_response)

    extractor = OpenAIExtractor(client=mock_client)
    with pytest.raises(ExtractionError, match="refused extraction"):
        await extractor.extract("title", "body", "reddit", "BurningMan")


@pytest.mark.asyncio
async def test_anthropic_extractor_raises_on_refusal():
    from matchbot.extraction.anthropic_extractor import AnthropicExtractor
    from matchbot.extraction.base import ExtractionError

    refusal_text = MagicMock()
    refusal_text.type = "text"
    refusal_text.text = "I cannot help with that."
    mock_response = MagicMock()
    mock_response.stop_reason = "refusal"
    mock_response.content = [refusal_text]
    mock_response.parsed_output = None

    mock_client = AsyncMock()
    mock_client.messages.parse = AsyncMock(return_value=mock_response)

    extractor = AnthropicExtractor(client=mock_client)
    with pytest.raises(ExtractionError, match="refused extraction"):
        await extractor.extract("title", "body", "reddit", "community")
