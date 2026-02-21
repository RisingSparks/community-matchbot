import json
import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------


class PostRole:
    SEEKER = "seeker"
    CAMP = "camp"
    UNKNOWN = "unknown"


class PostStatus:
    RAW = "raw"
    EXTRACTED = "extracted"
    INDEXED = "indexed"
    NEEDS_REVIEW = "needs_review"
    SKIPPED = "skipped"
    ERROR = "error"


class MatchStatus:
    PROPOSED = "proposed"
    APPROVED = "approved"
    INTRO_SENT = "intro_sent"
    CONVERSATION_STARTED = "conversation_started"
    DECLINED = "declined"
    ACCEPTED_PENDING = "accepted_pending"
    ONBOARDED = "onboarded"
    CLOSED_STALE = "closed_stale"


class Platform:
    REDDIT = "reddit"
    DISCORD = "discord"
    FACEBOOK = "facebook"
    MANUAL = "manual"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class Profile(SQLModel, table=True):
    __tablename__ = "profile"

    id: str = Field(default_factory=_new_id, primary_key=True)
    role: str = Field(index=True)  # PostRole
    display_name: str = Field(default="")
    platform: str = Field(index=True)  # Platform
    platform_author_id: str = Field(index=True)
    camp_name: str | None = Field(default=None)
    openings_count: int | None = Field(default=None)
    vibes: str = Field(default="")  # pipe-delimited
    contribution_types: str = Field(default="")  # pipe-delimited
    year: int | None = Field(default=None)
    availability_notes: str | None = Field(default=None)
    contact_method: str | None = Field(default=None)
    notes: str | None = Field(default=None)  # moderator freeform
    is_active: bool = Field(default=True)
    opted_in: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def vibes_list(self) -> list[str]:
        return [v for v in self.vibes.split("|") if v] if self.vibes else []

    def contribution_types_list(self) -> list[str]:
        return [v for v in self.contribution_types.split("|") if v] if self.contribution_types else []


class Post(SQLModel, table=True):
    __tablename__ = "post"

    id: str = Field(default_factory=_new_id, primary_key=True)
    platform: str = Field(index=True)
    platform_post_id: str = Field(index=True)  # deduplication key
    platform_author_id: str = Field(default="")
    author_display_name: str = Field(default="")
    source_url: str = Field(default="")
    source_community: str = Field(default="")
    title: str = Field(default="")
    raw_text: str = Field(default="")  # max 2000 chars

    detected_at: datetime = Field(default_factory=_now)
    status: str = Field(default=PostStatus.RAW, index=True)
    expires_at: datetime | None = Field(default=None)

    # Extraction results
    role: str | None = Field(default=None)
    vibes: str = Field(default="")  # pipe-delimited
    contribution_types: str = Field(default="")  # pipe-delimited
    camp_name: str | None = Field(default=None)
    camp_size_min: int | None = Field(default=None)
    camp_size_max: int | None = Field(default=None)
    year: int | None = Field(default=None)
    location_preference: str | None = Field(default=None)
    availability_notes: str | None = Field(default=None)
    contact_method: str | None = Field(default=None)
    extraction_confidence: float | None = Field(default=None)
    extraction_method: str | None = Field(default=None)  # keyword | llm_anthropic | llm_openai

    # FK
    profile_id: str | None = Field(default=None, foreign_key="profile.id")

    def vibes_list(self) -> list[str]:
        return [v for v in self.vibes.split("|") if v] if self.vibes else []

    def contribution_types_list(self) -> list[str]:
        return [v for v in self.contribution_types.split("|") if v] if self.contribution_types else []


class Match(SQLModel, table=True):
    __tablename__ = "match"

    id: str = Field(default_factory=_new_id, primary_key=True)
    seeker_post_id: str = Field(foreign_key="post.id", index=True)
    camp_post_id: str = Field(foreign_key="post.id", index=True)
    seeker_profile_id: str | None = Field(default=None, foreign_key="profile.id")
    camp_profile_id: str | None = Field(default=None, foreign_key="profile.id")

    status: str = Field(default=MatchStatus.PROPOSED, index=True)
    score: float = Field(default=0.0)
    score_breakdown: str = Field(default="{}")  # JSON string
    match_method: str = Field(default="deterministic")  # deterministic | llm_triage
    confidence: float | None = Field(default=None)
    moderator_notes: str | None = Field(default=None)
    intro_sent_at: datetime | None = Field(default=None)
    intro_platform: str | None = Field(default=None)
    mismatch_reason: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def score_breakdown_dict(self) -> dict:
        try:
            return json.loads(self.score_breakdown)
        except (json.JSONDecodeError, TypeError):
            return {}


class Event(SQLModel, table=True):
    __tablename__ = "event"

    id: str = Field(default_factory=_new_id, primary_key=True)
    occurred_at: datetime = Field(default_factory=_now)
    event_type: str = Field(index=True)
    post_id: str | None = Field(default=None, foreign_key="post.id")
    match_id: str | None = Field(default=None, foreign_key="match.id")
    actor: str = Field(default="system")  # system | moderator:username
    payload: str = Field(default="{}")  # JSON string
    note: str | None = Field(default=None)

    def payload_dict(self) -> dict:
        try:
            return json.loads(self.payload)
        except (json.JSONDecodeError, TypeError):
            return {}
