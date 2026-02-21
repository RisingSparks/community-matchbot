"""Extraction orchestration: keyword filter → LLM extraction → DB update."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Event, Post, PostStatus
from matchbot.extraction.base import LLMExtractor
from matchbot.extraction.keywords import keyword_filter
from matchbot.settings import get_settings
from matchbot.taxonomy import normalize_contribution_types, normalize_infra_categories, normalize_vibes


async def process_post(session: AsyncSession, post: Post, extractor: LLMExtractor) -> Post:
    """
    Full extraction pipeline for a single post.

    1. Keyword filter (no LLM)
    2. If no match: status=SKIPPED, return
    3. LLM extraction
    4. Normalize against taxonomy
    5. Update Post fields + status
    6. Append Event record
    7. Call propose_matches (deferred import to avoid circular)
    """
    settings = get_settings()

    # --- 1. Keyword filter ---
    kw_result = keyword_filter(post.title, post.raw_text)

    if not kw_result.matched:
        post.status = PostStatus.SKIPPED
        post.extraction_method = "keyword"
        session.add(post)
        await _append_event(session, post, "post_skipped", {"reason": "keyword_filter_no_match"})
        await session.commit()
        await session.refresh(post)
        return post

    # Seed post_type and infra_role from keyword filter hints
    post.post_type = kw_result.post_type
    if kw_result.infra_role is not None:
        post.infra_role = kw_result.infra_role

    # Use keyword role hint if LLM later can't determine
    keyword_role_hint = kw_result.candidate_role

    # --- 3. LLM extraction ---
    try:
        extracted = await extractor.extract(
            title=post.title,
            body=post.raw_text,
            platform=post.platform,
            source_community=post.source_community,
        )
    except Exception as exc:
        post.status = PostStatus.ERROR
        session.add(post)
        await _append_event(
            session, post, "extraction_error", {"error": str(exc), "provider": extractor.provider_name()}
        )
        await session.commit()
        await session.refresh(post)
        return post

    # --- 4. Normalize against taxonomy ---
    valid_vibes = normalize_vibes(extracted.vibes)
    valid_contributions = normalize_contribution_types(extracted.contribution_types)
    valid_infra_categories = normalize_infra_categories(extracted.infra_categories)

    # --- 5. Update Post fields ---
    post.post_type = extracted.post_type

    # Mentorship fields
    post.role = extracted.role if extracted.role else keyword_role_hint
    post.vibes = "|".join(valid_vibes)
    post.contribution_types = "|".join(valid_contributions)
    post.camp_name = extracted.camp_name
    post.camp_size_min = extracted.camp_size_min
    post.camp_size_max = extracted.camp_size_max
    post.year = extracted.year
    post.location_preference = extracted.location_preference
    post.availability_notes = extracted.availability_notes
    post.contact_method = extracted.contact_method

    # Infrastructure fields
    post.infra_role = extracted.infra_role
    post.infra_categories = "|".join(valid_infra_categories)
    post.quantity = extracted.quantity
    post.condition = extracted.condition
    post.dates_needed = extracted.dates_needed

    post.extraction_confidence = extracted.confidence
    post.extraction_method = f"llm_{extractor.provider_name()}"

    if extracted.confidence < settings.llm_extraction_confidence_threshold:
        post.status = PostStatus.NEEDS_REVIEW
    else:
        post.status = PostStatus.INDEXED

    session.add(post)
    await _append_event(
        session,
        post,
        "post_extracted",
        {
            "provider": extractor.provider_name(),
            "confidence": extracted.confidence,
            "post_type": post.post_type,
            "role": post.role,
            "infra_role": post.infra_role,
            "status": post.status,
        },
    )
    await session.commit()
    await session.refresh(post)

    # --- 7. Propose matches (for all INDEXED posts; dispatcher handles type routing) ---
    if post.status == PostStatus.INDEXED:
        from matchbot.matching.queue import propose_matches

        await propose_matches(session, post)
        # propose_matches commits, which expires post; refresh to keep attributes accessible
        await session.refresh(post)

    return post


async def _append_event(
    session: AsyncSession,
    post: Post,
    event_type: str,
    payload: dict,
    actor: str = "system",
    note: str | None = None,
) -> None:
    event = Event(
        event_type=event_type,
        post_id=post.id,
        actor=actor,
        payload=json.dumps(payload),
        note=note,
    )
    session.add(event)
