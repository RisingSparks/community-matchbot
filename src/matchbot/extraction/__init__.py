"""Extraction orchestration: keyword filter → LLM extraction → DB update."""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Event, Post, PostStatus, PostType
from matchbot.db.profiles import sync_profile_from_post
from matchbot.extraction.base import LLMExtractor
from matchbot.extraction.keywords import keyword_filter
from matchbot.log_config import log_exception
from matchbot.settings import get_settings
from matchbot.taxonomy import (
    normalize_condition,
    split_contribution_types,
    split_infra_categories,
    split_vibes,
)

logger = logging.getLogger(__name__)

_SERVICE_REQUEST_PATTERN = re.compile(
    r"\b("
    r"clean(?:ing)?|deep\s+clean|repair|fix(?:ing)?|maintenance|service|servicing|"
    r"technician|specialist|professional\s+help|restoration|tune[\s-]?up|detail(?:ing)?"
    r")\b"
)
_INFRA_EXCHANGE_PATTERN = re.compile(
    r"\b("
    r"borrow|lend|loan|rent|share|swap|sell|give(?:\s+away)?|available|extra|spare|"
    r"free\s+to\s+a\s+good\s+home"
    r")\b"
)


def _join_pipe(values: list[str]) -> str:
    return "|".join(values)


def _is_service_like_infrastructure_post(title: str, body: str, extracted_post_type: str | None) -> bool:
    """Reject service/repair asks that drift into infrastructure despite not being gear exchange."""
    if extracted_post_type != PostType.INFRASTRUCTURE:
        return False

    text = f"{title}\n{body}".lower()
    return bool(_SERVICE_REQUEST_PATTERN.search(text)) and not bool(
        _INFRA_EXCHANGE_PATTERN.search(text)
    )


