"""Tests for the Match status lifecycle state machine."""

from __future__ import annotations

import pytest

from matchbot.db.models import Match, MatchStatus
from matchbot.lifecycle.status import InvalidTransitionError, transition


async def _make_match(session, status: str = MatchStatus.PROPOSED) -> Match:
    match = Match(
        seeker_post_id="seeker_post_id_placeholder",
        camp_post_id="camp_post_id_placeholder",
        status=status,
        score=0.75,
    )
    session.add(match)
    await session.commit()
    await session.refresh(match)
    return match


@pytest.mark.asyncio
async def test_proposed_to_approved(db_session):
    match = await _make_match(db_session)
    updated = await transition(db_session, match, MatchStatus.APPROVED, actor="moderator:alice")
    assert updated.status == MatchStatus.APPROVED


@pytest.mark.asyncio
async def test_proposed_to_declined(db_session):
    match = await _make_match(db_session)
    updated = await transition(db_session, match, MatchStatus.DECLINED, note="Different years")
    assert updated.status == MatchStatus.DECLINED


@pytest.mark.asyncio
async def test_approved_to_intro_sent(db_session):
    match = await _make_match(db_session, MatchStatus.APPROVED)
    updated = await transition(db_session, match, MatchStatus.INTRO_SENT)
    assert updated.status == MatchStatus.INTRO_SENT


@pytest.mark.asyncio
async def test_intro_sent_to_conversation_started(db_session):
    match = await _make_match(db_session, MatchStatus.INTRO_SENT)
    updated = await transition(db_session, match, MatchStatus.CONVERSATION_STARTED)
    assert updated.status == MatchStatus.CONVERSATION_STARTED


@pytest.mark.asyncio
async def test_conversation_started_to_accepted_pending(db_session):
    match = await _make_match(db_session, MatchStatus.CONVERSATION_STARTED)
    updated = await transition(db_session, match, MatchStatus.ACCEPTED_PENDING)
    assert updated.status == MatchStatus.ACCEPTED_PENDING


@pytest.mark.asyncio
async def test_accepted_pending_to_onboarded(db_session):
    match = await _make_match(db_session, MatchStatus.ACCEPTED_PENDING)
    updated = await transition(db_session, match, MatchStatus.ONBOARDED)
    assert updated.status == MatchStatus.ONBOARDED


@pytest.mark.asyncio
async def test_any_state_to_closed_stale(db_session):
    for status in [
        MatchStatus.PROPOSED,
        MatchStatus.APPROVED,
        MatchStatus.INTRO_SENT,
        MatchStatus.CONVERSATION_STARTED,
        MatchStatus.ACCEPTED_PENDING,
    ]:
        match = await _make_match(db_session, status)
        updated = await transition(db_session, match, MatchStatus.CLOSED_STALE)
        assert updated.status == MatchStatus.CLOSED_STALE


class TestInvalidTransitions:
    @pytest.mark.asyncio
    async def test_proposed_to_intro_sent_invalid(self, db_session):
        match = await _make_match(db_session)
        with pytest.raises(InvalidTransitionError):
            await transition(db_session, match, MatchStatus.INTRO_SENT)

    @pytest.mark.asyncio
    async def test_proposed_to_onboarded_invalid(self, db_session):
        match = await _make_match(db_session)
        with pytest.raises(InvalidTransitionError):
            await transition(db_session, match, MatchStatus.ONBOARDED)

    @pytest.mark.asyncio
    async def test_declined_is_terminal(self, db_session):
        match = await _make_match(db_session, MatchStatus.DECLINED)
        with pytest.raises(InvalidTransitionError):
            await transition(db_session, match, MatchStatus.PROPOSED)

    @pytest.mark.asyncio
    async def test_onboarded_is_terminal(self, db_session):
        match = await _make_match(db_session, MatchStatus.ONBOARDED)
        with pytest.raises(InvalidTransitionError):
            await transition(db_session, match, MatchStatus.PROPOSED)

    @pytest.mark.asyncio
    async def test_closed_stale_is_terminal(self, db_session):
        match = await _make_match(db_session, MatchStatus.CLOSED_STALE)
        with pytest.raises(InvalidTransitionError):
            await transition(db_session, match, MatchStatus.PROPOSED)

    @pytest.mark.asyncio
    async def test_approved_to_proposed_invalid(self, db_session):
        match = await _make_match(db_session, MatchStatus.APPROVED)
        with pytest.raises(InvalidTransitionError):
            await transition(db_session, match, MatchStatus.PROPOSED)


@pytest.mark.asyncio
async def test_transition_creates_event_record(db_session):
    from sqlmodel import select

    from matchbot.db.models import Event

    match = await _make_match(db_session)
    await transition(db_session, match, MatchStatus.APPROVED, actor="moderator:bob", note="great match")

    events = (
        await db_session.exec(select(Event).where(Event.match_id == match.id))
    ).all()
    assert len(events) >= 1
    event = events[-1]
    assert event.event_type == "match_status_changed"
    assert event.actor == "moderator:bob"
    assert event.note == "great match"

    payload = event.payload_dict()
    assert payload["from"] == MatchStatus.PROPOSED
    assert payload["to"] == MatchStatus.APPROVED
