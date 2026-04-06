"""Tests for match queue propose logic."""

from __future__ import annotations

import pytest

from matchbot.db.models import Post, PostRole, PostStatus, PostType
from matchbot.matching.queue import propose_matches


def _make_post(role: str, platform_post_id: str, platform_author_id: str, **kwargs) -> Post:
    return Post(
        platform="manual",
        platform_post_id=platform_post_id,
        platform_author_id=platform_author_id,
        author_display_name="Test",
        raw_text="test post",
        status=PostStatus.INDEXED,
        role=role,
        post_type=PostType.MENTORSHIP,
        vibes="art|build_focused",
        contribution_types="build|art",
        year=2025,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_opted_out_candidate_excluded(db_session):
    """An opted-out camp should not be matched against an incoming seeker."""
    seeker = _make_post(PostRole.SEEKER, "s1", "u1")
    camp = _make_post(PostRole.CAMP, "c1", "u2", opted_out=True)
    db_session.add(seeker)
    db_session.add(camp)
    await db_session.commit()

    matches = await propose_matches(db_session, seeker)
    assert matches == []


@pytest.mark.asyncio
async def test_opted_out_new_post_excluded(db_session):
    """If the new post itself is opted out, no matches should be proposed."""
    seeker = _make_post(PostRole.SEEKER, "s1", "u1", opted_out=True)
    camp = _make_post(PostRole.CAMP, "c1", "u2")
    db_session.add(seeker)
    db_session.add(camp)
    await db_session.commit()

    matches = await propose_matches(db_session, seeker)
    assert matches == []
