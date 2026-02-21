"""Tests for LLM extraction layer."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matchbot.db.models import Platform, Post, PostRole, PostStatus
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

    def test_unknown_vibes_dropped(self):
        ep = ExtractedPost(vibes=["art", "invalid_vibe_xyz"])
        assert "art" in ep.vibes
        assert "invalid_vibe_xyz" not in ep.vibes

    def test_unknown_contribution_types_dropped(self):
        ep = ExtractedPost(contribution_types=["build", "interpretive_dance"])
        assert "build" in ep.contribution_types
        assert "interpretive_dance" not in ep.contribution_types

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
        contribution_types=["build", "kitchen"],
        year=2025,
        confidence=0.9,
    )

    result = await process_post(db_session, post, mock_extractor)

    assert result.status == PostStatus.INDEXED
    assert result.role == PostRole.SEEKER
    assert result.year == 2025
    mock_extractor.extract.assert_called_once()


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
    mock_response.content = [MagicMock(text=json.dumps({
        "role": "seeker",
        "camp_name": None,
        "camp_size_min": None,
        "camp_size_max": None,
        "year": 2025,
        "vibes": ["art", "build_focused"],
        "contribution_types": ["build"],
        "location_preference": None,
        "availability_notes": "Available build week",
        "contact_method": "DM on Reddit",
        "confidence": 0.85,
        "extraction_notes": None,
    }))]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    extractor = AnthropicExtractor(client=mock_client)
    result = await extractor.extract("Seeking camp", "Looking for camp", "reddit", "BurningMan")

    assert result.role == "seeker"
    assert result.year == 2025
    assert "art" in result.vibes
    assert result.confidence == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_openai_extractor_parses_response():
    from matchbot.extraction.openai_extractor import OpenAIExtractor

    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "role": "camp",
        "camp_name": "Solar Circus",
        "camp_size_min": 20,
        "camp_size_max": 30,
        "year": 2025,
        "vibes": ["art", "party"],
        "contribution_types": ["build", "kitchen"],
        "location_preference": None,
        "availability_notes": "Need builders for early arrival",
        "contact_method": "Post in comments",
        "confidence": 0.9,
        "extraction_notes": None,
    })
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    extractor = OpenAIExtractor(client=mock_client)
    result = await extractor.extract("Camp has openings", "We are recruiting", "reddit", "BurningMan")

    assert result.role == "camp"
    assert result.camp_name == "Solar Circus"
    assert result.camp_size_min == 20


@pytest.mark.asyncio
async def test_anthropic_extractor_raises_on_bad_json():
    from matchbot.extraction.anthropic_extractor import AnthropicExtractor
    from matchbot.extraction.base import ExtractionError

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="not valid json {{{")]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    extractor = AnthropicExtractor(client=mock_client)
    with pytest.raises(ExtractionError):
        await extractor.extract("title", "body", "reddit", "community")
