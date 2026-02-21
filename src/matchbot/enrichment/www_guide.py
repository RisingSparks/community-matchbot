"""
WWW Guide (What/Where/When) camp data enrichment.

Fetches theme camp data from the Burning Man guide API and enriches
matched camp Post records with structured metadata.

The guide API returns an array of camp objects. The URL and year are
configurable via settings (WWW_GUIDE_URL and WWW_GUIDE_YEAR).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Post, PostRole, PostStatus, PostType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model for a guide camp record
# ---------------------------------------------------------------------------


@dataclass
class GuideCamp:
    """Normalised view of a single camp from the WWW Guide."""

    uid: str
    name: str
    description: str = ""
    location_string: str = ""  # e.g. "7:30 & Esplanade"
    camp_size: int | None = None
    hometown: str = ""
    url: str = ""
    year: int | None = None
    raw: dict = field(default_factory=dict)


def _parse_camp(record: dict, year: int | None) -> GuideCamp:
    """Map a raw guide API record to a GuideCamp."""
    # The guide API uses different key names across years; handle common variants
    name = (
        record.get("name")
        or record.get("camp_name")
        or record.get("title")
        or ""
    )
    uid = str(record.get("uid") or record.get("id") or record.get("entity_id") or name)
    description = record.get("description") or record.get("body") or ""
    location_string = (
        record.get("location_string")
        or record.get("location")
        or record.get("address")
        or ""
    )
    camp_size_raw = record.get("camp_size") or record.get("size")
    camp_size: int | None = None
    try:
        if camp_size_raw is not None:
            camp_size = int(camp_size_raw)
    except (ValueError, TypeError):
        pass

    hometown = record.get("hometown") or record.get("city") or ""
    url = record.get("url") or record.get("website") or ""

    return GuideCamp(
        uid=uid,
        name=name,
        description=description,
        location_string=location_string,
        camp_size=camp_size,
        hometown=hometown,
        url=url,
        year=year,
        raw=record,
    )


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


async def fetch_guide_camps(url: str, year: int | None = None) -> list[GuideCamp]:
    """
    Fetch and parse camp records from the WWW Guide endpoint.

    ``url`` should point to a JSON array of camp objects.

    Raises ``httpx.HTTPError`` on network / status errors.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    if isinstance(data, dict):
        # Some guide APIs wrap the array: {"camps": [...]} or {"data": [...]}
        data = data.get("camps") or data.get("data") or data.get("results") or []

    if not isinstance(data, list):
        logger.warning("WWW Guide response was not a list; got %s", type(data).__name__)
        return []

    camps = []
    for record in data:
        if not isinstance(record, dict):
            continue
        try:
            camps.append(_parse_camp(record, year=year))
        except Exception as exc:
            logger.debug("Skipping malformed guide record: %s", exc)
    return camps


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------


def _normalise(name: str) -> str:
    """Lower-case, strip punctuation for fuzzy camp name matching."""
    import re
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def _find_best_match(post_camp_name: str, guide_camps: list[GuideCamp]) -> GuideCamp | None:
    """Return the guide camp whose normalised name best matches the post's camp_name."""
    normalised_post = _normalise(post_camp_name)
    if not normalised_post:
        return None

    # Exact match first
    for gc in guide_camps:
        if _normalise(gc.name) == normalised_post:
            return gc

    # Substring match (post name inside guide name or vice versa)
    for gc in guide_camps:
        ng = _normalise(gc.name)
        if normalised_post in ng or ng in normalised_post:
            return gc

    return None


async def enrich_camp_posts(
    session: AsyncSession,
    guide_camps: list[GuideCamp],
    dry_run: bool = False,
) -> list[tuple[Post, GuideCamp]]:
    """
    Match guide camp data against indexed camp posts and write enrichments.

    For each matched pair, overwrites:
    - ``camp_size_min`` / ``camp_size_max`` (from guide size if not already set)
    - ``location_preference``  (guide location_string)
    - ``year`` (guide year, if the post has no year set)

    Returns a list of ``(post, guide_camp)`` pairs that were (or would be) updated.
    """
    if not guide_camps:
        return []

    camp_posts = (
        await session.exec(
            select(Post).where(
                Post.post_type == PostType.MENTORSHIP,
                Post.role == PostRole.CAMP,
                Post.status == PostStatus.INDEXED,
                Post.camp_name.isnot(None),  # type: ignore[union-attr]
            )
        )
    ).all()

    enriched: list[tuple[Post, GuideCamp]] = []

    for post in camp_posts:
        if not post.camp_name:
            continue
        match = _find_best_match(post.camp_name, guide_camps)
        if match is None:
            continue

        changed = False

        if match.camp_size and post.camp_size_min is None and post.camp_size_max is None:
            post.camp_size_min = match.camp_size
            post.camp_size_max = match.camp_size
            changed = True

        if match.location_string and not post.location_preference:
            post.location_preference = match.location_string
            changed = True

        if match.year and post.year is None:
            post.year = match.year
            changed = True

        if changed:
            enriched.append((post, match))
            if not dry_run:
                session.add(post)

    if not dry_run and enriched:
        await session.commit()
        for post, _ in enriched:
            await session.refresh(post)

    return enriched
