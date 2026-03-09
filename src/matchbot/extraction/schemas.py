from pydantic import BaseModel, field_validator

from matchbot.db.models import PostType


class ExtractedPost(BaseModel):
    # --- shared fields ---
    role: str = "unknown"          # seeker | camp | unknown (mentorship path)
    post_type: str = PostType.MENTORSHIP  # mentorship | infrastructure
    confidence: float = 0.5        # 0.0–1.0
    extraction_notes: str | None = None

    seeker_intent: str | None = None  # join_camp | join_art_project | skills_learning | unknown | None

    # --- mentorship fields ---
    camp_name: str | None = None
    camp_size_min: int | None = None
    camp_size_max: int | None = None
    year: int | None = None
    vibes: list[str] = []
    vibes_other: list[str] = []
    contribution_types: list[str] = []
    contribution_types_other: list[str] = []
    location_preference: str | None = None
    availability_notes: str | None = None
    contact_method: str | None = None

    # --- infrastructure / "Bitch n Swap" fields ---
    infra_role: str | None = None          # seeking | offering
    infra_categories: list[str] = []       # from INFRASTRUCTURE_CATEGORIES
    infra_categories_other: list[str] = []
    quantity: str | None = None            # "2 units", "~50 ft"
    condition: str | None = None           # from INFRASTRUCTURE_CONDITIONS
    condition_other: str | None = None
    dates_needed: str | None = None        # near-verbatim from post

    # -----------------------------------------------------------------------
    # Validators
    # -----------------------------------------------------------------------

    @field_validator("seeker_intent")
    @classmethod
    def validate_seeker_intent(cls, v: str | None) -> str | None:
        if v is None:
            return None
        allowed = {"join_camp", "join_art_project", "skills_learning", "unknown"}
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
        return _normalize_string_list(v)

    @field_validator("contribution_types")
    @classmethod
    def validate_contribution_types(cls, v: list[str]) -> list[str]:
        return _normalize_string_list(v)

    @field_validator("infra_categories")
    @classmethod
    def validate_infra_categories(cls, v: list[str]) -> list[str]:
        return _normalize_string_list(v)

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip().lower()
        return cleaned or None

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    @field_validator(
        "vibes",
        "vibes_other",
        "contribution_types",
        "contribution_types_other",
        "infra_categories",
        "infra_categories_other",
        mode="before",
    )
    @classmethod
    def default_list_fields(cls, v: list[str] | None) -> list[str]:
        return v or []


def _normalize_string_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = value.strip().lower()
        if not cleaned or cleaned in seen:
            continue
        normalized.append(cleaned)
        seen.add(cleaned)

    return normalized
