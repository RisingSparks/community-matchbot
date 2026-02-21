from pydantic import BaseModel, field_validator

from matchbot.db.models import PostType
from matchbot.taxonomy import (
    CONTRIBUTION_TYPES,
    INFRASTRUCTURE_CATEGORIES,
    INFRASTRUCTURE_CONDITIONS,
    VIBES,
)


class ExtractedPost(BaseModel):
    # --- shared fields ---
    role: str = "unknown"          # seeker | camp | unknown (mentorship path)
    post_type: str = PostType.MENTORSHIP  # mentorship | infrastructure
    confidence: float = 0.5        # 0.0–1.0
    extraction_notes: str | None = None

    seeker_intent: str | None = None  # membership | skills_learning | unknown | None

    # --- mentorship fields ---
    camp_name: str | None = None
    camp_size_min: int | None = None
    camp_size_max: int | None = None
    year: int | None = None
    vibes: list[str] = []
    contribution_types: list[str] = []
    location_preference: str | None = None
    availability_notes: str | None = None
    contact_method: str | None = None

    # --- infrastructure / "Bitch n Swap" fields ---
    infra_role: str | None = None          # seeking | offering
    infra_categories: list[str] = []       # from INFRASTRUCTURE_CATEGORIES
    quantity: str | None = None            # "2 units", "~50 ft"
    condition: str | None = None           # from INFRASTRUCTURE_CONDITIONS
    dates_needed: str | None = None        # near-verbatim from post

    # -----------------------------------------------------------------------
    # Validators
    # -----------------------------------------------------------------------

    @field_validator("seeker_intent")
    @classmethod
    def validate_seeker_intent(cls, v: str | None) -> str | None:
        if v is None:
            return None
        allowed = {"membership", "skills_learning", "unknown"}
        return v if v in allowed else None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"seeker", "camp", "unknown"}
        return v if v in allowed else "unknown"

    @field_validator("post_type")
    @classmethod
    def validate_post_type(cls, v: str) -> str:
        allowed = {PostType.MENTORSHIP, PostType.INFRASTRUCTURE}
        return v if v in allowed else PostType.MENTORSHIP

    @field_validator("infra_role")
    @classmethod
    def validate_infra_role(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v if v in {"seeking", "offering"} else None

    @field_validator("vibes")
    @classmethod
    def validate_vibes(cls, v: list[str]) -> list[str]:
        return [x.lower() for x in v if x.lower() in VIBES]

    @field_validator("contribution_types")
    @classmethod
    def validate_contribution_types(cls, v: list[str]) -> list[str]:
        return [x.lower() for x in v if x.lower() in CONTRIBUTION_TYPES]

    @field_validator("infra_categories")
    @classmethod
    def validate_infra_categories(cls, v: list[str]) -> list[str]:
        return [x.lower() for x in v if x.lower() in INFRASTRUCTURE_CATEGORIES]

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.lower() if v.lower() in INFRASTRUCTURE_CONDITIONS else None

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))
