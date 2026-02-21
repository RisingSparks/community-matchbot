"""Status lifecycle state machine for Match records."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Event, Match, MatchStatus

# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[str, set[str]] = {
    MatchStatus.PROPOSED: {
        MatchStatus.APPROVED,
        MatchStatus.DECLINED,
        MatchStatus.CLOSED_STALE,
    },
    MatchStatus.APPROVED: {
        MatchStatus.INTRO_SENT,
        MatchStatus.DECLINED,
        MatchStatus.CLOSED_STALE,
    },
    MatchStatus.INTRO_SENT: {
        MatchStatus.CONVERSATION_STARTED,
        MatchStatus.DECLINED,
        MatchStatus.CLOSED_STALE,
    },
    MatchStatus.CONVERSATION_STARTED: {
        MatchStatus.ACCEPTED_PENDING,
        MatchStatus.DECLINED,
        MatchStatus.CLOSED_STALE,
    },
    MatchStatus.ACCEPTED_PENDING: {
        MatchStatus.ONBOARDED,
        MatchStatus.DECLINED,
        MatchStatus.CLOSED_STALE,
    },
    # Terminal states — no further transitions
    MatchStatus.ONBOARDED: set(),
    MatchStatus.DECLINED: set(),
    MatchStatus.CLOSED_STALE: set(),
}


class InvalidTransitionError(Exception):
    """Raised when a status transition is not allowed."""


async def transition(
    session: AsyncSession,
    match: Match,
    new_status: str,
    actor: str = "system",
    note: str | None = None,
) -> Match:
    """
    Transition a Match to new_status.

    Validates the transition, updates the record, and appends an Event.
    Raises InvalidTransitionError for disallowed transitions.
    """
    current = match.status
    allowed = _VALID_TRANSITIONS.get(current, set())

    if new_status not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition match {match.id!r} from {current!r} to {new_status!r}. "
            f"Allowed: {sorted(allowed)}"
        )

    match.status = new_status
    match.updated_at = datetime.now(UTC)

    event = Event(
        event_type="match_status_changed",
        match_id=match.id,
        actor=actor,
        payload=json.dumps({"from": current, "to": new_status}),
        note=note,
    )

    session.add(match)
    session.add(event)
    await session.commit()
    await session.refresh(match)
    return match
