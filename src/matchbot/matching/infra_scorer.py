"""Infra exchange scorer — matches infrastructure seeking/offering posts."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from matchbot.db.models import InfraRole, Post


def _category_jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity for infra category overlap."""
    if not a and not b:
        return 0.0  # both unknown → no signal (unlike mentorship where 0.5 for flexibility)
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union)


def _role_compatible(post_a: Post, post_b: Post) -> bool:
    """Return True only when one is seeking and the other is offering."""
    roles = {post_a.infra_role, post_b.infra_role}
    return roles == {InfraRole.SEEKING, InfraRole.OFFERING}


def _recency_score(detected_at: datetime | None) -> float:
    """Exponential decay with 30-day half-life; 0.0 after 60 days."""
    if detected_at is None:
        return 0.0
    now = datetime.now(UTC)
    if detected_at.tzinfo is None:
        detected_at = detected_at.replace(tzinfo=UTC)
    age_days = (now - detected_at).total_seconds() / 86400
    if age_days > 60:
        return 0.0
    return math.exp(-math.log(2) * age_days / 30.0)


INFRA_WEIGHTS = {
    "category_overlap": 0.60,
    "recency": 0.25,
    "role_match": 0.15,
}


def score_infra_match(post_a: Post, post_b: Post) -> tuple[float, dict]:
    """
    Compute composite match score between two infrastructure posts.

    One must be seeking, the other offering; they must share at least one category.
    Returns (composite_score, breakdown_dict).
    Returns (0.0, {}) if the pair is role-incompatible.
    """
    if not _role_compatible(post_a, post_b):
        return 0.0, {}

    cats_a = set(post_a.infra_categories_list())
    cats_b = set(post_b.infra_categories_list())
    category_overlap = _category_jaccard(cats_a, cats_b)

    # No category overlap → not a useful match
    if category_overlap == 0.0:
        return 0.0, {}

    older_date = min(
        post_a.detected_at or datetime.now(UTC),
        post_b.detected_at or datetime.now(UTC),
    )
    recency = _recency_score(older_date)
    role_match = 1.0  # already validated above

    breakdown = {
        "category_overlap": round(category_overlap, 4),
        "recency": round(recency, 4),
        "role_match": role_match,
    }

    composite = (
        INFRA_WEIGHTS["category_overlap"] * category_overlap
        + INFRA_WEIGHTS["recency"] * recency
        + INFRA_WEIGHTS["role_match"] * role_match
    )

    return round(composite, 4), breakdown
