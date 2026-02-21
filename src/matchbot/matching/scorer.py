"""Deterministic Jaccard-based matching scorer."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from matchbot.db.models import Post, PostRole


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity. Empty sets → 0.5 (both unknown = mild positive signal)."""
    if not a and not b:
        return 0.5
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union)


def _recency_score(detected_at: datetime | None) -> float:
    """Exponential decay with 30-day half-life. 0.0 after 60 days."""
    if detected_at is None:
        return 0.0
    now = datetime.now(timezone.utc)
    # Ensure timezone awareness
    if detected_at.tzinfo is None:
        detected_at = detected_at.replace(tzinfo=timezone.utc)
    age_days = (now - detected_at).total_seconds() / 86400
    if age_days > 60:
        return 0.0
    half_life = 30.0
    return math.exp(-math.log(2) * age_days / half_life)


def _year_score(seeker_year: int | None, camp_year: int | None) -> float:
    """Year compatibility score."""
    if seeker_year is not None and camp_year is not None:
        return 1.0 if seeker_year == camp_year else 0.0
    if seeker_year is None and camp_year is None:
        return 0.7
    return 0.5  # one specified, one not


WEIGHTS = {
    "vibe_overlap": 0.35,
    "contribution_overlap": 0.40,
    "recency": 0.15,
    "year_match": 0.10,
}


def score_match(seeker: Post, camp: Post) -> tuple[float, dict]:
    """
    Compute composite match score between a seeker and a camp post.

    Returns (composite_score, breakdown_dict).
    """
    seeker_vibes = set(seeker.vibes_list())
    camp_vibes = set(camp.vibes_list())
    seeker_contribs = set(seeker.contribution_types_list())
    camp_contribs = set(camp.contribution_types_list())

    vibe_overlap = _jaccard(seeker_vibes, camp_vibes)
    contribution_overlap = _jaccard(seeker_contribs, camp_contribs)

    # Use the older (more stale) post for recency — penalise stale pairs
    older_date = min(
        seeker.detected_at or datetime.now(timezone.utc),
        camp.detected_at or datetime.now(timezone.utc),
    )
    recency = _recency_score(older_date)
    year_match = _year_score(seeker.year, camp.year)

    breakdown = {
        "vibe_overlap": round(vibe_overlap, 4),
        "contribution_overlap": round(contribution_overlap, 4),
        "recency": round(recency, 4),
        "year_match": round(year_match, 4),
    }

    composite = (
        WEIGHTS["vibe_overlap"] * vibe_overlap
        + WEIGHTS["contribution_overlap"] * contribution_overlap
        + WEIGHTS["recency"] * recency
        + WEIGHTS["year_match"] * year_match
    )

    return round(composite, 4), breakdown