async def process_post(
    session: AsyncSession,
    post: Post,
    extractor: LLMExtractor,
    on_extraction_error: Literal["error", "raw"] = "error",
) -> Post:
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

    if kw_result.tier == "no_match":
        post.status = PostStatus.SKIPPED
        # SKIPPED means we intentionally did not classify the post.
        post.post_type = None
        post.extraction_method = "keyword"
        session.add(post)
        await _append_event(session, post, "post_skipped", {"reason": "keyword_filter_no_match"})
        await session.commit()
        await session.refresh(post)
        return post

    if kw_result.tier == "soft_match":
        if kw_result.post_type != PostType.MENTORSHIP:
            post.status = PostStatus.NEEDS_REVIEW
            post.post_type = kw_result.post_type
            if kw_result.infra_role is not None:
                post.infra_role = kw_result.infra_role
            post.role = kw_result.candidate_role
            post.extraction_method = "keyword_soft"
            session.add(post)
            await _append_event(
                session,
                post,
                "post_soft_matched",
                {
                    "score": kw_result.score,
                    "reasons": list(kw_result.reasons),
                    "post_type": post.post_type,
                    "role": post.role,
                    "infra_role": post.infra_role,
                },
            )
            await session.commit()
            await session.refresh(post)
            return post

    # Seed post_type and infra_role from keyword filter hints
    post.post_type = kw_result.post_type
    if kw_result.infra_role is not None:
        post.infra_role = kw_result.infra_role

    # --- 3. LLM extraction ---
    try:
        extracted = await extractor.extract(
            title=post.title,
            body=post.raw_text,
            platform=post.platform,
            source_community=post.source_community,
        )
    except Exception as exc:
        log_exception(logger, "Extraction failed for post %s: %s", post.id, exc)
        post.status = PostStatus.ERROR if on_extraction_error == "error" else PostStatus.RAW
        session.add(post)
        await _append_event(
            session,
            post,
            "extraction_error",
            {"error": str(exc), "provider": extractor.provider_name()},
        )
        await session.commit()
        await session.refresh(post)
        return post

    # --- 4. Normalize against taxonomy ---
    valid_vibes, vibe_other = split_vibes(extracted.vibes + extracted.vibes_other)
    valid_contributions, contribution_other = split_contribution_types(
        extracted.contribution_types + extracted.contribution_types_other
    )
    valid_infra_categories, infra_categories_other = split_infra_categories(
        extracted.infra_categories + extracted.infra_categories_other
    )
    valid_condition = normalize_condition(extracted.condition)
    condition_other = extracted.condition_other.strip() if extracted.condition_other else None
    if extracted.condition and valid_condition is None:
        condition_other = extracted.condition.strip().lower()

    if _is_service_like_infrastructure_post(post.title, post.raw_text, extracted.post_type):
        extracted = extracted.model_copy(
            update={
                "post_type": None,
                "infra_role": None,
                "infra_categories": [],
                "infra_categories_other": [],
                "quantity": None,
                "condition": None,
                "condition_other": None,
                "dates_needed": None,
                "extraction_notes": extracted.extraction_notes
                or "Service/repair request, not a tangible gear exchange post.",
            }
        )
        valid_infra_categories = []
        infra_categories_other = []
        valid_condition = None
        condition_other = None

    # --- 5. Update Post fields ---
    post.post_type = extracted.post_type

    if post.post_type is None:
        # LLM determined the post is not relevant to camp-finding or gear exchange
        post.status = PostStatus.SKIPPED
        post.extraction_confidence = extracted.confidence
        post.extraction_method = f"llm_{extractor.provider_name()}"
        # Deactivate any profile backed solely by this post (re-extraction flow)
        await sync_profile_from_post(session, post)
        session.add(post)
        await _append_event(
            session,
            post,
            "post_skipped",
            {
                "reason": "llm_not_relevant",
                "provider": extractor.provider_name(),
                "confidence": extracted.confidence,
                "extraction_notes": extracted.extraction_notes,
            },
        )
        await session.commit()
        await session.refresh(post)
        return post

    # Mentorship fields
    post.role = extracted.role
    post.seeker_intent = extracted.seeker_intent
    post.vibes = _join_pipe(valid_vibes)
    post.vibes_other = _join_pipe(vibe_other)
    post.contribution_types = _join_pipe(valid_contributions)
    post.contribution_types_other = _join_pipe(contribution_other)
    post.camp_name = extracted.camp_name
    post.camp_size_min = extracted.camp_size_min
    post.camp_size_max = extracted.camp_size_max
    post.year = extracted.year
    post.location_preference = extracted.location_preference
    post.origin_location_raw = extracted.origin_location_raw
    post.origin_location_city = extracted.origin_location_city
    post.origin_location_state = extracted.origin_location_state
    post.origin_location_county = extracted.origin_location_county
    post.origin_location_zip = extracted.origin_location_zip
    post.availability_notes = extracted.availability_notes
    post.contact_method = extracted.contact_method

    # Infrastructure fields
    post.infra_role = extracted.infra_role
    post.infra_categories = _join_pipe(valid_infra_categories)
    post.infra_categories_other = _join_pipe(infra_categories_other)
    post.quantity = extracted.quantity
    post.condition = valid_condition
    post.condition_other = condition_other
    post.dates_needed = extracted.dates_needed

    post.extraction_confidence = extracted.confidence
    post.extraction_method = f"llm_{extractor.provider_name()}"

    has_unmapped_taxonomy = bool(
        vibe_other or contribution_other or infra_categories_other or condition_other
    )

    if extracted.confidence < settings.llm_extraction_confidence_threshold or has_unmapped_taxonomy:
        post.status = PostStatus.NEEDS_REVIEW
    else:
        post.status = PostStatus.INDEXED

    if post.status == PostStatus.INDEXED:
        await sync_profile_from_post(session, post)

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
            "seeker_intent": post.seeker_intent,
            "infra_role": post.infra_role,
            "vibes_other": vibe_other,
            "contribution_types_other": contribution_other,
            "infra_categories_other": infra_categories_other,
            "condition_other": condition_other,
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
