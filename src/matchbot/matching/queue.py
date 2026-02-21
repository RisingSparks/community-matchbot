"""Match queue CRUD — propose, list, and retrieve matches."""

from __future__ import annotations

import json

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Match, MatchStatus, Post, PostRole, PostStatus
from matchbot.matching.scorer import score_match
from matchbot.settings import get_settings


async def propose_matches(session: AsyncSession, new_post: Post) -> list[Match]:
    """
    Find match candidates for a newly indexed post and create Match records.

    Skips pairs that already have a match record.
    """
    settings = get_settings()
    min_score = settings.matching_min_score
    triage_low = settings.matching_llm_triage_band_low
    triage_high = settings.matching_llm_triage_band_high

    # Determine which role is the "other" side
    if new_post.role == PostRole.SEEKER:
        seeker = new_post
        candidate_role = PostRole.CAMP
    elif new_post.role == PostRole.CAMP:
        camp = new_post
        candidate_role = PostRole.SEEKER
    else:
        return []  # unknown role — skip

    # Fetch all indexed posts of the opposite role
    candidates = (
        await session.exec(
            select(Post).where(
                Post.status == PostStatus.INDEXED,
                Post.role == candidate_role,
                Post.id != new_post.id,
            )
        )
    ).all()

    created: list[Match] = []

    for candidate in candidates:
        if new_post.role == PostRole.SEEKER:
            camp = candidate
        else:
            seeker = candidate

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

        composite, breakdown = score_match(seeker, camp)

        if composite < min_score:
            continue

        method = "deterministic"
        confidence = composite

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
            match_method=method,
            confidence=confidence,
            moderator_notes="[needs LLM triage]" if triage_needed else None,
        )
        session.add(match)
        created.append(match)

    await session.commit()
    # Refresh all created matches so attributes are accessible after commit
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
            .order_by(Match.score.desc())  # type: ignore[arg-type]
            .limit(limit)
        )
    ).all()
    return list(matches)


async def get_match(session: AsyncSession, match_id: str) -> Match | None:
    return await session.get(Match, match_id)
