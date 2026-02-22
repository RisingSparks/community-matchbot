"""Moderator API — /api/mod/"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Event, Match, MatchStatus, Post, PostStatus
from matchbot.lifecycle.status import InvalidTransitionError, transition
from matchbot.matching.queue import get_match as _get_match
from matchbot.matching.queue import get_queue as _get_match_queue
from matchbot.settings import get_settings
from matchbot.taxonomy import (
    CONTRIBUTION_TYPES,
    INFRASTRUCTURE_CATEGORIES,
    INFRASTRUCTURE_CONDITIONS,
    VIBES,
    normalize_contribution_types,
    normalize_infra_categories,
    normalize_vibes,
)

router = APIRouter(prefix="/api/mod", tags=["mod"])


# ---------------------------------------------------------------------------
# Session dependency
# ---------------------------------------------------------------------------


async def _get_session():
    """FastAPI-compatible async session dependency."""
    from matchbot.db.engine import get_engine

    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        yield session


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def _require_mod(request: Request) -> None:
    settings = get_settings()
    if not settings.mod_secret_key:
        return  # auth disabled in dev
    cookie = request.cookies.get("mod_session")
    if not cookie or "." not in cookie:
        raise HTTPException(401, "Not authenticated")
    ts_str, sig = cookie.rsplit(".", 1)
    try:
        ts_ms = int(ts_str)
    except ValueError:
        raise HTTPException(401, "Invalid session")
    now_ms = int(time.time() * 1000)
    if now_ms - ts_ms > 7 * 24 * 3600 * 1000:
        raise HTTPException(401, "Session expired")
    expected = hmac.new(settings.mod_secret_key.encode(), ts_str.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(401, "Invalid session")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    password: str


class OverrideFields(BaseModel):
    note: str | None = None
    role: str | None = None
    vibes: list[str] | None = None
    contribution_types: list[str] | None = None
    camp_name: str | None = None
    year: int | None = None
    infra_role: str | None = None
    infra_categories: list[str] | None = None
    quantity: str | None = None
    condition: str | None = None


DISMISS_REASONS = {"spam", "off-topic", "duplicate", "not-real", "other"}


class DismissRequest(BaseModel):
    reason: str
    note: str | None = None

    @field_validator("reason")
    @classmethod
    def check_reason(cls, v: str) -> str:
        if v not in DISMISS_REASONS:
            raise ValueError(f"must be one of {sorted(DISMISS_REASONS)}")
        return v


class ApproveMatchRequest(BaseModel):
    note: str | None = None


class DeclineMatchRequest(BaseModel):
    reason: str | None = None


class SendIntroRequest(BaseModel):
    platform: str | None = None  # defaults to seeker.platform


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_mod_overrides(post: Post, body: OverrideFields) -> None:
    """Apply list-valued overrides to post; multi-value fields normalized via taxonomy."""
    if body.role is not None:
        post.role = body.role
    if body.vibes is not None:
        post.vibes = "|".join(normalize_vibes(body.vibes))
    if body.contribution_types is not None:
        post.contribution_types = "|".join(normalize_contribution_types(body.contribution_types))
    if body.camp_name is not None:
        post.camp_name = body.camp_name
    if body.year is not None:
        post.year = body.year
    if body.infra_role is not None:
        post.infra_role = body.infra_role
    if body.infra_categories is not None:
        post.infra_categories = "|".join(normalize_infra_categories(body.infra_categories))
    if body.quantity is not None:
        post.quantity = body.quantity
    if body.condition is not None:
        post.condition = body.condition


async def _write_event(
    session: AsyncSession,
    post: Post,
    event_type: str,
    payload: dict,
    note: str | None = None,
) -> None:
    event = Event(
        event_type=event_type,
        post_id=post.id,
        actor="moderator",
        payload=json.dumps(payload),
        note=note,
    )
    session.add(event)


def _post_to_dict(post: Post, age_hours: float | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": post.id,
        "platform": post.platform,
        "platform_post_id": post.platform_post_id,
        "platform_author_id": post.platform_author_id,
        "author_display_name": post.author_display_name,
        "source_url": post.source_url,
        "source_community": post.source_community,
        "title": post.title,
        "raw_text": post.raw_text,
        "detected_at": post.detected_at.isoformat(),
        "status": post.status,
        "role": post.role,
        "seeker_intent": post.seeker_intent,
        "vibes": post.vibes_list(),
        "contribution_types": post.contribution_types_list(),
        "camp_name": post.camp_name,
        "camp_size_min": post.camp_size_min,
        "camp_size_max": post.camp_size_max,
        "year": post.year,
        "availability_notes": post.availability_notes,
        "contact_method": post.contact_method,
        "extraction_confidence": post.extraction_confidence,
        "extraction_method": post.extraction_method,
        "post_type": post.post_type,
        "infra_role": post.infra_role,
        "infra_categories": post.infra_categories_list(),
        "quantity": post.quantity,
        "condition": post.condition,
    }
    if age_hours is not None:
        d["age_hours"] = age_hours
    return d


def _event_to_dict(event: Event) -> dict[str, Any]:
    return {
        "id": event.id,
        "occurred_at": event.occurred_at.isoformat(),
        "event_type": event.event_type,
        "actor": event.actor,
        "payload": event.payload_dict(),
        "note": event.note,
    }


def _match_to_dict(
    match: Match,
    seeker: Post | None = None,
    camp: Post | None = None,
) -> dict[str, Any]:
    return {
        "id": match.id,
        "status": match.status,
        "score": match.score,
        "score_breakdown": match.score_breakdown_dict(),
        "match_method": match.match_method,
        "confidence": match.confidence,
        "moderator_notes": match.moderator_notes,
        "mismatch_reason": match.mismatch_reason,
        "intro_draft": match.intro_draft,
        "intro_sent_at": match.intro_sent_at.isoformat() if match.intro_sent_at else None,
        "intro_platform": match.intro_platform,
        "created_at": match.created_at.isoformat(),
        "seeker": _post_to_dict(seeker) if seeker else None,
        "camp": _post_to_dict(camp) if camp else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def mod_index() -> dict:
    return {"status": "ok"}


@router.post("/auth/login")
async def login(body: LoginRequest, response: Response) -> dict:
    settings = get_settings()
    if settings.mod_password and not hmac.compare_digest(body.password, settings.mod_password):
        raise HTTPException(401, "Invalid password")
    ts_str = str(int(time.time() * 1000))
    if settings.mod_secret_key:
        sig = hmac.new(settings.mod_secret_key.encode(), ts_str.encode(), hashlib.sha256).hexdigest()
    else:
        sig = "dev"
    response.set_cookie(
        key="mod_session",
        value=f"{ts_str}.{sig}",
        httponly=True,
        samesite="none",
        secure=True,
        path="/api/mod",
        max_age=604800,
    )
    return {"ok": True}


@router.post("/auth/logout")
async def logout(response: Response, _: None = Depends(_require_mod)) -> dict:
    response.set_cookie(
        key="mod_session",
        value="",
        httponly=True,
        samesite="none",
        secure=True,
        path="/api/mod",
        max_age=0,
    )
    return {"ok": True}


@router.get("/queue")
async def get_queue(
    post_type: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> list[dict]:
    q = select(Post).where(Post.status == PostStatus.NEEDS_REVIEW)
    if post_type:
        q = q.where(Post.post_type == post_type)
    if platform:
        q = q.where(Post.platform == platform)
    q = q.order_by(Post.detected_at.asc()).limit(limit)  # type: ignore[arg-type]
    posts = (await session.exec(q)).all()
    now = datetime.now(UTC)
    result = []
    for post in posts:
        detected = post.detected_at
        if detected.tzinfo is None:
            detected = detected.replace(tzinfo=UTC)
        age_hours = round((now - detected).total_seconds() / 3600, 1)
        result.append(_post_to_dict(post, age_hours=age_hours))
    return result


@router.get("/posts/{post_id}")
async def get_post(
    post_id: str,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    events = (await session.exec(select(Event).where(Event.post_id == post_id))).all()
    d = _post_to_dict(post)
    d["events"] = [_event_to_dict(e) for e in events]
    return d


@router.post("/posts/{post_id}/approve")
async def approve_post(
    post_id: str,
    body: OverrideFields,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    if post.status != PostStatus.NEEDS_REVIEW:
        raise HTTPException(409, f"Post status is {post.status!r}, expected needs_review")
    _apply_mod_overrides(post, body)
    post.status = PostStatus.INDEXED
    await _write_event(session, post, "post_approved", {"post_id": post_id}, note=body.note)
    await session.commit()
    await session.refresh(post)
    from matchbot.matching.queue import propose_matches

    await propose_matches(session, post)
    return {"ok": True, "post_id": post.id, "new_status": "INDEXED"}


@router.post("/posts/{post_id}/dismiss")
async def dismiss_post(
    post_id: str,
    body: DismissRequest,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    if post.status not in {PostStatus.NEEDS_REVIEW, PostStatus.ERROR}:
        raise HTTPException(409, f"Post status is {post.status!r}, cannot dismiss")
    post.status = PostStatus.SKIPPED
    await _write_event(
        session,
        post,
        "post_dismissed",
        {"post_id": post_id, "reason": body.reason},
        note=body.note,
    )
    await session.commit()
    return {"ok": True, "post_id": post.id, "new_status": "SKIPPED"}


@router.post("/posts/{post_id}/edit")
async def edit_post(
    post_id: str,
    body: OverrideFields,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    if post.status != PostStatus.NEEDS_REVIEW:
        raise HTTPException(409, f"Post status is {post.status!r}, expected needs_review")
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(422, "At least one field must be provided")
    _apply_mod_overrides(post, body)
    await _write_event(
        session,
        post,
        "post_edited",
        {"post_id": post_id, "fields": list(fields.keys())},
        note=body.note,
    )
    await session.commit()
    return {"ok": True, "post_id": post.id}


@router.post("/posts/{post_id}/re-extract")
async def re_extract_post(
    post_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    post.status = PostStatus.RAW
    await session.commit()
    background_tasks.add_task(_run_extraction, post_id)
    return {"ok": True, "post_id": post.id, "message": "re-extraction queued"}


async def _run_extraction(post_id: str) -> None:
    from matchbot.db.engine import get_engine
    from matchbot.extraction import process_post
    from matchbot.extraction.anthropic_extractor import AnthropicExtractor
    from matchbot.extraction.openai_extractor import OpenAIExtractor

    settings = get_settings()
    extractor = (
        AnthropicExtractor() if settings.llm_provider == "anthropic" else OpenAIExtractor()
    )
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        post = await session.get(Post, post_id)
        if post:
            try:
                await process_post(session, post, extractor)
            finally:
                await extractor.aclose()


@router.get("/taxonomy")
async def get_taxonomy(_: None = Depends(_require_mod)) -> dict:
    return {
        "vibes": sorted(VIBES),
        "contribution_types": sorted(CONTRIBUTION_TYPES),
        "infra_categories": sorted(INFRASTRUCTURE_CATEGORIES),
        "conditions": sorted(INFRASTRUCTURE_CONDITIONS),
        "roles": ["seeker", "camp", "unknown"],
    }


@router.get("/stats")
async def get_stats(
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    now = datetime.now(UTC)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

    # Count NEEDS_REVIEW posts
    nr_posts = (
        await session.exec(select(Post).where(Post.status == PostStatus.NEEDS_REVIEW))
    ).all()
    needs_review_count = len(nr_posts)

    # Age of the oldest NEEDS_REVIEW post
    oldest_age_hours = None
    if nr_posts:
        oldest = min(nr_posts, key=lambda p: p.detected_at)
        detected = oldest.detected_at
        if detected.tzinfo is None:
            detected = detected.replace(tzinfo=UTC)
        oldest_age_hours = round((now - detected).total_seconds() / 3600, 1)

    # Daily approved / dismissed event counts
    all_events = (await session.exec(select(Event))).all()
    approved_today = sum(
        1
        for e in all_events
        if e.event_type == "post_approved"
        and e.occurred_at.replace(tzinfo=None) >= today_midnight
    )
    dismissed_today = sum(
        1
        for e in all_events
        if e.event_type == "post_dismissed"
        and e.occurred_at.replace(tzinfo=None) >= today_midnight
    )

    return {
        "needs_review_count": needs_review_count,
        "oldest_needs_review_age_hours": oldest_age_hours,
        "approved_today": approved_today,
        "dismissed_today": dismissed_today,
    }


# ---------------------------------------------------------------------------
# Match endpoints
# ---------------------------------------------------------------------------


@router.get("/matches")
async def list_matches(
    status: str = MatchStatus.PROPOSED,
    limit: int = 50,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> list[dict]:
    matches = await _get_match_queue(session, status=status, limit=limit)
    result = []
    for m in matches:
        seeker = await session.get(Post, m.seeker_post_id)
        camp = await session.get(Post, m.camp_post_id)
        result.append(_match_to_dict(m, seeker, camp))
    return result


@router.get("/matches/{match_id}")
async def get_match_detail(
    match_id: str,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    match = await _get_match(session, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    seeker = await session.get(Post, match.seeker_post_id)
    camp = await session.get(Post, match.camp_post_id)
    return _match_to_dict(match, seeker, camp)


@router.post("/matches/{match_id}/approve")
async def approve_match(
    match_id: str,
    body: ApproveMatchRequest,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    match = await _get_match(session, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    try:
        await transition(session, match, MatchStatus.APPROVED, actor="moderator", note=body.note)
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "match_id": match_id, "new_status": MatchStatus.APPROVED}


@router.post("/matches/{match_id}/decline")
async def decline_match(
    match_id: str,
    body: DeclineMatchRequest,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    match = await _get_match(session, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    match.mismatch_reason = body.reason or None
    session.add(match)
    await session.commit()
    try:
        await transition(session, match, MatchStatus.DECLINED, actor="moderator", note=body.reason)
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "match_id": match_id, "new_status": MatchStatus.DECLINED}


@router.post("/matches/{match_id}/send-intro")
async def send_match_intro(
    match_id: str,
    body: SendIntroRequest,
    dry_run: bool = False,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    match = await _get_match(session, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    if match.status != MatchStatus.APPROVED:
        raise HTTPException(
            409, f"Match must be APPROVED before sending intro (current: {match.status})"
        )

    seeker = await session.get(Post, match.seeker_post_id)
    camp = await session.get(Post, match.camp_post_id)
    if not seeker or not camp:
        raise HTTPException(500, "Could not load seeker or camp post")

    target_platform = body.platform or seeker.platform

    from matchbot.messaging.renderer import render_intro

    intro_text = match.intro_draft or render_intro(seeker, camp, target_platform)

    if dry_run:
        return {"dry_run": True, "platform": target_platform, "intro_text": intro_text}

    from matchbot.messaging import send_intro_message

    await send_intro_message(session, match, seeker, camp, target_platform)
    match.intro_sent_at = datetime.now(UTC)
    match.intro_platform = target_platform
    session.add(match)
    await transition(session, match, MatchStatus.INTRO_SENT, actor="moderator")
    return {"ok": True, "match_id": match_id, "platform": target_platform}
