from pathlib import Path

import yaml

_TAXONOMY_PATH = Path(__file__).parent / "config" / "taxonomy.yaml"


def _load_taxonomy() -> dict:
    with open(_TAXONOMY_PATH) as f:
        return yaml.safe_load(f)


_taxonomy = _load_taxonomy()

VIBES: frozenset[str] = frozenset(_taxonomy.get("vibes", []))
CONTRIBUTION_TYPES: frozenset[str] = frozenset(_taxonomy.get("contribution_types", []))
INFRASTRUCTURE_CATEGORIES: frozenset[str] = frozenset(
    _taxonomy.get("infrastructure_categories", [])
)
INFRASTRUCTURE_CONDITIONS: frozenset[str] = frozenset(
    _taxonomy.get("infrastructure_conditions", [])
)

# Preserve compatibility with historical labels that were renamed in taxonomy.yaml.
CONTRIBUTION_TYPE_ALIASES: dict[str, str] = {
    "admin": "camp_admin",
    "logistics": "camp_admin",
}

INFRASTRUCTURE_CATEGORY_ALIASES: dict[str, str] = {
    "scaffold": "scaffolding",
    "scaffolds": "scaffolding",
    "scaffold tower": "scaffolding",
    "scaffold towers": "scaffolding",
    "shower stall": "shower",
    "shower stalls": "shower",
    "showers": "shower",
    "gazebos": "gazebo",
    "pavilion": "gazebo",
    "pavilions": "gazebo",
    "canopies": "canopy",
    "awning": "canopy",
    "awnings": "canopy",
    "temporary structure": "structure",
    "temporary structures": "structure",
    "structure": "structure",
    "structures": "structure",
    "parts bundle": "parts",
    "spare parts": "parts",
    "hardware bundle": "parts",
    "hardware bundles": "parts",
}


def _canonicalize_terms(
    raw: list[str],
    allowed: frozenset[str],
    *,
    aliases: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    canonical: list[str] = []
    other: list[str] = []
    seen_canonical: set[str] = set()
    seen_other: set[str] = set()

    for value in raw:
        cleaned = value.strip().lower()
        if not cleaned:
            continue
        if aliases is not None:
            cleaned = aliases.get(cleaned, cleaned)
        if cleaned in allowed:
            if cleaned not in seen_canonical:
                canonical.append(cleaned)
                seen_canonical.add(cleaned)
        elif cleaned not in seen_other:
            other.append(cleaned)
            seen_other.add(cleaned)

    return canonical, other


def normalize_vibes(raw: list[str]) -> list[str]:
    """Return only taxonomy-valid vibe values, lowercased."""
    canonical, _ = _canonicalize_terms(raw, VIBES)
    return canonical


def split_vibes(raw: list[str]) -> tuple[list[str], list[str]]:
    """Return (canonical_values, unmapped_values) for vibe labels."""
    return _canonicalize_terms(raw, VIBES)


def normalize_contribution_types(raw: list[str]) -> list[str]:
    """Return only taxonomy-valid contribution type values, lowercased."""
    canonical, _ = _canonicalize_terms(raw, CONTRIBUTION_TYPES, aliases=CONTRIBUTION_TYPE_ALIASES)
    return canonical


def split_contribution_types(raw: list[str]) -> tuple[list[str], list[str]]:
    """Return (canonical_values, unmapped_values) for contribution labels."""
    return _canonicalize_terms(raw, CONTRIBUTION_TYPES, aliases=CONTRIBUTION_TYPE_ALIASES)


def normalize_infra_categories(raw: list[str]) -> list[str]:
    """Return only taxonomy-valid infrastructure category values, lowercased."""
    canonical, _ = _canonicalize_terms(
        raw,
        INFRASTRUCTURE_CATEGORIES,
        aliases=INFRASTRUCTURE_CATEGORY_ALIASES,
    )
    return canonical


def split_infra_categories(raw: list[str]) -> tuple[list[str], list[str]]:
    """Return (canonical_values, unmapped_values) for infra category labels."""
    return _canonicalize_terms(
        raw,
        INFRASTRUCTURE_CATEGORIES,
        aliases=INFRASTRUCTURE_CATEGORY_ALIASES,
    )


def normalize_condition(raw: str | None) -> str | None:
    """Return a canonical infrastructure condition or None."""
    if raw is None:
        return None
    cleaned = raw.strip().lower()
    if not cleaned:
        return None
    return cleaned if cleaned in INFRASTRUCTURE_CONDITIONS else None


def normalize_role(raw: str | None) -> str | None:
    """Return a canonical mentorship role or None."""
    if raw is None:
        return None
    cleaned = raw.strip().lower()
    if not cleaned:
        return None
    return cleaned if cleaned in {"seeker", "camp", "unknown"} else None


def normalize_infra_role(raw: str | None) -> str | None:
    """Return a canonical infrastructure role or None."""
    if raw is None:
        return None
    cleaned = raw.strip().lower()
    if not cleaned:
        return None
    return cleaned if cleaned in {"seeking", "offering"} else None
