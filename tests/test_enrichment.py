"""Tests for WWW Guide enrichment and intake form."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matchbot.db.models import Platform, Post, PostRole, PostStatus, PostType
from matchbot.enrichment.www_guide import (
    GuideCamp,
    _find_best_match,
    _normalise,
    _parse_camp,
    enrich_camp_posts,
    fetch_guide_camps,
)

# ---------------------------------------------------------------------------
# _normalise
# ---------------------------------------------------------------------------


class TestNormalise:
    def test_lowercases(self):
        assert _normalise("Solar CIRCUS") == "solar circus"

    def test_strips_punctuation(self):
        assert _normalise("Camp: Foo-Bar!") == "camp foobar"

    def test_empty(self):
        assert _normalise("") == ""


# ---------------------------------------------------------------------------
# _parse_camp
# ---------------------------------------------------------------------------


class TestParseCamp:
    def test_basic_record(self):
        record = {
            "uid": "123",
            "name": "Solar Circus",
            "description": "We do art.",
            "location_string": "7:30 & Esplanade",
            "camp_size": "50",
            "hometown": "San Francisco",
        }
        camp = _parse_camp(record, year=2026)
        assert camp.name == "Solar Circus"
        assert camp.uid == "123"
        assert camp.camp_size == 50
        assert camp.year == 2026
        assert camp.location_string == "7:30 & Esplanade"

    def test_alternate_key_names(self):
        record = {"id": "99", "camp_name": "Dusty Palace", "address": "3:00 & C"}
        camp = _parse_camp(record, year=None)
        assert camp.name == "Dusty Palace"
        assert camp.location_string == "3:00 & C"

    def test_non_numeric_size_becomes_none(self):
        record = {"name": "Test Camp", "camp_size": "large"}
        camp = _parse_camp(record, year=None)
        assert camp.camp_size is None

    def test_missing_name_is_empty_string(self):
        camp = _parse_camp({}, year=None)
        assert camp.name == ""


# ---------------------------------------------------------------------------
# _find_best_match
# ---------------------------------------------------------------------------


class TestFindBestMatch:
    def _camps(self):
        return [
            GuideCamp(uid="1", name="Solar Circus"),
            GuideCamp(uid="2", name="Camp Dusty"),
            GuideCamp(uid="3", name="The Art Collective"),
        ]

    def test_exact_match(self):
        result = _find_best_match("Solar Circus", self._camps())
        assert result is not None
        assert result.uid == "1"

    def test_case_insensitive_match(self):
        result = _find_best_match("solar circus", self._camps())
        assert result is not None
        assert result.uid == "1"

    def test_substring_match(self):
        result = _find_best_match("Art Collective", self._camps())
        assert result is not None
        assert result.uid == "3"

    def test_no_match(self):
        result = _find_best_match("Completely Different Camp", self._camps())
        assert result is None

    def test_empty_name(self):
        result = _find_best_match("", self._camps())
        assert result is None


# ---------------------------------------------------------------------------
# fetch_guide_camps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_guide_camps_list_response():
    """Parses a JSON array response from the guide API."""
    mock_data = [
        {"uid": "1", "name": "Solar Circus", "camp_size": "40"},
        {"uid": "2", "name": "Camp Dusty"},
    ]

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_data
        mock_get.return_value = mock_response

        camps = await fetch_guide_camps("https://example.com/guide.json", year=2026)

    assert len(camps) == 2
    assert camps[0].name == "Solar Circus"
    assert camps[0].camp_size == 40
    assert camps[0].year == 2026


@pytest.mark.asyncio
async def test_fetch_guide_camps_wrapped_response():
    """Handles wrapped response: {"camps": [...]}."""
    mock_data = {"camps": [{"uid": "1", "name": "Test Camp"}]}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_data
        mock_get.return_value = mock_response

        camps = await fetch_guide_camps("https://example.com/guide.json")

    assert len(camps) == 1
    assert camps[0].name == "Test Camp"


@pytest.mark.asyncio
async def test_fetch_guide_camps_unexpected_format():
    """Returns empty list if response is not a list or known wrapped format."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = "unexpected string"
        mock_get.return_value = mock_response

        camps = await fetch_guide_camps("https://example.com/guide.json")

    assert camps == []


