"""Match queue CRUD — propose, list, and retrieve matches."""

from __future__ import annotations

import json

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Match, MatchStatus, Post, PostRole, PostStatus, PostType, is_opted_out
from matchbot.matching.infra_scorer import score_infra_match
from matchbot.matching.scorer import score_match
from matchbot.messaging.renderer import render_intro
from matchbot.settings import get_settings


async def propose_matches(session: AsyncSession, new_post: Post) -> list[Match]:
    """
    Find match candidates for a newly indexed post and create Match records.

    Dispatches to infra or mentorship scoring based on post_type.
    Skips pairs that already have a match record.
    """
    if new_post.post_type == PostType.INFRASTRUCTURE:
        return await _propose_infra_matches(session, new_post)
    return await _propose_mentorship_matches(session, new_post)


async def _propose_mentorship_matches(session: AsyncSession, new_post: Post) -> list[Match]:
    settings = get_settings()
    min_score = settings.matching_min_score
    triage_low = settings.matching_llm_triage_band_low
    triage_high = settings.matching_llm_triage_band_high

    # Determine which role is the "other" side
    if new_post.role == PostRole.SEEKER:
        seeker = new_post
        camp = None
        candidate_role = PostRole.CAMP
    elif new_post.role == PostRole.CAMP:
        seeker = None
        camp = new_post
        candidate_role = PostRole.SEEKER
    else:
        return []  # unknown role — skip

    # Skip if the new post's author has opted out or the post itself is opted out
    if new_post.opted_out:
        return []
    if await is_opted_out(session, new_post.platform, new_post.platform_author_id):
        return []

    # Fetch all indexed posts of the opposite role
    candidates = (
        await session.exec(
            select(Post).where(
                Post.status == PostStatus.INDEXED,
                Post.role == candidate_role,
                Post.post_type == PostType.MENTORSHIP,
                Post.id != new_post.id,
                Post.opted_out == False,  # noqa: E712
            )
        )
    ).all()

    created: list[Match] = []

    for candidate in candidates:
        if new_post.role == PostRole.SEEKER:
            camp = candidate
        else:
            seeker = candidate

        # Skip opted-out candidates
        if await is_opted_out(session, candidate.platform, candidate.platform_author_id):
            continue

        # Deduplicate: skip if match already exists
        existing = (
            await session.exec(
                select(Match).where(
                    Match.seeker_post_id == seeker.id,
                    Match.camp_post_id == camp.id,
                )
            )
        ).first()
        if existing:
            continue

        composite, breakdown = score_match(seeker, camp, seeker_intent=seeker.seeker_intent)

        if composite < min_score:
            continue

        # LLM triage band — store flag in moderator_notes; actual triage happens lazily
        triage_needed = triage_low <= composite < triage_high

        match = Match(
            seeker_post_id=seeker.id,
            camp_post_id=camp.id,
            seeker_profile_id=seeker.profile_id,
            camp_profile_id=camp.profile_id,
            status=MatchStatus.PROPOSED,
            score=composite,
            score_breakdown=json.dumps(breakdown),
            match_method="deterministic",
            confidence=composite,
            moderator_notes="[needs LLM triage]" if triage_needed else None,
        )
        try:
            match.intro_draft = render_intro(seeker, camp, seeker.platform)
        except Exception:
            pass  # draft is best-effort; don't block match creation
        session.add(match)
        created.append(match)

    await session.commit()
    for match in created:
        await session.refresh(match)
    return created


async def _propose_infra_matches(session: AsyncSession, new_post: Post) -> list[Match]:
    settings = get_settings()
    min_score = settings.matching_min_score

    # Skip if the new post's author has opted out or the post itself is opted out
    if new_post.opted_out:
        return []
    if await is_opted_out(session, new_post.platform, new_post.platform_author_id):
        return []

    # Fetch all indexed infra posts (opposite role handled inside scorer)
    candidates = (
        await session.exec(
            select(Post).where(
                Post.status == PostStatus.INDEXED,
                Post.post_type == PostType.INFRASTRUCTURE,
                Post.id != new_post.id,
                Post.opted_out == False,  # noqa: E712
            )
        )
    ).all()

    created: list[Match] = []

    for candidate in candidates:
        # Skip opted-out candidates
        if await is_opted_out(session, candidate.platform, candidate.platform_author_id):
            continue

        # Use canonical ordering: seeker_post_id always holds the "seeking" post
        if new_post.infra_role == "seeking":
            seeker, offerer = new_post, candidate
        else:
            seeker, offerer = candidate, new_post

        # Deduplicate
        existing = (
            await session.exec(
                select(Match).where(
                    Match.seeker_post_id == seeker.id,
                    Match.camp_post_id == offerer.id,
                )
            )
        ).first()
        if existing:
            continue

        composite, breakdown = score_infra_match(new_post, candidate)
        if composite < min_score:
            continue

        match = Match(
            seeker_post_id=seeker.id,
            camp_post_id=offerer.id,
            seeker_profile_id=seeker.profile_id,
            camp_profile_id=offerer.profile_id,
            status=MatchStatus.PROPOSED,
            score=composite,
            score_breakdown=json.dumps(breakdown),
            match_method="deterministic_infra",
            confidence=composite,
        )
        try:
            match.intro_draft = render_intro(seeker, offerer, seeker.platform)
        except Exception:
            pass  # draft is best-effort; don't block match creation
        session.add(match)
        created.append(match)

    await session.commit()
    for match in created:
        await session.refresh(match)
    return created


async def get_queue(
    session: AsyncSession,
    status: str = MatchStatus.PROPOSED,
    min_score: float = 0.0,
    limit: int = 50,
) -> list[Match]:
    """Return matches in the queue, ordered by score descending."""
    matches = (
        await session.exec(
            select(Match)
            .where(Match.status == status, Match.score >= min_score)
            .order_by(Match.score.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
    ).all()
    return list(matches)


async def get_match(session: AsyncSession, match_id: str) -> Match | None:
    return await session.get(Match, match_id)
