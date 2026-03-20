# Plan: Add Match Queue Endpoints to Mod API

## Context

The mod API (`src/matchbot/mod/router.py`) only covers the *post review* flow (NEEDS_REVIEW).
It has no match-related endpoints, so a web-based moderator UI cannot see the match queue,
view intro drafts, or take any match actions. We need to add a full set of match endpoints
so the mod UI can surface `intro_draft` and let the moderator approve/decline/send.

## Files to change

| File | Change |
|------|--------|
| `src/matchbot/mod/router.py` | Add `_match_to_dict()` helper, request models, and 5 new endpoints |

No model changes, no migrations — `intro_draft` already exists on `Match`.

## Reused internals

| Symbol | Source |
|--------|--------|
| `get_match`, `get_queue` | `matchbot.matching.queue` |
| `transition` | `matchbot.lifecycle.status` |
| `send_intro_message` | `matchbot.messaging` |
| `render_intro` | `matchbot.messaging.renderer` |
| `_post_to_dict` | already in `router.py` |
| `_require_mod`, `_get_session` | already in `router.py` |

## Implementation

### 1. New imports at top of `router.py`

```python
from datetime import UTC, datetime  # already present
from matchbot.db.models import Event, Match, MatchStatus, Post, PostStatus  # add Match, MatchStatus
from matchbot.lifecycle.status import InvalidTransitionError, transition
from matchbot.matching.queue import get_match, get_queue
```

(`send_intro_message` and `render_intro` imported inline in the handler to avoid circular imports.)

### 2. New request models

```python
class ApproveMatchRequest(BaseModel):
    note: str | None = None

class DeclineMatchRequest(BaseModel):
    reason: str | None = None

class SendIntroRequest(BaseModel):
    platform: str | None = None  # defaults to seeker.platform
```

### 3. `_match_to_dict()` helper

```python
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
```

### 4. New endpoints

**`GET /api/mod/matches`** — list queue

```python
@router.get("/matches")
async def list_matches(
    status: str = MatchStatus.PROPOSED,
    limit: int = 50,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> list[dict]:
    matches = await get_queue(session, status=status, limit=limit)
    result = []
    for m in matches:
        seeker = await session.get(Post, m.seeker_post_id)
        camp = await session.get(Post, m.camp_post_id)
        result.append(_match_to_dict(m, seeker, camp))
    return result
```

**`GET /api/mod/matches/{match_id}`** — single match detail

```python
@router.get("/matches/{match_id}")
async def get_match_detail(
    match_id: str,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    match = await get_match(session, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    seeker = await session.get(Post, match.seeker_post_id)
    camp = await session.get(Post, match.camp_post_id)
    return _match_to_dict(match, seeker, camp)
```

**`POST /api/mod/matches/{match_id}/approve`**

```python
@router.post("/matches/{match_id}/approve")
async def approve_match(
    match_id: str,
    body: ApproveMatchRequest,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    match = await get_match(session, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    try:
        await transition(session, match, MatchStatus.APPROVED, actor="moderator", note=body.note)
    except InvalidTransitionError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "match_id": match_id, "new_status": MatchStatus.APPROVED}
```

**`POST /api/mod/matches/{match_id}/decline`**

```python
@router.post("/matches/{match_id}/decline")
async def decline_match(
    match_id: str,
    body: DeclineMatchRequest,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    match = await get_match(session, match_id)
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
```

**`POST /api/mod/matches/{match_id}/send-intro`**

```python
@router.post("/matches/{match_id}/send-intro")
async def send_match_intro(
    match_id: str,
    body: SendIntroRequest,
    dry_run: bool = False,
    _: None = Depends(_require_mod),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    match = await get_match(session, match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    if match.status != MatchStatus.APPROVED:
        raise HTTPException(409, f"Match must be APPROVED before sending intro (current: {match.status})")

    seeker = await session.get(Post, match.seeker_post_id)
    camp = await session.get(Post, match.camp_post_id)
    if not seeker or not camp:
        raise HTTPException(500, "Could not load seeker or camp post")

    target_platform = body.platform or (seeker.platform if seeker else "reddit")

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
```

## Verification

1. `uv run pytest tests/ -x -q` — all existing tests pass
2. Start server: `uv run uvicorn matchbot.server:app --port 8080`
3. `curl -s http://localhost:8080/api/mod/matches` — returns JSON array (empty or with matches)
4. `curl -s http://localhost:8080/api/mod/matches/<id>` — returns match dict with `intro_draft` field
5. `curl -s -X POST http://localhost:8080/api/mod/matches/<id>/approve -d '{}'` — transitions to APPROVED
6. `curl -s -X POST http://localhost:8080/api/mod/matches/<id>/send-intro?dry_run=true -d '{}'` — returns `intro_text` without sending