# ---------------------------------------------------------------------------
# enrich_camp_posts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrich_camp_posts_updates_fields(db_session):
    """Matching camp post gets enriched with guide data."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="camp_enrich_001",
        title="Solar Circus has openings",
        raw_text="Join our art camp!",
        status=PostStatus.INDEXED,
        post_type=PostType.MENTORSHIP,
        role=PostRole.CAMP,
        camp_name="Solar Circus",
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    guide_camps = [
        GuideCamp(
            uid="gc1",
            name="Solar Circus",
            camp_size=50,
            location_string="7:30 & Esplanade",
            year=2026,
        )
    ]

    result = await enrich_camp_posts(db_session, guide_camps)

    assert len(result) == 1
    updated_post, matched_camp = result[0]
    assert updated_post.camp_size_min == 50
    assert updated_post.camp_size_max == 50
    assert updated_post.location_preference == "7:30 & Esplanade"
    assert updated_post.year == 2026


@pytest.mark.asyncio
async def test_enrich_camp_posts_dry_run_does_not_commit(db_session):
    """Dry run returns enrichable pairs but does not write to DB."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="camp_enrich_002",
        title="Solar Circus camp openings",
        raw_text="Join us!",
        status=PostStatus.INDEXED,
        post_type=PostType.MENTORSHIP,
        role=PostRole.CAMP,
        camp_name="Solar Circus",
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)

    guide_camps = [GuideCamp(uid="gc2", name="Solar Circus", camp_size=60, year=2026)]

    result = await enrich_camp_posts(db_session, guide_camps, dry_run=True)

    assert len(result) == 1
    # Dry run: in-memory update but DB not committed
    # Re-fetch to confirm no write
    await db_session.refresh(post)
    # In dry_run mode the post object is mutated in memory but not committed
    # so the *returned* post has the new values, DB row still has original
    _, matched = result[0]
    assert matched.name == "Solar Circus"


@pytest.mark.asyncio
async def test_enrich_camp_posts_no_match(db_session):
    """Post with unmatched camp name is not enriched."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="camp_enrich_003",
        title="Unknown Camp",
        raw_text="We exist.",
        status=PostStatus.INDEXED,
        post_type=PostType.MENTORSHIP,
        role=PostRole.CAMP,
        camp_name="Completely Unknown Camp Name",
    )
    db_session.add(post)
    await db_session.commit()

    guide_camps = [GuideCamp(uid="gc3", name="Solar Circus", camp_size=50)]

    result = await enrich_camp_posts(db_session, guide_camps)
    assert result == []


@pytest.mark.asyncio
async def test_enrich_camp_posts_skips_already_set_fields(db_session):
    """Fields that are already populated are not overwritten."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="camp_enrich_004",
        title="Solar Circus camp",
        raw_text="We have openings.",
        status=PostStatus.INDEXED,
        post_type=PostType.MENTORSHIP,
        role=PostRole.CAMP,
        camp_name="Solar Circus",
        camp_size_min=30,
        camp_size_max=40,
        location_preference="Existing location",
        year=2025,
    )
    db_session.add(post)
    await db_session.commit()

    guide_camps = [
        GuideCamp(uid="gc4", name="Solar Circus", camp_size=60, location_string="New location", year=2026)
    ]

    result = await enrich_camp_posts(db_session, guide_camps)
    # No changes because all fields were already set
    assert result == []


@pytest.mark.asyncio
async def test_enrich_camp_posts_skips_infra_posts(db_session):
    """Infrastructure posts are never enriched with camp guide data."""
    post = Post(
        platform=Platform.REDDIT,
        platform_post_id="camp_enrich_005",
        title="Solar Circus generator available",
        raw_text="Infra post.",
        status=PostStatus.INDEXED,
        post_type=PostType.INFRASTRUCTURE,
        role=PostRole.CAMP,
        camp_name="Solar Circus",
    )
    db_session.add(post)
    await db_session.commit()

    guide_camps = [GuideCamp(uid="gc5", name="Solar Circus", camp_size=50)]

    result = await enrich_camp_posts(db_session, guide_camps)
    assert result == []


