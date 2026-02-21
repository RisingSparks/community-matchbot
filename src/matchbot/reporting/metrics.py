"""Pilot metric queries and export utilities."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Match, MatchStatus, Post, PostRole, PostStatus, Profile


async def compute_metrics(session: AsyncSession) -> dict:
    """Compute pilot metrics from the database."""

    # Profile counts
    active_camps = len(
        (await session.exec(
            select(Profile).where(Profile.role == PostRole.CAMP, Profile.is_active)
        )).all()
    )
    active_seekers = len(
        (await session.exec(
            select(Profile).where(Profile.role == PostRole.SEEKER, Profile.is_active)
        )).all()
    )

    # Post counts
    indexed_posts = len(
        (await session.exec(select(Post).where(Post.status == PostStatus.INDEXED))).all()
    )

    all_matches = (await session.exec(select(Match))).all()
    total_attempts = len(all_matches)

    terminal_sent = {
        MatchStatus.INTRO_SENT,
        MatchStatus.CONVERSATION_STARTED,
        MatchStatus.ACCEPTED_PENDING,
        MatchStatus.ONBOARDED,
    }
    terminal_conv = {
        MatchStatus.CONVERSATION_STARTED,
        MatchStatus.ACCEPTED_PENDING,
        MatchStatus.ONBOARDED,
    }

    intro_sent = sum(1 for m in all_matches if m.status in terminal_sent)
    conv_started = sum(1 for m in all_matches if m.status in terminal_conv)
    onboarded = sum(1 for m in all_matches if m.status == MatchStatus.ONBOARDED)

    intro_to_conv_rate = conv_started / intro_sent if intro_sent > 0 else 0.0
    conv_to_onboard_rate = onboarded / conv_started if conv_started > 0 else 0.0

    # Mismatch reasons
    mismatch_counts: Counter = Counter()
    for m in all_matches:
        if m.mismatch_reason:
            mismatch_counts[m.mismatch_reason] += 1

    # By platform
    all_posts = (await session.exec(select(Post))).all()
    platform_counts: Counter = Counter(p.platform for p in all_posts)

    # By contribution type
    contrib_counts: Counter = Counter()
    for p in all_posts:
        if p.status == PostStatus.INDEXED:
            for ct in p.contribution_types_list():
                contrib_counts[ct] += 1

    return {
        "computed_at": datetime.now(UTC).isoformat(),
        "active_camp_profiles": active_camps,
        "active_seeker_profiles": active_seekers,
        "total_posts_indexed": indexed_posts,
        "match_attempts_total": total_attempts,
        "intro_sent_total": intro_sent,
        "conversation_started_total": conv_started,
        "onboarded_total": onboarded,
        "intro_to_conversation_rate": round(intro_to_conv_rate, 4),
        "conversation_to_onboarding_rate": round(conv_to_onboard_rate, 4),
        "top_mismatch_reasons": dict(mismatch_counts.most_common(10)),
        "by_platform": dict(platform_counts),
        "by_contribution_type": dict(contrib_counts.most_common()),
    }


async def export_metrics_json(session: AsyncSession, path: str | Path) -> None:
    metrics = await compute_metrics(session)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)


async def export_matches_csv(session: AsyncSession, path: str | Path) -> None:
    matches = (await session.exec(select(Match))).all()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id", "status", "score", "match_method", "confidence",
                "seeker_post_id", "camp_post_id",
                "intro_sent_at", "intro_platform",
                "mismatch_reason", "created_at", "updated_at",
            ],
        )
        writer.writeheader()
        for m in matches:
            writer.writerow({
                "id": m.id,
                "status": m.status,
                "score": m.score,
                "match_method": m.match_method,
                "confidence": m.confidence,
                "seeker_post_id": m.seeker_post_id,
                "camp_post_id": m.camp_post_id,
                "intro_sent_at": m.intro_sent_at,
                "intro_platform": m.intro_platform,
                "mismatch_reason": m.mismatch_reason,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
            })
