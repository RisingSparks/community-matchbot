from pydantic import BaseModel, field_validator

from matchbot.taxonomy import CONTRIBUTION_TYPES, VIBES


class ExtractedPost(BaseModel):
    role: str = "unknown"  # seeker | camp | unknown
    camp_name: str | None = None
    camp_size_min: int | None = None
    camp_size_max: int | None = None
    year: int | None = None
    vibes: list[str] = []
    contribution_types: list[str] = []
    location_preference: str | None = None
    availability_notes: str | None = None
    contact_method: str | None = None
    confidence: float = 0.5  # 0.0–1.0
    extraction_notes: str | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"seeker", "camp", "unknown"}
        if v not in allowed:
            return "unknown"
        return v

    @field_validator("vibes")
    @classmethod
    def validate_vibes(cls, v: list[str]) -> list[str]:
        return [x.lower() for x in v if x.lower() in VIBES]

    @field_validator("contribution_types")
    @classmethod
    def validate_contribution_types(cls, v: list[str]) -> list[str]:
        return [x.lower() for x in v if x.lower() in CONTRIBUTION_TYPES]

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))