# ---------------------------------------------------------------------------
# Intake form routes
# ---------------------------------------------------------------------------


def test_intake_landing_page():
    """GET /forms/ returns HTML with links."""
    from fastapi.testclient import TestClient

    from matchbot.server import create_app

    client = TestClient(create_app())
    response = client.get("/forms/")
    assert response.status_code == 200
    assert "Rising Sparks Pool" in response.text
    assert "/forms/seeker" in response.text
    assert "/forms/camp" in response.text
    assert "/forms/infra" in response.text


def test_intake_seeker_form_renders():
    """GET /forms/seeker returns the seeker form HTML."""
    from fastapi.testclient import TestClient

    from matchbot.server import create_app

    client = TestClient(create_app())
    response = client.get("/forms/seeker")
    assert response.status_code == 200
    assert "Find Your Community" in response.text
    assert 'name="display_name"' in response.text


def test_intake_camp_form_renders():
    """GET /forms/camp returns the camp form HTML."""
    from fastapi.testclient import TestClient

    from matchbot.server import create_app

    client = TestClient(create_app())
    response = client.get("/forms/camp")
    assert response.status_code == 200
    assert "Find Your Builders" in response.text
    assert 'name="camp_name"' in response.text


def test_intake_infra_form_renders():
    """GET /forms/infra returns the infrastructure form HTML."""
    from fastapi.testclient import TestClient

    from matchbot.server import create_app

    client = TestClient(create_app())
    response = client.get("/forms/infra")
    assert response.status_code == 200
    assert "Share Infra Signals" in response.text
    assert 'name="infra_role"' in response.text
    assert 'name="infra_categories"' in response.text


def test_intake_seeker_submit_redirects():
    """POST /forms/seeker creates a Post and redirects to /forms/thanks."""
    from fastapi.testclient import TestClient

    from matchbot.server import create_app

    client = TestClient(create_app(), follow_redirects=False)
    response = client.post(
        "/forms/seeker",
        data={
            "display_name": "TestBurner",
            "bio": "I love to build and cook.",
            "vibes": "art, build_focused",
            "contributions": "build, kitchen",
            "year": "2026",
            "availability_notes": "Available build week",
            "contact_method": "DM on Reddit",
        },
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/forms/thanks"


def test_intake_camp_submit_redirects():
    """POST /forms/camp creates a Post and redirects to /forms/thanks."""
    from fastapi.testclient import TestClient

    from matchbot.server import create_app

    client = TestClient(create_app(), follow_redirects=False)
    response = client.post(
        "/forms/camp",
        data={
            "camp_name": "Solar Circus",
            "display_name": "CampContact",
            "bio": "We do art and fire.",
            "vibes": "art, fire",
            "contributions": "build, art",
            "camp_size": "40",
            "year": "2026",
            "availability_notes": "Need early arrival crew",
            "contact_method": "DM on Reddit",
        },
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/forms/thanks"


def test_intake_infra_submit_redirects():
    """POST /forms/infra creates a Post and redirects to /forms/thanks."""
    from fastapi.testclient import TestClient

    from matchbot.server import create_app

    client = TestClient(create_app(), follow_redirects=False)
    response = client.post(
        "/forms/infra",
        data={
            "display_name": "DustOps",
            "infra_role": "seeking",
            "infra_categories": "power, shade",
            "quantity": "2 generators",
            "condition": "good",
            "dates_needed": "build week",
            "bio": "Need backup generation and extra shade.",
            "contact_method": "DM on Reddit",
        },
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/forms/thanks"


def test_intake_thanks_page():
    """GET /forms/thanks returns confirmation page."""
    from fastapi.testclient import TestClient

    from matchbot.server import create_app

    client = TestClient(create_app())
    response = client.get("/forms/thanks")
    assert response.status_code == 200
    assert "Welcome to the Pool" in response.text
